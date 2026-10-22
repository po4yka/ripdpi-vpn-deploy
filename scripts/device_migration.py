"""Resumable encrypted device migration, exact publication and offline evidence."""
from __future__ import annotations

import base64
import copy
import json
import secrets
import time
import uuid

from bootstrap_readiness import check_cancelled
from client_delivery_identity import authority, comparable, digest
from client_payload import ROOT, materialize, validate_options
from device_migration_credentials import prepare_credentials
from device_migration_errors import MigrationRefused
from device_migration_io import encoded, sha
from device_migration_receipt import (
    HEX,
    decode,
    matches,
    metadata,
    path_is_current,
    verify,
)
from encrypted_client_document import MAX_BYTES, operate

DELIVERY_FIELDS = ('status', 'formats', 'hosts', 'cohorts', 'token_hash_prefix', 'token_expires',
                   'awg_delivery_host', 'delivery_sources', 'delivery_options', 'last_payload_identity', 'migration_delivery')


def fingerprint(document):
    return sha(encoded({k: v for k, v in document.items() if k != 'device_migrations'}))


def un64(value):
    return base64.b64decode(value, validate=True)


def envelope(raw):
    from device_migration_receipt import unique_object
    value = json.loads(raw, object_pairs_hook=unique_object)
    if (not isinstance(value, dict) or set(value) != {'schema_version', 'client', 'expires', 'payload_b64'}
            or value['schema_version'] != 1 or not isinstance(value['client'], str)
            or not isinstance(value['expires'], str) or not isinstance(value['payload_b64'], str)):
        raise MigrationRefused('invalid-migration-document')
    payload = json.loads(un64(value['payload_b64']), object_pairs_hook=unique_object)
    if not isinstance(payload, dict):
        raise MigrationRefused('invalid-migration-payload')
    return value, payload


def wrap_payload(payload, proof):
    """Reproduce the exact published metadata and opaque AWG tag for drift."""
    proof = metadata(proof)
    result = copy.deepcopy(payload)
    extension = result.get('ripdpi')
    if not isinstance(extension, dict):
        raise MigrationRefused('migration-requires-ripdpi-bundle')
    for target in proof['awg_previous_tags']:
        selected = extension.get('amneziawg', [])
        if len(selected) != 1:
            raise MigrationRefused('migration-awg-tag-changed')
        selected[0]['tag'] = target
    extension['migration'] = copy.deepcopy(proof)
    return result


def merge_delivery(entry, delivery):
    result = copy.deepcopy(entry)
    for field in DELIVERY_FIELDS:
        result.pop(field, None)
        if field in delivery:
            result[field] = copy.deepcopy(delivery[field])
    return result


