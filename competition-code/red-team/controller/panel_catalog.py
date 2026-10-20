"""Shared fixed capability catalog. No executable or path is an input."""
import copy
import json
import math
from fixture_contract import identifiers
from four_hours import FAULTS, validate as validate_four

SERVICES = {'shop01': ('apache',), 'sql01': ('mariadb',), 'dc01': ('dns',),
            'forum01': ('web', 'ftp'), 'mail01': ('smtp', 'imap', 'web'), 'workstation01': ()}
DURATIONS = (10800, 12600, 14400)


class PanelError(ValueError):
    def __init__(self, code, message, rows=None):
        super().__init__(message)
        self.code, self.message, self.rows = code, message, rows or []


def build_catalog(guests: dict, gates: dict) -> dict:
    capabilities = []
    for guest, config in guests.items():
        targets = config.get('targets', []) if isinstance(config, dict) else []
        gate = gates.get(guest, {})
        def add(action, target):
            capabilities.append(dict(guest=guest, action=action, target=target,
                                     label=action.replace('_', ' ').title()))
        for target in ('desktop', 'wall'):
            if target in targets and (target != 'wall' or guest in ('shop01', 'sql01', 'workstation01')):
                add('notice', target)
        if gate.get('business_enabled') is True:
            for target in SERVICES.get(guest, ()):
                if target not in targets: continue
                for action in ('business_stop', 'business_disable', 'business_restart_off'):
                    if target == 'web' and action == 'business_restart_off': continue
                    add(action, target)
                if gate.get('hour4_enabled') is True and (guest, target) in FAULTS:
                    add(FAULTS[guest, target], target)
    return dict(capabilities=capabilities, durations=list(DURATIONS), max_events=256,
                window_min=1, window_max=15, reservation_min=15, reservation_max=180)


def validate_profile(document: dict, catalog: dict) -> dict:
    if not isinstance(document, dict) or set(document) != {'name', 'duration', 'events'}:
        raise PanelError('invalid', 'Expected name, duration and events only')
    name, duration, events = document['name'], document['duration'], document['events']
    if not isinstance(name, str) or not 1 <= len(name.strip()) <= 80 or any(ord(c) < 32 for c in name):
        raise PanelError('invalid', 'Profile name must be 1–80 printable characters')
    if type(duration) is not int or duration not in DURATIONS:
        raise PanelError('invalid', 'Choose a supported exercise duration')
    if not isinstance(events, list) or len(events) > 256:
        raise PanelError('invalid', 'At most 256 events are allowed')
    allowed = {(c['guest'], c['action'], c['target']) for c in catalog['capabilities']}
    targets = {}
    for guest, _, target in allowed: targets.setdefault(guest, set()).add(target)
    rows, seen = [], set()
    for index, event in enumerate(events):
        try:
            if not isinstance(event, dict): raise ValueError('Expected an event object')
            identifiers(event.get('guest'), event.get('id'))
            identifiers(event.get('target'), 'target')
            if event['id'] in seen: raise ValueError('Duplicate event ID')
            seen.add(event['id'])
            if (event['guest'], event.get('action'), event['target']) not in allowed:
                raise ValueError('Unsupported or unaccepted guest/action/target')
            validate_four([event], targets, allow_pilot=len(events) == 1)
            finish = event['at'] + event['window'] + (event['duration'] + 30 if 'duration' in event else 0)
            if finish > duration: raise ValueError('Event exceeds selected exercise duration')
        except (ValueError, TypeError, KeyError):
            rows.append(dict(index=index, id=event.get('id') if isinstance(event, dict) else None,
                             field='event', message='Invalid fields, capability, timing, reservation or duplicate ID'))
    if rows: raise PanelError('invalid', 'Correct the highlighted schedule rows', rows)
    # Also rejects nonfinite values outside event numeric fields before persistence.
    try: json.dumps(document, allow_nan=False)
    except (ValueError, TypeError): raise PanelError('invalid', 'Invalid JSON document')
    return copy.deepcopy(document)
