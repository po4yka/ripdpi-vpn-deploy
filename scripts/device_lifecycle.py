"""Resumable encrypted device issue, refresh and complete fleet revocation."""
from __future__ import annotations

import base64
import copy
import json
import secrets
from datetime import UTC, datetime

from client_delivery_identity import authority, digest
from client_payload import ROOT, materialize, native_delivery, options
from device_lifecycle_credentials import ACTIVE, discover, issue, profile, revoke
from device_lifecycle_probe import render_profiles
from device_migration import envelope, parse_snapshot, un64
from device_migration_io import encoded, sha
from encrypted_client_document import MAX_BYTES, operate


def content(document):
    return {key: copy.deepcopy(value) for key, value in document.items() if key != 'device_operations'}


def fingerprint(document):
    return sha(encoded(content(document)))


def b64(value):
    return base64.b64encode(value).decode()


def revocation_intent(journal, operation_id):
    immutable = {key: journal[key] for key in (
        'schema_version', 'manifest_sha256', 'action', 'device', 'source',
        'before', 'after', 'profiles', 'grants', 'artifact')}
    immutable['canaries'] = {host: {key: row[key] for key in ('token', 'document_b64')}
                             for host, row in journal['canaries'].items()}
    return {'operation_id': operation_id, 'intent_sha256': sha(encoded(immutable))}


