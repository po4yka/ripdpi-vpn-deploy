"""Independent regression boundaries; local adapters do not establish live acceptance."""
from __future__ import annotations

import base64
import copy
import hashlib
import json
import os
from pathlib import Path

import pytest
from device_migration import envelope, un64
from device_migration_io import encoded, load_plan
from encrypted_client_document import operate
from test_device_migration import migration as migration  # noqa: PLC0414
from test_device_migration import prepare, signed_receipt
from test_device_migration_credentials import authorities as authorities  # noqa: PLC0414
from test_device_migration_io import plan as plan  # noqa: PLC0414
from test_subscription_document import service as service  # noqa: PLC0414


@pytest.mark.parametrize('alias', ['dot', 'double-slash', 'parent-symlink', 'hardlink'])
def test_same_physical_authorities_refuse_before_any_private_write(plan, alias):
    document, plan_path = plan
    source = Path(document['source']['secrets_file'])
    target = Path(document['target']['secrets_file'])
    originals = {path: path.read_bytes() for path in (source, target)}
    changed = copy.deepcopy(document)
    if alias == 'dot':
        alternate = str(source.parent) + '/./' + source.name
    elif alias == 'double-slash':
        alternate = str(source.parent) + '//' + source.name
    elif alias == 'parent-symlink':
        link = source.parent / 'authority-link'
        link.symlink_to(source.parent, target_is_directory=True)
        alternate = str(link / source.name)
    else:
        link = source.parent / 'authority-hardlink.yaml'
        os.link(source, link)
        alternate = str(link)
    changed['target']['secrets_file'] = alternate
    plan_path.write_bytes(encoded(changed))
    reviewed_plan = plan_path.read_bytes()

    with pytest.raises(ValueError, match='distinct-migration-authorities|unsafe-private-document'):
        load_plan(plan_path)

    assert plan_path.read_bytes() == reviewed_plan
    assert all(path.read_bytes() == raw for path, raw in originals.items())
    assert not list(source.parent.glob('*.migration.lock'))
    assert not list(source.parent.glob('.*.client.*'))


def test_distinct_authorities_keep_canonical_identity_after_parent_alias(plan):
    document, plan_path = plan
    source = Path(document['source']['secrets_file'])
    document['source']['secrets_file'] = str(source.parent) + '/./' + source.name
    plan_path.write_text(json.dumps(document))
    admitted = load_plan(plan_path)
    assert admitted['source']['secrets_file'] == str(source.parent.resolve() / source.name)
    assert admitted['source']['secrets_file'] != admitted['target']['secrets_file']


@pytest.mark.parametrize('change', ['source-authority', 'target-authority', 'new-grant', 'replaced-grant', 'revoked-grant', 'origin-pivot'])
def test_ready_rechecks_mutations_during_long_target_verification(migration, monkeypatch, change):
    instance, token, get = migration
    prepare(migration)
    instance.publish()
    instance.evidence(signed_receipt(instance, token))
    assert instance.ready()['ready'] is True
    source_before = Path(instance.source_path).read_bytes()
    target_before = Path(instance.target_path).read_bytes()
    published = get()
    mutations = []
    origin_points_to_target = True

    def check_pivot():
        if not origin_points_to_target:
            raise ValueError('migration-publication-origin-pivot-unconfirmed')

    monkeypatch.setattr(instance.io, 'pivot_ready', check_pivot)

    def mutate_during_verify(_document):
        nonlocal origin_points_to_target
        mutations.append(change)
        if change == 'origin-pivot':
            origin_points_to_target = False
        elif change in ('source-authority', 'target-authority'):
            path = instance.source_path if change == 'source-authority' else instance.target_path

            def mutate(current):
                current['xray']['reality_public_key'] = 'concurrent-authority-change'
                return current, None

            operate(path, mutate)
        else:
            snapshot = instance.io.service._migration_snapshot()
            row = next(row for row in snapshot['documents'] if row['token_hash'] == token)
            grant, _ = envelope(un64(row['document_b64']))
            if change == 'new-grant':
                new_token = hashlib.sha256(b'independent-review-new-grant').hexdigest()
                instance.io.service._publish_subscription(new_token, un64(row['document_b64']))
            elif change == 'replaced-grant':
                replacement = dict(grant, payload_b64=base64.b64encode(b'{"concurrent":true}').decode())
                instance.io.service._publish_subscription(token, encoded(replacement))
            else:
                instance.io.service.REVOKED_FILE.write_text(token + '\n')

    monkeypatch.setattr(instance.io, 'verify_target', mutate_during_verify)
    category = {
        'source-authority': 'source-changed',
        'target-authority': 'target-changed',
        'new-grant': 'grant-set-changed',
        'replaced-grant': 'publication-conflict',
        'revoked-grant': 'grant-no-longer-active',
        'origin-pivot': 'origin-pivot-unconfirmed',
    }[change]
    with pytest.raises(ValueError, match=category):
        instance.ready()

    assert mutations == [change]
    if change != 'source-authority':
        assert Path(instance.source_path).read_bytes() == source_before
    if change != 'target-authority':
        assert Path(instance.target_path).read_bytes() == target_before
    if change == 'replaced-grant':
        assert get()[1] == b'{"concurrent":true}'
    elif change == 'revoked-grant':
        assert get()[0] == 410
    else:
        assert get() == published
