import importlib.util
import unittest
import tempfile
import sqlite3
import json
from pathlib import Path


class ScorerTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(importlib.util.find_spec('scorer'), 'Scoring implementation is not installed yet')
        import scorer
        self.scorer = scorer

    def test_expected_page_passes(self):
        self.assertEqual(self.scorer.validate_page(200, b'CATALOG SKU $49.00', ['CATALOG', 'SKU', '$49.00'])[0], 'PASS')

    def test_generic_page_fails(self):
        self.assertEqual(self.scorer.validate_page(200, b'Apache default page', ['CATALOG'])[0], 'DOWN')

    def test_changed_price_fails(self):
        self.assertEqual(self.scorer.validate_page(200, b'CATALOG SKU $99.00', ['CATALOG', 'SKU', '$49.00'])[0], 'DOWN')

    def test_error_status_fails_even_with_content(self):
        self.assertEqual(self.scorer.validate_page(503, b'CATALOG', ['CATALOG'])[0], 'DOWN')

    def test_oversized_body_fails(self):
        self.assertEqual(self.scorer.validate_page(200, b'x' * (self.scorer.MAX_BODY + 1), ['x'])[0], 'DOWN')

    def test_missing_trust_file_is_invalid(self):
        status, _ = self.scorer.check({'url': 'https://127.0.0.1/', 'ca_file': '/nonexistent/summit-cert.pem', 'expected': ['CATALOG']})
        self.assertEqual(status, 'INVALID')

    def test_plain_http_configuration_is_invalid(self):
        status, _ = self.scorer.check({'url': 'http://127.0.0.1/', 'ca_file': '/nonexistent/summit-cert.pem', 'expected': ['CATALOG']})
        self.assertEqual(status, 'INVALID')

    def test_invalid_result_keeps_its_label(self):
        with tempfile.TemporaryDirectory() as folder, sqlite3.connect(':memory:') as db:
            db.execute('CREATE TABLE rounds(id INTEGER PRIMARY KEY, timestamp TEXT, status TEXT, reason TEXT, latency_ms INTEGER)')
            db.execute("INSERT INTO rounds VALUES(1,'2026-09-08T00:00:00+00:00','INVALID','Configuration error',0)")
            self.scorer.render_report(db, Path(folder))
            self.assertIn('class="status">INVALID<', (Path(folder) / 'index.html').read_text())


class ScoringStateTests(unittest.TestCase):
    def setUp(self):
        import scorer
        self.scorer = scorer
        self.db = sqlite3.connect(':memory:')
        self.addCleanup(self.db.close)
        self.scorer.initialize_schema(self.db)
        self.ssh = {'id': 'dc01-ssh', 'points': 1, 'sla_penalty': 5}
        self.web = {'id': 'shop01-https', 'points': 5, 'sla_penalty': 15}

    def apply(self, service, status):
        return self.scorer.apply_scoring_result(self.db, service, status)

    def test_pass_awards_points_and_resets_counter(self):
        self.apply(self.web, 'DOWN')
        result = self.apply(self.web, 'PASS')
        self.assertEqual(result, {'awarded_points': 5, 'sla_deduction': 0, 'consecutive_failures': 0})

    def test_fifth_down_deducts_once_and_starts_a_new_window(self):
        results = [self.apply(self.web, 'DOWN') for _ in range(6)]
        self.assertEqual([item['sla_deduction'] for item in results], [0, 0, 0, 0, 15, 0])
        self.assertEqual([item['consecutive_failures'] for item in results], [1, 2, 3, 4, 0, 1])

    def test_invalid_neither_increments_nor_resets_counter(self):
        self.apply(self.web, 'DOWN')
        result = self.apply(self.web, 'INVALID')
        self.assertEqual(result['consecutive_failures'], 1)
        self.assertEqual(result['awarded_points'], 0)
        self.assertEqual(result['sla_deduction'], 0)

    def test_service_counters_are_independent(self):
        self.apply(self.web, 'DOWN')
        self.apply(self.ssh, 'DOWN')
        self.apply(self.web, 'PASS')
        self.assertEqual(self.scorer.get_failure_count(self.db, 'shop01-https'), 0)
        self.assertEqual(self.scorer.get_failure_count(self.db, 'dc01-ssh'), 1)

    def test_full_round_writes_an_audit_row_per_service(self):
        services = [self.web, self.ssh]
        observations = {
            'shop01-https': ('PASS', 'ok', 12),
            'dc01-ssh': ('DOWN', 'connection refused', 4),
        }
        round_id = self.scorer.record_round(self.db, services, observations, '2026-10-01T12:00:00+00:00')
        rows = self.db.execute(
            'SELECT service_id,status,awarded_points,sla_deduction,consecutive_failures '
            'FROM service_checks WHERE round_id=? ORDER BY service_id', (round_id,)
        ).fetchall()
        self.assertEqual(rows, [('dc01-ssh', 'DOWN', 0, 0, 1), ('shop01-https', 'PASS', 5, 0, 0)])

    def test_legacy_round_table_is_preserved(self):
        self.db.execute('CREATE TABLE rounds(id INTEGER PRIMARY KEY, timestamp TEXT, status TEXT, reason TEXT, latency_ms INTEGER)')
        self.db.execute("INSERT INTO rounds VALUES(1,'old','PASS','legacy',1)")
        self.scorer.initialize_schema(self.db)
        self.assertEqual(self.db.execute('SELECT reason FROM rounds').fetchone()[0], 'legacy')


class ConfigurationTests(unittest.TestCase):
    def setUp(self):
        import scorer
        self.scorer = scorer

    def test_forum_https_transition_changes_weights_and_resets_only_forum(self):
        config = {
            'forum_web_mode': 'http',
            'services': [
                {'id': 'forum01-web', 'variants': {
                    'http': {'probe': 'http', 'url': 'http://10.77.30.20/', 'points': 3, 'sla_penalty': 10},
                    'https': {'probe': 'https', 'url': 'https://10.77.30.20/', 'points': 5, 'sla_penalty': 15},
                }},
                {'id': 'dc01-ssh', 'probe': 'banner', 'points': 1, 'sla_penalty': 5},
            ],
        }
        db = sqlite3.connect(':memory:')
        self.addCleanup(db.close)
        self.scorer.initialize_schema(db)
        self.scorer.apply_scoring_result(db, {'id': 'forum01-web', 'points': 3, 'sla_penalty': 10}, 'DOWN')
        self.scorer.apply_scoring_result(db, {'id': 'dc01-ssh', 'points': 1, 'sla_penalty': 5}, 'DOWN')
        resolved = self.scorer.set_forum_mode(config, 'https', db)
        forum = next(service for service in resolved if service['id'] == 'forum01-web')
        self.assertEqual((forum['probe'], forum['points'], forum['sla_penalty']), ('https', 5, 15))
        self.assertEqual(self.scorer.get_failure_count(db, 'forum01-web'), 0)
        self.assertEqual(self.scorer.get_failure_count(db, 'dc01-ssh'), 1)

    def test_unknown_probe_is_invalid_configuration(self):
        status, reason = self.scorer.run_probe({'id': 'bad', 'probe': 'not-real'})
        self.assertEqual(status, 'INVALID')
        self.assertIn('configuration', reason.lower())


if __name__ == '__main__':
    unittest.main()
