import copy
import json
import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'payload/controller'))
try:
    from panel_catalog import build_catalog, validate_profile, PanelError
except ImportError:
    build_catalog = validate_profile = PanelError = None

GUESTS = {
    'shop01': {'targets': ['apache', 'desktop', 'wall'], 'business_enabled': True, 'hour4_enabled': True},
    'sql01': {'targets': ['mariadb', 'desktop', 'wall'], 'business_enabled': True, 'hour4_enabled': True},
    'dc01': {'targets': ['dns', 'desktop'], 'business_enabled': True, 'hour4_enabled': True},
    'forum01': {'targets': ['web', 'ftp', 'desktop'], 'business_enabled': True, 'hour4_enabled': True},
    'mail01': {'targets': ['web', 'smtp', 'imap', 'desktop'], 'business_enabled': True, 'hour4_enabled': True},
    'workstation01': {'targets': ['desktop'], 'business_enabled': True},
}


class CatalogTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(build_catalog, 'panel catalog is not implemented')
        self.catalog = build_catalog(GUESTS, GUESTS)

    def document(self, **event):
        return {'name': 'Custom', 'duration': 10800, 'events': [dict(id='test', guest='shop01', action='notice', target='desktop', at=0, window=15, **event)]}

    def test_catalog_filters_enrollment_and_gates(self):
        guests = copy.deepcopy(GUESTS)
        guests['shop01']['business_enabled'] = False
        c = build_catalog({'shop01': guests['shop01']}, guests)
        self.assertEqual({x['action'] for x in c['capabilities']}, {'notice'})

    def test_workstation_notice_only(self):
        self.assertEqual({x['action'] for x in self.catalog['capabilities'] if x['guest'] == 'workstation01'}, {'notice'})

    def test_no_iis_restart_off(self):
        self.assertFalse(any(x['target'] == 'web' and x['action'] == 'business_restart_off' for x in self.catalog['capabilities']))

    def test_notice_target_cannot_be_business_service(self):
        d = self.document()
        d['events'][0].update(action='business_stop', duration=15)
        with self.assertRaises(PanelError): validate_profile(d, self.catalog)

    def test_accepted_templates(self):
        for name, count, duration in [('first3h-all', 102, 10800), ('first4h-all', 110, 14400)]:
            events = json.loads((ROOT / 'payload/controller/profiles' / (name + '.json')).read_text())
            self.assertEqual(len(validate_profile(dict(name=name, duration=duration, events=events), self.catalog)['events']), count)

    def test_strict_profile_inputs(self):
        for change in [dict(at=True), dict(at=float('nan')), dict(window=float('inf')), dict(command='id'), dict(id='../bad')]:
            d = self.document(); d['events'][0].update(change)
            with self.subTest(change=change), self.assertRaises(PanelError): validate_profile(d, self.catalog)
        for field, value in [('duration', True), ('duration', 42), ('events', [self.document()['events'][0]] * 257)]:
            d = self.document(); d[field] = value
            with self.assertRaises(PanelError): validate_profile(d, self.catalog)
        d = self.document(); d['events'] *= 2
        with self.assertRaises(PanelError): validate_profile(d, self.catalog)

    def test_custom_name_cannot_bypass_gates(self):
        g = copy.deepcopy(GUESTS); g['shop01']['hour4_enabled'] = False
        d = self.document(); d.update(duration=14400)
        d['events'][0].update(action='business_binary_rename', target='apache', duration=180, at=10800)
        with self.assertRaises(PanelError): validate_profile(d, build_catalog(g, g))

    def test_selected_duration_bounds(self):
        d = self.document(); d['events'][0].update(action='business_binary_rename', target='apache', duration=180, at=10800)
        with self.assertRaises(PanelError): validate_profile(d, self.catalog)
        d['duration'] = 14400
        self.assertEqual(validate_profile(d, self.catalog), d)
        d['events'][0].update(id='hour4-pilot-shop01-apache', at=4)
        with self.assertRaises(PanelError): validate_profile(d, self.catalog)

    def test_single_hour4_pilot_at_three_seconds(self):
        for path in (ROOT / 'payload/controller/profiles').glob('hour4-*-pilot.json'):
            with self.subTest(profile=path.stem):
                document = dict(name=path.stem, duration=14400, events=json.loads(path.read_text()))
                self.assertEqual(validate_profile(document, self.catalog), document)

    def test_hour4_pilot_exception_requires_single_exact_event_and_gates(self):
        event = dict(id='hour4-pilot-shop01-apache', guest='shop01', target='apache',
                     action='business_binary_rename', at=3, window=15, duration=15)
        document = dict(name='Quick test', duration=14400, events=[event])
        for events in ([dict(event, id='custom-event')], [dict(event, at=4)],
                       [event, self.document()['events'][0]], [dict(event, duration=181)],
                       [dict(event, action='business_launch_fault')]):
            with self.subTest(events=events), self.assertRaises(PanelError):
                validate_profile(dict(document, events=events), self.catalog)
        for gate in ('business_enabled', 'hour4_enabled'):
            guests = copy.deepcopy(GUESTS)
            guests['shop01'][gate] = False
            with self.subTest(gate=gate), self.assertRaises(PanelError):
                validate_profile(document, build_catalog(guests, guests))

if __name__ == '__main__': unittest.main()
