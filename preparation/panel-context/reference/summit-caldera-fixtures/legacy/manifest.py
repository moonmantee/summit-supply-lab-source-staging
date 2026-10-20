"""Strict exercise manifest with fixed marker and bounded disposable-service targets."""
import json
import math
import re


def identifier(value):
    return isinstance(value, str) and re.fullmatch(r'[a-zA-Z0-9_-]{1,64}', value)


def strict_json(data):
    def pairs(items):
        result = {}
        for k, v in items:
            if k in result:
                raise ValueError('duplicate JSON key')
            result[k] = v
        return result
    def invalid(value):
        raise ValueError('non-finite JSON number')
    return json.loads(data, object_pairs_hook=pairs, parse_constant=invalid)


def validate_scenario(document, allowed_targets):
    if isinstance(document,list) and any(isinstance(e,dict) and e.get('action') in ('business_binary_rename','business_launch_fault') for e in document):
        from four_hours import validate
        return validate(document,allowed_targets,allow_pilot=True)
    if isinstance(document,list) and any(isinstance(e,dict) and str(e.get('action','')).startswith('business_') for e in document):
        from first_three_hours import validate
        return validate(document,allowed_targets)
    if not isinstance(document, list) or len(document) > 1000:
        raise ValueError('scenario must contain at most 1000 events')
    seen = set()
    for e in document:
        fields={'id', 'at', 'window', 'guest', 'action', 'target'}
        if isinstance(e,dict) and e.get('action') in ('service_stop','service_disable','service_config','service_executable','service_definition'):fields.add('duration')
        if not isinstance(e, dict) or set(e) != fields:
            raise ValueError('invalid event fields')
        if not identifier(e['id']) or e['id'] in seen:
            raise ValueError('invalid or duplicate event id')
        seen.add(e['id'])
        if e['action'] not in ('marker','service_stop','service_disable','service_config','service_executable','service_definition','notice') or not identifier(e['guest']) or e['guest'] not in allowed_targets:
            raise ValueError('unsupported action or guest')
        if e['action'] in ('service_stop','service_disable','service_config','service_executable','service_definition') and (e['target']!='demo' or type(e['duration']) is not int or not 5<=e['duration']<=120):
            raise ValueError('unapproved service target or duration')
        if e['action']=='notice' and e['target'] not in ('desktop','wall'):
            raise ValueError('unapproved notice target')
        if not identifier(e['target']) or e['target'] not in allowed_targets[e['guest']]:
            raise ValueError('target not allowlisted')
        for key, low, high in [('at', 0, 12599), ('window', 1, 600)]:
            v = e[key]
            if type(v) not in (int, float) or not math.isfinite(v) or not low <= v <= high:
                raise ValueError('invalid event timing')
    return document


def load_config(path):
    with open(path, encoding='utf-8') as f:
        c = strict_json(f.read())
    expected = {'bind', 'port', 'scoring_db', 'scenario', 'guests', 'certificate', 'key'}
    if not isinstance(c, dict) or set(c) != expected:
        raise ValueError('invalid configuration fields')
    if c['bind'] not in ('127.0.0.1', '10.77.70.20'):
        raise ValueError('unapproved listener address')
    if type(c['port']) is not int or not 1024 <= c['port'] <= 65535:
        raise ValueError('invalid port')
    if not isinstance(c['guests'], dict) or len(c['guests']) > 32:
        raise ValueError('invalid guest roster')
    for name, guest in c['guests'].items():
        if not identifier(name) or set(guest) not in ({'token_sha256', 'targets'}, {'token_sha256', 'targets', 'source_ip'}):
            raise ValueError('invalid guest record')
        if not re.fullmatch('[0-9a-f]{64}', guest['token_sha256']):
            raise ValueError('invalid credential hash')
        if not isinstance(guest['targets'], list) or not all(identifier(t) for t in guest['targets']):
            raise ValueError('invalid target identifiers')
        if guest.get('source_ip', '127.0.0.1') not in ('127.0.0.1', '10.77.20.10'):
            raise ValueError('unapproved guest source')
    return c