class Migration:
    def __init__(self, plan, io, *, writer=operate, now=None):
        self.plan, self.io, self.writer = plan, io, writer
        self.now = now or (lambda: int(time.time() * 1000))
        self.source_path, self.target_path = (plan[key]['secrets_file'] for key in ('source', 'target'))
        self.publishers = list(dict.fromkeys([plan['publication']['source_alias'], plan['publication']['target_alias']]))

    def read(self):
        return self.io.read(self.source_path), self.io.read(self.target_path)

    def snapshots(self, *, source_only=False):
        snapshots = {}
        for alias in self.publishers[:1] if source_only else self.publishers:
            self.io.publisher(alias, 'ready')
            self.io.origin(alias)
            value = self.io.publisher(alias, 'snapshot')
            if (not isinstance(value, dict) or set(value) != {'schema_version', 'documents', 'active_bootstrap_count'}
                    or value['schema_version'] != 1 or not isinstance(value['documents'], list)
                    or len(value['documents']) > 256 or type(value['active_bootstrap_count']) is not int
                    or value['active_bootstrap_count'] < 0):
                raise MigrationRefused('invalid-migration-snapshot')
            rows = {}
            total = 0
            for row in value['documents']:
                if (not isinstance(row, dict) or set(row) != {'token_hash', 'document_sha256', 'document_b64', 'revoked', 'expired'}
                        or not matches(HEX, row['token_hash']) or not matches(HEX, row['document_sha256'])
                        or type(row['revoked']) is not bool or type(row['expired']) is not bool
                        or row['token_hash'] in rows):
                    raise MigrationRefused('invalid-migration-snapshot-row')
                content = un64(row['document_b64'])
                total += len(content)
                if total > 2 * 1024 * 1024 or sha(content) != row['document_sha256']:
                    raise MigrationRefused('invalid-migration-snapshot-content')
                envelope(content)
                rows[row['token_hash']] = row
            snapshots[alias] = {'rows': rows, 'bootstrap': value['active_bootstrap_count']}
        if len(self.publishers) > 1 and snapshots[self.publishers[0]]['bootstrap']:
            raise MigrationRefused('drain-active-bootstrap-grants-before-migration')
        return snapshots

    def inspect(self):
        source, target = self.read()
        if any(v.get('phase') != 'rolled-back' for v in source.get('device_migrations', {}).values()):
            raise MigrationRefused('migration-already-prepared-use-status-or-resume')
        # Green has not been converged yet. Only source publication authority
        # exists at preparation; target CAS admission happens after its gates.
        snapshots = self.snapshots(source_only=True)
        source_rows = snapshots[self.publishers[0]]['rows']
        active = {key: row for key, row in source_rows.items() if not row['revoked'] and not row['expired']}
        selected, excluded = [], []
        registry = source.get('client_registry', {})
        for name, entry in sorted(registry.items()):
            if self.plan['source']['host'] not in entry.get('hosts', []):
                continue
            grants = [key for key, row in active.items() if envelope(un64(row['document_b64']))[0]['client'] == name]
            if entry.get('status') in ('revoked', 'burned') or not grants:
                if grants:
                    raise MigrationRefused('revoked-device-has-active-migration-grant')
                if entry.get('status') in ('delivered', 'active', 'stale') and not any(
                    envelope(un64(row['document_b64']))[0]['client'] == name and (row['revoked'] or row['expired']) for row in source_rows.values()):
                    raise MigrationRefused('delivered-device-has-no-discoverable-grant')
                excluded.append({'client': name, 'reason': 'inactive-or-unissued'})
                continue
            validate_options(entry.get('delivery_options'))
            if not comparable(entry.get('last_payload_identity'), authority(source)):
                raise MigrationRefused('migration-delivery-identity-unavailable-reissue-required')
            if not entry.get('delivery_sources') or len(entry['delivery_sources']) != len(entry['hosts']):
                raise MigrationRefused('migration-delivery-sources-unavailable')
            if sum(key.startswith(entry.get('token_hash_prefix', '')) for key in grants) != 1:
                raise MigrationRefused('migration-canonical-grant-ambiguous')
            selected.append(name)
        candidate = prepare_credentials(source, target, selected, self.plan['source'], self.plan['target']) if selected else copy.deepcopy(target)
        additional_sources, endpoints = {}, {}
        for name in selected:
            entry = registry[name]
            for host, path in zip(entry['hosts'], entry['delivery_sources'], strict=True):
                endpoints[host] = self.io.endpoint(host)
                if path not in (self.source_path, self.target_path):
                    additional_sources[path] = fingerprint(self.io.read(path))
        endpoints[self.plan['target']['host']] = self.io.endpoint(self.plan['target']['host'])
        # Do not hide an unregistered profile still pointing at the retiring node.
        old_ip = self.io.endpoint(self.plan['source']['host'])
        for row in active.values():
            grant, payload = envelope(un64(row['document_b64']))
            if grant['client'] not in selected and old_ip in encoded(payload).decode():
                raise MigrationRefused('untracked-profile-still-uses-source')
        inputs = {'plan': self.plan, 'admission': self.io.admission, 'source': fingerprint(source),
                  'target': fingerprint(target), 'candidate': fingerprint(candidate), 'snapshots': snapshots,
                  'additional_sources': additional_sources, 'endpoints': endpoints}
        review = {'migration_id': self.plan['id'], 'devices': selected, 'excluded': excluded,
                  'active_grants': sum(envelope(un64(r['document_b64']))[0]['client'] in selected for r in active.values()),
                  'preserved_other_grants': sum(envelope(un64(r['document_b64']))[0]['client'] not in selected for r in active.values()),
                  'publisher_move': len(self.publishers) > 1, 'normalize_to_registry_selection': True,
                  'approval': sha(encoded(inputs))}
        return source, target, candidate, snapshots, inputs, review

    def save(self, source, journal):
        check_cancelled()
        expected = copy.deepcopy(source)
        def change(current):
            if current != expected:
                raise MigrationRefused('migration-source-changed')
            current.setdefault('device_migrations', {})[self.plan['id']] = copy.deepcopy(journal)
            # SOPS per-field overhead is large; bound before cross-document mutation.
            if len(encoded(current)) > MAX_BYTES // 4:
                raise MigrationRefused('migration-journal-capacity-exceeded')
            return current, None
        self.writer(self.source_path, change)
        source.setdefault('device_migrations', {})[self.plan['id']] = copy.deepcopy(journal)

    def replace_target(self, expected, desired):
        check_cancelled()
        def change(current):
            if current == desired:
                return current, None
            if current != expected:
                raise MigrationRefused('migration-target-changed')
            return copy.deepcopy(desired), None
        self.writer(self.target_path, change)

    def prepare(self, approval):
        source, target = self.read()
        if self.plan['id'] in source.get('device_migrations', {}):
            journal = self.load(source)
            if approval != journal['approval']:
                raise MigrationRefused('migration-approval-mismatch')
            if journal['phase'] in ('rolling-back', 'rolled-back'):
                raise MigrationRefused('migration-cannot-resume-after-rollback')
            if journal['phase'] != 'preparing':
                self.check_inputs(source, target, journal)
                return self.status(source, journal)
        else:
            source, target, candidate, snapshots, inputs, review = self.inspect()
            if approval != review['approval']:
                raise MigrationRefused('migration-review-required')
            journal = {'schema_version': 1, 'plan': copy.deepcopy(self.plan), 'admission': self.io.admission,
                       'approval': approval, 'phase': 'preparing', 'source_before': fingerprint(source),
                       'target_before': fingerprint(target), 'target_candidate': candidate,
                       'additional_sources': inputs['additional_sources'], 'endpoints': inputs['endpoints'],
                       'devices': review['devices'], 'excluded': review['excluded'], 'grants': {}, 'receipts': {}, 'attestations': {}}
            for token, row in snapshots[self.publishers[0]]['rows'].items():
                if row['expired'] or row['revoked']:
                    continue
                grant, old_payload = envelope(un64(row['document_b64']))
                name = grant['client']
                if name not in journal['devices'] and len(self.publishers) == 1:
                    continue
                entry = {'client': name, 'old': row['document_b64'], 'new': row['document_b64'], 'before': {}, 'metadata': None}
                if name in journal['devices']:
                    original = source['client_registry'][name]
                    options = copy.deepcopy(original['delivery_options'])
                    index = options['hosts'].index(self.plan['source']['host'])
                    options['hosts'][index] = self.plan['target']['host']
                    if not options['cohorts']:
                        raise MigrationRefused('explicit-migration-cohorts-required')
                    options['cohorts'][index] = self.plan['target']['cohort']
                    if options['awg_host'] == self.plan['source']['host']:
                        options['awg_host'] = self.plan['target']['host']
                    options['expires'] = grant['expires']
                    if any('protocol' in v for v in old_payload.get('outbounds', [])):
                        raise MigrationRefused('unsupported-migration-subscription-format')
                    options['format'] = 'ripdpi' if 'ripdpi' in old_payload else 'singbox'
                    sources = list(original['delivery_sources'])
                    if sources[index] != self.source_path:
                        raise MigrationRefused('migration-source-path-mismatch')
                    sources[index] = self.target_path
                    documents = {self.target_path: candidate, self.source_path: source}
                    for path, expected in journal['additional_sources'].items():
                        documents[path] = self.io.read(path)
                        if fingerprint(documents[path]) != expected:
                            raise MigrationRefused('migration-additional-source-changed')
                    payload, bindings = materialize(name, options, documents=documents, source_paths=sources, private_only=True,
                                                    extended=options['format'] == 'ripdpi', endpoints=journal['endpoints'])
                    if options['format'] == 'ripdpi':
                        delivery_id = str(uuid.uuid4())
                        suffix = '-'.join(self.plan['target']['host'].split(':'))
                        tags = [v['tag'] for v in payload['outbounds'] if v.get('type') in ('vless', 'hysteria2', 'snell')
                                and v.get('server') == self.io.endpoint(self.plan['target']['host'])
                                and (v['tag'].endswith('-' + suffix) or '-' + suffix + '-' in v['tag'] or v['tag'].endswith('-' + suffix + ':alternate'))]
                        previous = {}
                        if options['awg_host'] in ('', self.plan['target']['host']):
                            for _awg in payload['ripdpi']['amneziawg']:
                                tag = 'migration-awg-' + delivery_id
                                prior = old_payload.get('ripdpi', {}).get('amneziawg', [])
                                if len(prior) != 1:
                                    raise MigrationRefused('migration-prior-awg-profile-unavailable')
                                previous[tag] = prior[0]['tag']
                                tags.append(tag)
                        proof = {'schema_version': 1, 'migration_id': self.plan['id'], 'delivery_id': delivery_id,
                                 'receipt_key': secrets.token_hex(32), 'target_tags': tags, 'awg_previous_tags': previous}
                        payload = wrap_payload(payload, proof)
                        import jsonschema
                        validator = jsonschema.Draft202012Validator(json.loads((ROOT / 'contract/ripdpi-bundle.schema.json').read_text()))
                        if not validator.is_valid(payload['ripdpi']):
                            raise MigrationRefused('invalid-migration-rendered-bundle')
                        entry['metadata'] = proof
                    raw = encoded(payload)
                    entry.update(new=base64.b64encode(encoded(dict(grant, payload_b64=base64.b64encode(raw).decode()))).decode(),
                                 options=options, sources=sources, bindings=bindings, payload_sha256=sha(raw))
                for alias in snapshots:
                    existing = snapshots[alias]['rows'].get(token)
                    if existing and (existing['revoked'] or existing['expired'] or existing['document_b64'] != row['document_b64']):
                        raise MigrationRefused('migration-target-grant-conflict')
                    entry['before'][alias] = existing['document_b64'] if existing else None
                journal['grants'][token] = entry
            self.save(source, journal)
        if fingerprint(source) != journal['source_before']:
            raise MigrationRefused('migration-source-changed')
        candidate = journal['target_candidate']
        if fingerprint(target) not in (journal['target_before'], fingerprint(candidate)):
            raise MigrationRefused('migration-target-changed')
        self.check_inputs(source, candidate, journal)
        self.replace_target(target, candidate)
        journal['phase'] = 'prepared'
        self.save(source, journal)
        return self.status(source, journal)

    def load(self, source):
        journal = copy.deepcopy(source.get('device_migrations', {}).get(self.plan['id']))
        if (not isinstance(journal, dict) or journal.get('schema_version') != 1
                or journal.get('plan') != self.plan or journal.get('admission') != self.io.admission):
            raise MigrationRefused('migration-plan-or-admission-changed')
        return journal

    def check_inputs(self, source, target, journal):
        for path, expected in journal['additional_sources'].items():
            if fingerprint(self.io.read(path)) != expected:
                raise MigrationRefused('migration-additional-source-changed')
        if any(self.io.endpoint(host) != address for host, address in journal['endpoints'].items()):
            raise MigrationRefused('migration-endpoint-changed')
        if fingerprint(source) not in {journal['source_before'], journal.get('source_after', ''), journal.get('source_rollback', '')}:
            raise MigrationRefused('migration-source-changed')
        if fingerprint(target) not in {fingerprint(journal['target_candidate']), journal.get('target_after', ''), journal.get('target_rollback', '')}:
            raise MigrationRefused('migration-target-changed')

    def reconcile(self, journal, *, rollback=False, exact=False):
        snapshots = self.snapshots()
        # Refuse newly issued affected grants instead of quietly missing URLs.
        for alias in self.publishers:
            for token, row in snapshots[alias]['rows'].items():
                if not row['expired'] and not row['revoked'] and token not in journal['grants']:
                    name = envelope(un64(row['document_b64']))[0]['client']
                    if name in journal['devices'] or len(self.publishers) > 1 and alias == self.publishers[0]:
                        raise MigrationRefused('migration-grant-set-changed')
        for token, entry in journal['grants'].items():
            expiry = envelope(un64(entry['old']))[0]['expires']
            if expiry:
                from datetime import datetime
                instant = datetime.fromisoformat(expiry)
                if instant.tzinfo is None or int(instant.timestamp() * 1000) <= self.now():
                    raise MigrationRefused('migration-grant-no-longer-active')
            for alias in self.publishers:
                row = snapshots[alias]['rows'].get(token)
                before, after = entry['before'][alias], entry['new']
                wanted = before if rollback else after
                allowed = after if rollback else before
                if row and (row['revoked'] or row['expired']):
                    raise MigrationRefused('migration-grant-no-longer-active')
                actual = row['document_b64'] if row else None
                if actual != wanted and (exact or actual != allowed):
                    raise MigrationRefused('migration-publication-conflict')
                if not exact:
                    expected = sha(un64(allowed)) if allowed is not None else None
                    result = self.io.publisher(alias, 'publish', token, expected, un64(wanted) if wanted is not None else None)
                    if (result.get('schema_version') != 1 or result.get('token_hash') != token
                            or result.get('document_sha256') != (sha(un64(wanted)) if wanted is not None else None)
                            or result.get('result') not in ('applied', 'already-applied')):
                        raise MigrationRefused('migration-publication-acknowledgement-uncertain')

    def delivered_documents(self, source, target, journal):
        result_source, result_target = copy.deepcopy(source), copy.deepcopy(target)
        for name in journal['devices']:
            original = source['client_registry'][name]
            choices = [(key, value) for key, value in journal['grants'].items() if value['client'] == name and key.startswith(original['token_hash_prefix'])]
            if len(choices) != 1:
                raise MigrationRefused('migration-canonical-grant-changed')
            token, grant = choices[0]
            options = grant['options']
            payload = envelope(un64(grant['new']))[1]
            for document in (result_source, result_target):
                delivery = {'status': 'delivered', 'formats': [options['format']], 'hosts': options['hosts'], 'cohorts': options['cohorts'],
                            'token_hash_prefix': token[:8], 'token_expires': options['expires'], 'awg_delivery_host': options['awg_host'],
                            'delivery_options': options, 'delivery_sources': grant['sources'],
                            'last_payload_identity': digest(name, options, payload, grant['bindings'], authority(document, create=True))}
                if grant['metadata']:
                    delivery['migration_delivery'] = grant['metadata']
                document['client_registry'][name] = merge_delivery(document['client_registry'][name], delivery)
        return result_source, result_target

    def publish(self):
        source, target = self.read()
        journal = self.load(source)
        if journal['phase'] not in ('prepared', 'publishing', 'published'):
            raise MigrationRefused('migration-not-prepared')
        self.check_inputs(source, target, journal)
        self.io.verify_target(target)
        self.io.verify_routes()
        source, target = self.read()
        journal = self.load(source)
        self.check_inputs(source, target, journal)
        if journal['phase'] == 'prepared':
            snapshots = self.snapshots()
            for token, grant in journal['grants'].items():
                for alias in self.publishers:
                    if alias in grant['before']:
                        continue
                    row = snapshots[alias]['rows'].get(token)
                    if row and (row['expired'] or row['revoked'] or row['document_b64'] != grant['old']):
                        raise MigrationRefused('migration-target-grant-conflict')
                    grant['before'][alias] = row['document_b64'] if row else None
            final_source, final_target = self.delivered_documents(source, target, journal)
            journal.update(phase='publishing', published_at_ms=self.now(), source_after=fingerprint(final_source), target_after=fingerprint(final_target),
                           source_delivery={name: final_source['client_registry'][name] for name in journal['devices']},
                           source_registry_before={name: source['client_registry'][name] for name in journal['devices']},
                           target_delivery={name: final_target['client_registry'][name] for name in journal['devices']},
                           target_identity=final_target.get('client_delivery_identity'), source_identity=final_source.get('client_delivery_identity'))
            self.save(source, journal)
        self.reconcile(journal)
        self.reconcile(journal, exact=True)
        # The encrypted intent fences both halves across a crash between commits.
        desired_target = copy.deepcopy(target)
        desired_target['client_registry'].update(copy.deepcopy(journal['target_delivery']))
        if journal['target_identity'] is not None:
            desired_target['client_delivery_identity'] = journal['target_identity']
        if fingerprint(desired_target) != journal['target_after']:
            raise MigrationRefused('migration-target-delivery-changed')
        self.replace_target(target, desired_target)
        def commit(current):
            if current != source:
                raise MigrationRefused('migration-source-changed')
            current['client_registry'].update(copy.deepcopy(journal['source_delivery']))
            if journal['source_identity'] is not None:
                current['client_delivery_identity'] = journal['source_identity']
            if fingerprint(current) != journal['source_after']:
                raise MigrationRefused('migration-source-delivery-changed')
            journal['phase'] = 'published'
            current['device_migrations'][self.plan['id']] = journal
            return current, None
        self.writer(self.source_path, commit)
        return self.status(None, journal)

    def evidence(self, content=None, *, client=None, reason=None):
        source, target = self.read()
        journal = self.load(source)
        self.check_inputs(source, target, journal)
        if journal['phase'] != 'published':
            raise MigrationRefused('migration-not-published')
        self.reconcile(journal, exact=True)
        if content is not None:
            receipt = decode(content)
            choices = [g for g in journal['grants'].values() if g['metadata'] and g['metadata']['delivery_id'] == receipt['delivery_id']]
            if len(choices) != 1:
                raise MigrationRefused('migration-receipt-delivery-unavailable')
            grant = choices[0]
            verified = verify(receipt, dict(grant, published_at_ms=journal['published_at_ms']), now_ms=self.now())
            old = journal['receipts'].get(receipt['delivery_id'])
            if old and (old['tested_at_ms'] > verified['tested_at_ms'] or old['received_at_ms'] > verified['received_at_ms']):
                raise MigrationRefused('migration-evidence-downgrade')
            journal['receipts'][receipt['delivery_id']] = verified
        else:
            if (client not in journal['devices'] or not isinstance(reason, str) or not 8 <= len(reason) <= 500
                    or any(ord(c) < 32 for c in reason)):
                raise MigrationRefused('explicit-device-path-attestation-required')
            if any(g['client'] == client and g['metadata'] for g in journal['grants'].values()):
                raise MigrationRefused('ripdpi-device-requires-authenticated-receipt')
            journal['attestations'][client] = {'tested_at_ms': self.now(), 'reason': reason, 'approval': journal['approval']}
        self.save(source, journal)
        return self.status(None, journal)

    def status(self, source=None, journal=None):
        if journal is None:
            source, _ = self.read()
            journal = self.load(source)
        devices = []
        for name in journal['devices']:
            grants = [g for g in journal['grants'].values() if g['client'] == name]
            receipts = [journal['receipts'].get(g['metadata']['delivery_id']) for g in grants if g['metadata']]
            state = 'published' if journal['phase'] == 'published' else journal['phase']
            if any(r and path_is_current(r, now_ms=self.now()) for r in receipts):
                state = 'path-tested'
            elif any(receipts):
                state = 'received'
            attestation = journal['attestations'].get(name)
            if attestation and 0 <= self.now() - attestation['tested_at_ms'] <= 86400000:
                state = 'operator-confirmed'
            devices.append({'client': name, 'state': state, 'grants': len(grants)})
        return {'migration_id': self.plan['id'], 'phase': journal['phase'], 'devices': devices, 'excluded': journal['excluded']}

    def ready(self):
        source, target = self.read()
        journal = self.load(source)
        self.check_inputs(source, target, journal)
        if journal['phase'] != 'published':
            raise MigrationRefused('migration-not-published')
        self.io.pivot_ready()
        self.io.verify_target(target)
        self.io.verify_routes()
        source, target = self.read()
        journal = self.load(source)
        self.check_inputs(source, target, journal)
        self.reconcile(journal, exact=True)
        self.io.pivot_ready()
        report = self.status(None, journal)
        if any(device['state'] not in ('path-tested', 'operator-confirmed') for device in report['devices']):
            raise MigrationRefused('migration-device-path-evidence-incomplete')
        report['ready'] = True
        return report

    def rollback(self):
        source, target = self.read()
        journal = self.load(source)
        if journal['phase'] == 'rolled-back':
            return self.status(None, journal)
        self.check_inputs(source, target, journal)
        if journal['phase'] not in ('prepared', 'publishing', 'published', 'rolling-back'):
            raise MigrationRefused('migration-cannot-rollback')
        if journal['phase'] == 'prepared':
            journal['phase'] = 'rolled-back'
            self.save(source, journal)
            return self.status(None, journal)
        desired_target = copy.deepcopy(journal['target_candidate'])
        # Retain the committed target delivery authority key, which is unrelated
        # to peer removal and may already have been consumed by other tooling.
        if 'client_delivery_identity' in target:
            desired_target['client_delivery_identity'] = target['client_delivery_identity']
        desired_source = copy.deepcopy(source)
        desired_source['client_registry'].update(copy.deepcopy(journal.get('source_registry_before', {})))
        journal.update(phase='rolling-back', source_rollback=fingerprint(desired_source), target_rollback=fingerprint(desired_target))
        self.save(source, journal)
        self.reconcile(journal, rollback=True)
        self.reconcile(journal, rollback=True, exact=True)
        self.replace_target(target, desired_target)
        def commit(current):
            if current != source:
                raise MigrationRefused('migration-source-changed')
            current['client_registry'].update(copy.deepcopy(journal.get('source_registry_before', {})))
            journal.update(phase='rolled-back', receipts={}, attestations={})
            current['device_migrations'][self.plan['id']] = journal
            return current, None
        self.writer(self.source_path, commit)
        return self.status(None, journal)