class Lifecycle:
    def __init__(self, manifest, io, *, writer=operate, now=None):
        self.manifest, self.io, self.writer = manifest, io, writer
        self.nodes = {node['host']: node for node in manifest['nodes']}
        self.journal_host = manifest['journal_host']
        self.journal_path = self.nodes[self.journal_host]['secrets_file']
        self.now = now or (lambda: datetime.now(UTC).strftime('%Y-%m-%dT%H:%M:%SZ'))
        self.manifest_digest = sha(encoded(manifest))
        self.name, self.action = manifest['device'], manifest['action']
        self.native = manifest['delivery'] is not None and manifest['delivery']['format'] == 'native'

    def documents(self):
        self.io.revalidate()
        return {host: self.io.read(node['secrets_file']) for host, node in self.nodes.items()}

    def snapshots(self):
        result = {}
        for pub in self.manifest['publishers']:
            host = pub['host']
            self.io.publisher(host, 'ready')
            result[host] = parse_snapshot(self.io.publisher(host, 'snapshot'))
        return result

    def inspect(self):
        self.io.verify_publisher_scope()
        source = self.io.source_identity()
        if self.action == 'issue' or self.native:
            self.io.admit_output(self.manifest['delivery']['output'])
        documents, snapshots = self.documents(), self.snapshots()
        found = {host: discover(doc, self.name) for host, doc in documents.items()}
        if self.action == 'issue' and any(found.values()):
            raise ValueError('device-already-exists-in-fleet')
        grants = {host: {token: row for token, row in snapshot['rows'].items()
                        if envelope(un64(row['document_b64']))[0]['client'] == self.name}
                  for host, snapshot in snapshots.items()}
        if self.action != 'issue' and not any(found.values()) and not (self.action == 'revoke' and any(grants.values())):
            raise ValueError('device-not-found-in-fleet')
        if any(snapshot['bootstrap'] for snapshot in snapshots.values()):
            raise ValueError('drain-active-bootstrap-grants-before-device-operation')
        if self.action == 'refresh' and not self.native and not any(not row['revoked'] and not row['expired'] for rows in grants.values() for row in rows.values()):
            raise ValueError('device-has-no-active-grant-to-refresh')
        if (self.action == 'issue' or self.native) and any(grants.values()):
            raise ValueError('device-has-existing-published-grants')
        if self.action in ('issue', 'refresh'):
            for host in self.manifest['delivery']['hosts']:
                entry = documents[host].get('client_registry', {}).get(self.name)
                if self.action == 'refresh' and (not isinstance(entry, dict) or entry.get('status') not in ACTIVE):
                    raise ValueError('refresh-requires-active-device-authority-on-every-delivery-host')
        for document in documents.values():
            if any(record.get('phase') != 'complete' for record in document.get('device_operations', {}).values()):
                raise ValueError('resume-existing-device-operation-first')
        review = {'operation_id': self.manifest['id'], 'action': self.action, 'device': self.name, 'source': source,
                  'nodes': {host: sorted(kinds) for host, kinds in found.items()},
                  'grants': {host: len(rows) for host, rows in grants.items()}}
        review['approval'] = sha(encoded({'manifest': self.manifest, 'documents': {host: fingerprint(doc) for host, doc in documents.items()},
                                         'snapshots': snapshots, 'source': source}))
        return documents, snapshots, grants, review

    def _save(self, journal):
        if len(encoded(journal)) > MAX_BYTES // 2:
            raise ValueError('device-operation-journal-capacity')
        self._validate_journal(journal)
        self.io.revalidate()
        if self.io.source_identity() != journal['source']:
            raise ValueError('device-source-changed')
        def transform(document):
            allowed = {journal['before'][self.journal_host], fingerprint(journal['after'][self.journal_host])}
            if fingerprint(document) not in allowed:
                raise ValueError('device-journal-authority-changed')
            records = document.setdefault('device_operations', {})
            previous = records.get(self.manifest['id'])
            if previous is not None and previous['manifest_sha256'] != self.manifest_digest:
                raise ValueError('device-operation-manifest-changed')
            records[self.manifest['id']] = copy.deepcopy(journal)
            return document, {}
        self.writer(self.journal_path, transform)

    def _render(self, documents, format, expires):
        delivery = self.manifest['delivery']
        hosts = delivery['hosts']
        selected = options(format, hosts=hosts, cohorts=[self.nodes[host]['cohort'] for host in hosts],
                           awg_host=delivery['awg_host'], expires=expires, utls='')
        paths = [self.nodes[host]['secrets_file'] for host in hosts]
        payload, bindings = materialize(self.name, selected, documents={node['secrets_file']: documents[host] for host, node in self.nodes.items()},
            source_paths=paths, private_only=True, extended=format == 'ripdpi', endpoints={host: self.io.endpoint(host) for host in hosts})
        for host in hosts:
            entry = documents[host]['client_registry'][self.name]
            auth = authority(documents[host], create=True)
            entry.update(status='delivered', hosts=list(hosts), cohorts=list(selected['cohorts']), delivery_sources=list(paths),
                         delivery_options=selected, token_expires=expires, awg_delivery_host=selected['awg_host'],
                         last_payload_identity=digest(self.name, selected, payload, bindings, auth))
            entry['formats'] = sorted(set(entry.get('formats', [])) | {format})
            entry.pop('migration_delivery', None)
        return payload

    def prepare(self, approval):
        documents, _, grants, review = self.inspect()
        if approval != review['approval']:
            raise ValueError('exact-device-operation-approval-required')
        expires = self.manifest['delivery']['expires'] if self.action == 'issue' else ''
        if expires and datetime.fromisoformat(expires) <= datetime.now(UTC):
            raise ValueError('device-delivery-expired')
        before = {host: fingerprint(doc) for host, doc in documents.items()}
        after = {host: content(doc) for host, doc in documents.items()}
        if self.action == 'issue':
            after = issue(after, self.nodes, self.name, self.manifest['delivery']['hosts'], self.now())
        elif self.action == 'revoke':
            after = revoke(after, self.name)
        journal = {'schema_version': 1, 'manifest_sha256': self.manifest_digest, 'phase': 'prepared', 'action': self.action,
                   'device': self.name, 'source': review['source'], 'before': before, 'after': after, 'profiles': {}, 'grants': {},
                   'written': [], 'adopted': [], 'published': [], 'artifact': None, 'canaries': {}, 'revocation': None}
        for host, document in documents.items():
            actual = discover(document, self.name)
            if self.action == 'revoke' and set(actual) - {'registry'}:
                journal['profiles'][host] = render_profiles(document, self.nodes[host]['cohort'], self.name, host,
                                                           self.io.endpoint(host), include_disabled=True)
            elif self.action != 'revoke' and host in self.manifest['delivery']['hosts']:
                journal['profiles'][host] = render_profiles(after[host], self.nodes[host]['cohort'], self.name, host, self.io.endpoint(host))
        if self.native:
            payload = self._render(after, 'native', '')
            journal['artifact'] = b64(encoded({'schema_version': 1, 'device': self.name,
                'subscription_url': None, 'profile': None, **payload['native']}))
        elif self.action == 'issue':
            token = secrets.token_urlsafe(32)
            token_hash = sha(token.encode())
            host = self.manifest['publishers'][0]['host']
            payload = self._render(after, self.manifest['delivery']['format'], self.manifest['delivery']['expires'])
            document = encoded({'schema_version': 1, 'client': self.name, 'expires': self.manifest['delivery']['expires'], 'payload_b64': b64(encoded(payload))})
            journal['grants'][host] = {token_hash: {'before': None, 'after': b64(document)}}
            artifact = {'schema_version': 1, 'device': self.name, 'subscription_url': self.manifest['publishers'][0]['origin'] + '/sub/' + token,
                        'profile': payload, 'amneziawg_configs': {}, 'naive_uris': {}}
            for selected in self.manifest['delivery']['hosts']:
                entry = after[selected]['client_registry'][self.name]
                entry['token_hash_prefix'] = token_hash[:8]
                native, _ = native_delivery(after[selected], profile(self.nodes[selected]['cohort']), self.name,
                                            selected, self.io.endpoint(selected))
                for key in native:
                    artifact[key].update(native[key])
            journal['artifact'] = b64(encoded(artifact))
        else:
            for host, rows in grants.items():
                journal['grants'][host] = {}
                for token_hash, row in rows.items():
                    original = un64(row['document_b64'])
                    if self.action == 'revoke':
                        revoked = after[host].setdefault('subscription', {}).setdefault('revoked_tokens', [])
                        if token_hash not in revoked:
                            revoked.append(token_hash)
                        updated = original
                    else:
                        if row['revoked'] or row['expired']:
                            continue
                        grant, previous = envelope(original)
                        format = 'ripdpi' if 'ripdpi' in previous else 'singbox'
                        if any('protocol' in item for item in previous.get('outbounds', [])):
                            raise ValueError('unsupported-device-grant-format')
                        payload = self._render(after, format, grant['expires'])
                        updated = encoded(dict(grant, payload_b64=b64(encoded(payload))))
                    journal['grants'][host][token_hash] = {'before': row['document_b64'], 'after': b64(updated)}
        if self.action == 'revoke':
            for host in [pub['host'] for pub in self.manifest['publishers']]:
                token = secrets.token_urlsafe(32)
                payload = encoded({'device_revocation_nonce': secrets.token_hex(32)})
                document = encoded({'schema_version': 1, 'client': 'device-revocation-check', 'expires': '', 'payload_b64': b64(payload)})
                journal['canaries'][host] = {'token': token, 'document_b64': b64(document), 'positive': False, 'cleanup_started': False, 'cleaned': False}
                after[host].setdefault('subscription', {}).setdefault('revoked_tokens', []).append(sha(token.encode()))
        if self.action == 'revoke':
            journal['revocation'] = revocation_intent(journal, self.manifest['id'])
        # Intent includes generated authority, every CAS preimage and recipient bytes.
        # Nothing changes on a managed node before this encrypted publication.
        self._save(journal)
        return self.status()

    def _journal(self):
        journal = self.io.read(self.journal_path).get('device_operations', {}).get(self.manifest['id'])
        if not isinstance(journal, dict) or journal.get('manifest_sha256') != self.manifest_digest:
            raise ValueError('device-operation-not-prepared-or-manifest-changed')
        self._validate_journal(journal)
        return copy.deepcopy(journal)

    def _validate_journal(self, journal):
        import jsonschema
        schema = json.loads((ROOT / 'secrets/schema.json').read_text())
        validator = jsonschema.Draft202012Validator(schema).evolve(schema=schema['$defs']['device_operation_record'])
        if next(validator.iter_errors(journal), None) is not None:
            raise ValueError('invalid-device-operation-journal')
        expected = revocation_intent(journal, self.manifest['id']) if self.action == 'revoke' else None
        if journal['revocation'] != expected:
            raise ValueError('device-revocation-intent-changed')
        hosts = set(self.nodes)
        grant_ids = {host + '/' + token for host, grants in journal['grants'].items() for token in grants}
        if (set(journal['before']) != hosts or set(journal['after']) != hosts
                or not set(journal['profiles']) <= hosts or not set(journal['grants']) <= {p['host'] for p in self.manifest['publishers']}
                or not set(journal['written']) <= hosts or not set(journal['adopted']) <= set(journal['written'])
                or not set(journal['published']) <= grant_ids or journal['action'] != self.action or journal['device'] != self.name
                or (journal['artifact'] is not None) != (self.action == 'issue' or self.native)
                or set(journal['canaries']) != ({pub['host'] for pub in self.manifest['publishers']} if self.action == 'revoke' else set())):
            raise ValueError('invalid-device-operation-journal')
        affected = self._runtime_hosts(journal)
        if ((journal['phase'] != 'prepared' and set(journal['written']) != hosts)
                or (journal['phase'] in ('runtime-adopted', 'complete') and set(journal['adopted']) != affected)
                or (journal['phase'] == 'complete' and set(journal['published']) != grant_ids)
                or (journal['written'] and not all(c['positive'] for c in journal['canaries'].values()))
                or (journal['phase'] == 'complete' and not all(c['cleaned'] for c in journal['canaries'].values()))):
            raise ValueError('incomplete-device-operation-evidence')

    def _runtime_hosts(self, journal):
        if self.action == 'revoke':
            return set(self.nodes)
        return {host for host in self.nodes if journal['before'][host] != fingerprint(journal['after'][host])} | set(journal['profiles'])

    def _fence(self, journal):
        if self.io.source_identity() != journal['source']:
            raise ValueError('device-source-changed')
        for host, doc in self.documents().items():
            expected = {fingerprint(journal['after'][host])} if host in journal['written'] else {journal['before'][host], fingerprint(journal['after'][host])}
            if fingerprint(doc) not in expected:
                raise ValueError('device-authority-changed-during-operation')
        snapshots = self.snapshots()
        for host, snapshot in snapshots.items():
            if snapshot['bootstrap']:
                raise ValueError('new-bootstrap-grant-during-device-operation')
            canary = journal['canaries'].get(host)
            current = {token: row for token, row in snapshot['rows'].items()
                       if envelope(un64(row['document_b64']))[0]['client'] == self.name
                       and not (canary is not None and token == sha(canary['token'].encode())
                                and row['document_b64'] == canary['document_b64'])}
            known = journal['grants'].get(host, {})
            for token, row in current.items():
                if token not in known:
                    if self.action == 'refresh' and (row['revoked'] or row['expired']):
                        continue
                    raise ValueError('new-device-grant-during-operation')
                if row['document_b64'] not in (known[token]['before'], known[token]['after']):
                    raise ValueError('device-grant-changed-during-operation')
                if self.action != 'revoke' and (row['revoked'] or row['expired']):
                    raise ValueError('device-grant-no-longer-active')
            for token, grant in known.items():
                if token not in current and grant['before'] is not None:
                    raise ValueError('device-grant-disappeared')
        return snapshots

    def _probe(self, host, profiles):
        if not profiles:
            raise ValueError('device-probe-coverage-empty')
        result = self.io.probe(host, profiles, 'deny' if self.action == 'revoke' else 'accept')
        if (not isinstance(result, dict) or result.get('control') != 'passed' or result.get('cleanup') != 'confirmed'
                or not isinstance(result.get('profiles'), list) or len(result['profiles']) != len(profiles)
                or {row.get('id') for row in result['profiles']} != {row['id'] for row in profiles}):
            raise ValueError('device-native-probe-incomplete')
        expected = 'denied' if self.action == 'revoke' else 'accepted'
        for row in result['profiles']:
            if row.get('state') != expected or any(row.get(key) is not True for key in ('control_ok', 'setup_ok', 'cleanup_ok')):
                raise ValueError('device-native-probe-incomplete')
            if self.action == 'revoke' and not (row.get('peer_absent') is True and (
                    row.get('runtime_healthy') is True or row.get('inactive_confirmed') is True)):
                raise ValueError('device-revocation-runtime-witness-incomplete')

    def run(self):
        journal = self._journal()
        self.io.verify_publisher_scope()
        self._fence(journal)
        for host, canary in journal['canaries'].items():
            if not canary['positive']:
                token_hash = sha(canary['token'].encode())
                document = un64(canary['document_b64'])
                self.io.publisher(host, 'publish', token_hash, None, document)
                self.io.read_route(host, canary['token'], un64(envelope(document)[0]['payload_b64']))
                canary['positive'] = True
                self._save(journal)
        for host, node in self.nodes.items():
            candidate = journal['after'][host]
            if host not in journal['written']:
                def transform(current, host=host, candidate=candidate):
                    expected = fingerprint(current)
                    if expected not in {journal['before'][host], fingerprint(candidate)}:
                        raise ValueError('device-authority-CAS-conflict')
                    return copy.deepcopy(candidate) | ({'device_operations': current['device_operations']} if 'device_operations' in current else {}), {}
                self.writer(node['secrets_file'], transform)
                journal['written'].append(host)
                self._save(journal)
            self._fence(journal)
        journal['phase'] = 'authority-written'
        self._save(journal)
        affected = self._runtime_hosts(journal)
        for host in sorted(affected):
            if host not in journal['adopted']:
                self.io.runtime(host, journal['after'][host], check=True, revocation=journal['revocation'])
                self._fence(journal)
                self.io.runtime(host, journal['after'][host], revocation=journal['revocation'])
                self._fence(journal)
                if host in journal['profiles']:
                    self._probe(host, journal['profiles'][host])
                journal['adopted'].append(host)
                self._save(journal)
        journal['phase'] = 'runtime-adopted'
        self._save(journal)
        for host, grants in journal['grants'].items():
            if self.action != 'revoke' and grants:
                self.io.verify_routes(host)
            for token, grant in grants.items():
                snapshots = self._fence(journal)
                row = snapshots[host]['rows'].get(token)
                if self.action == 'revoke':
                    if row is None or not row['revoked']:
                        raise ValueError('device-publisher-revocation-unconfirmed')
                elif row is None or row['document_b64'] != grant['after']:
                    response = self.io.publisher(host, 'publish', token, sha(un64(grant['before'])) if grant['before'] else None, un64(grant['after']))
                    if response.get('document_sha256') != sha(un64(grant['after'])):
                        raise ValueError('device-publication-acknowledgement-unconfirmed')
                key = host + '/' + token
                if key not in journal['published']:
                    journal['published'].append(key)
                    self._save(journal)
        if journal['artifact'] is not None:
            self.io.output(self.manifest['delivery']['output'], un64(journal['artifact']))
        # Every resumed completion rechecks current canonical runtime, including publishers.
        for host in sorted(affected):
            self.io.runtime(host, journal['after'][host], verify_only=True, revocation=journal['revocation'])
        # Recheck native credentials after publication; old accepted sessions never count.
        for host, profiles in journal['profiles'].items():
            self._probe(host, profiles)
        snapshots = self._fence(journal)
        for host, grants in journal['grants'].items():
            for token, grant in grants.items():
                row = snapshots[host]['rows'].get(token)
                if row is None or row['document_b64'] != grant['after'] or row['revoked'] != (self.action == 'revoke'):
                    raise ValueError('device-final-publication-unconfirmed')
        for host, canary in journal['canaries'].items():
            row = snapshots[host]['rows'].get(sha(canary['token'].encode()))
            if ((row is None and not canary['cleanup_started'])
                    or row is not None and (row['document_b64'] != canary['document_b64'] or not row['revoked'] or row['expired'])):
                raise ValueError('device-revocation-canary-authority-unconfirmed')
            self.io.verify_routes(host)
            self.io.read_route(host, canary['token'], b'', revoked=True)
            if not canary['cleaned']:
                canary['cleanup_started'] = True
                self._save(journal)
                result = self.io.publisher(host, 'publish', sha(canary['token'].encode()), sha(un64(canary['document_b64'])), None)
                if result.get('document_sha256') is not None:
                    raise ValueError('device-canary-cleanup-unconfirmed')
                canary['cleaned'] = True
                self._save(journal)
        self.io.verify_publisher_scope()
        final = self._fence(journal)
        if self.action == 'revoke':
            for host in journal['canaries']:
                hashes = set(journal['grants'].get(host, {}))
                if sha(journal['canaries'][host]['token'].encode()) in final[host]['rows']:
                    raise ValueError('device-canary-cleanup-unconfirmed')
                if any(not final[host]['rows'].get(token, {}).get('revoked', False) for token in hashes):
                    raise ValueError('device-final-revocation-changed')
        journal['phase'] = 'complete'
        self._save(journal)
        return self.status()

    def status(self):
        journal = self._journal()
        return {'operation_id': self.manifest['id'], 'action': self.action, 'device': self.name, 'phase': journal['phase'],
                'nodes_written': len(journal['written']), 'nodes_adopted': len(journal['adopted']),
                'native_credential_profiles': sum(len(rows) for rows in journal['profiles'].values()),
                'grants_confirmed': len(journal['published']), 'recipient_artifact': journal['artifact'] is not None and journal['phase'] == 'complete'}
