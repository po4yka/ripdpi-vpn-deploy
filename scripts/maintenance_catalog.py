"""Catalog selection and compare-and-swap publication of accepted core state."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from operator_maintenance_io import (MaintenanceError, read_bytes, private_directory,
                                    update_document, write_document)
from recovery_io import document, digest, unique

CORE_FIELDS = ('core_source_revision', 'core_deployable_digest', 'current_core_verified_at',
               'current_operation_receipt', 'current_operation_receipt_sha256')


def core_state(catalog, host):
    records = catalog.get('current_actual_configuration', {})
    if not isinstance(records, dict) or not isinstance(records.get(host, {}), dict):
        raise MaintenanceError('invalid-current-core-state')
    return {key: records.get(host, {})[key] for key in CORE_FIELDS if key in records.get(host, {})}


def baseline(catalog_path, nodes):
    catalog = document(catalog_path)
    return {node['host']: core_state(catalog, node['host']) for node in nodes}


def require_baseline(plan, nodes):
    catalog = document(Path(plan['catalog']))
    for node in nodes:
        if core_state(catalog, node['host']) != plan['catalog_baseline'][node['host']]:
            raise MaintenanceError('catalog-core-conflict')


def generate(request_path, output, fleet):
    request = document(request_path)
    if (set(request) != {'schema_version', 'catalog', 'id', 'expires_at', 'state_directory',
                         'runtime_parent', 'nodes'} or type(request['schema_version']) is not int
            or request['schema_version'] != 1):
        raise MaintenanceError('invalid-generation-request')
    fleet.deadline(request)
    catalog_path = Path(fleet.absolute(request['catalog']))
    catalog = document(catalog_path)
    mapping = catalog['maintenance']
    if set(mapping) != {'defaults', 'nodes'}:
        raise MaintenanceError('invalid-maintenance-mapping')
    defaults = mapping['defaults']
    if set(defaults) != {'age_identity', 'log_recipient', 'liveness_config', 'liveness_inputs'}:
        raise MaintenanceError('invalid-maintenance-defaults')
    names = request['nodes']
    if (not isinstance(names, list) or not 1 <= len(names) <= 10
            or any(not isinstance(name, str) for name in names) or len(set(names)) != len(names)):
        raise MaintenanceError('invalid-node-selection')

    def path(value):
        fleet.literal(value)
        result = fleet.absolute(str(catalog_path.parent / value))
        read_bytes(result)
        return result

    value = {key: request[key] for key in ('id', 'expires_at', 'state_directory', 'runtime_parent')}
    value.update(schema_version=2, catalog=str(catalog_path), **defaults)
    for key in ('state_directory', 'runtime_parent'):
        private_directory(fleet.absolute(value[key]))
    for key in ('age_identity', 'liveness_config'):
        value[key] = path(value[key])
    if not isinstance(value['liveness_inputs'], list):
        raise MaintenanceError('invalid-liveness-inputs')
    value['liveness_inputs'] = [path(item) for item in value['liveness_inputs']]
    value['nodes'] = []
    for name in names:
        node = dict(mapping['nodes'][name])
        if (node.get('host') != name or not fleet.NODE_FIELDS <= node.keys()
                or node.keys() - fleet.NODE_FIELDS - fleet.OPTIONAL
                or not isinstance(node['inputs'], list)):
            raise MaintenanceError('invalid-node-mapping')
        for key in fleet.PATH_ENV.keys() & node.keys():
            node[key] = path(node[key])
        node['inputs'] = [path(item) for item in node['inputs']]
        # Verify the same discovered dependencies as prepare without contacting hosts.
        inputs, trees = {}, {}
        fleet.known_dependencies(node, inputs, trees)
        for item in inputs:
            read_bytes(item)
        value['nodes'].append(node)
    fleet.validate_configuration(value)
    write_document(output, value)
    return {'phase': 'generated', 'nodes': names, 'deployment_authorized': False}


def reconcile(plan, node, receipt_path, receipt_sha256):
    raw = read_bytes(receipt_path)
    if hashlib.sha256(raw).hexdigest() != receipt_sha256:
        raise MaintenanceError('acceptance-receipt-changed')
    receipt = json.loads(raw, object_pairs_hook=unique)
    if (receipt.get('plan_sha256') != digest(plan) or receipt.get('host') != node['host']
            or receipt.get('source') != plan['source'] or receipt.get('cleanup') != 'absent'
            or receipt.get('accepted') is not True):
        raise MaintenanceError('invalid-acceptance-receipt')
    path = Path(plan['catalog'])
    raw_catalog = read_bytes(path)
    catalog = json.loads(raw_catalog, object_pairs_hook=unique)
    reference = Path(receipt_path)
    if reference.is_relative_to(path.parent):
        reference = reference.relative_to(path.parent)
    wanted = dict(zip(CORE_FIELDS, (plan['source']['revision'], plan['source']['deployable_digest'],
                                   receipt['at'], str(reference), receipt_sha256)))
    current = core_state(catalog, node['host'])
    if current == wanted:
        return
    if current != plan['catalog_baseline'][node['host']]:
        raise MaintenanceError('catalog-core-conflict')
    catalog.setdefault('current_actual_configuration', {}).setdefault(node['host'], {}).update(wanted)
    update_document(path, hashlib.sha256(raw_catalog).hexdigest(), catalog)
