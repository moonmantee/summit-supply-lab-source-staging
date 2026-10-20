import copy
import json
import unittest
from pathlib import Path
import build_config


class ManifestTests(unittest.TestCase):
    def valid(self):
        return {'issues': [{'id': n, 'points': 4 if n in (2,5,14,17,18,25,26,27,28,32) else 2,
                            'message': f'Objective {n} repaired', 'category': 'training',
                            'probe': str(n), 'status': 'probe-drafted'} for n in range(1,41)]}

    def test_duplicate_id_rejected(self):
        data = self.valid(); data['issues'][-1]['id'] = 1
        with self.assertRaises(ValueError): build_config.validate_manifest(data)

    def test_missing_objective_rejected(self):
        data = self.valid(); data['issues'].pop()
        with self.assertRaises(ValueError): build_config.validate_manifest(data)

    def test_wrong_point_allocation_rejected(self):
        data = self.valid(); data['issues'][0]['points'] = 6
        with self.assertRaises(ValueError): build_config.validate_manifest(data)

    def test_arbitrary_probe_command_rejected(self):
        data = self.valid(); data['issues'][0]['probe'] = '1; command'
        with self.assertRaises(ValueError): build_config.validate_manifest(data)

    def test_render_is_valid_toml_and_uses_exact_pass(self):
        import tomllib
        data = tomllib.loads(build_config.render(self.valid(), '/opt/summit-shop01'))
        self.assertEqual(len(data['check']), 40)
        self.assertEqual(sum(c['points'] for c in data['check']), 100)
        self.assertEqual(data['check'][0]['pass'][0], {
            'type':'CommandOutput', 'cmd':'/usr/bin/python3 /opt/summit-shop01/probes/check.py 1', 'value':'PASS'})

    def test_installed_manifest_matches_approved_scope(self):
        data = json.loads((Path(__file__).parent/'competition-manifest.json').read_text())
        build_config.validate_manifest(data)
        self.assertEqual(data['issues'][14]['points'], 2)
        self.assertEqual(data['issues'][28]['points'], 2)

if __name__ == '__main__': unittest.main()
