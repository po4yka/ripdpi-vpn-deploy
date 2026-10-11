"""Synthetic protected configurations for wrapper and publication unit tests."""
import json


def guarded_xray_config(marker='fixture'):
    return {
        'outbounds': [
            {'tag': 'direct', 'protocol': 'socks', 'settings': {'servers': [{'address': '127.0.0.1', 'port': 12080, 'users': [{'user': 'normalizer-direct-xray', 'pass': 'synthetic-'+marker+'-authority-00000000000000000000'}]}]}},
            {'tag': 'block', 'protocol': 'blackhole', 'settings': {'response': {'type': 'none'}}},
        ],
        'routing': {'domainStrategy': 'AsIs', 'rules': [{'type': 'field', 'network': 'tcp,udp', 'outboundTag': 'direct'}]},
    }


def guarded_xray_bytes(marker='fixture'):
    return json.dumps(guarded_xray_config(marker), separators=(',', ':'))+'\n'
