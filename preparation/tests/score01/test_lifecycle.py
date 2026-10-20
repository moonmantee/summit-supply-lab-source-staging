import sqlite3
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

import scorer


SERVICE = {
    'id': 'shop01-https',
    'host_name': 'shop01',
    'service_name': 'HTTPS storefront',
    'points': 5,
    'sla_penalty': 15,
}


class LifecycleDatabaseTestCase(unittest.TestCase):
    def setUp(self):
        self.db = sqlite3.connect(':memory:')
        self.addCleanup(self.db.close)
        scorer.initialize_schema(self.db)

    def seed_existing_data(self):
        scorer.record_round(
            self.db,
            [SERVICE],
            {SERVICE['id']: ('DOWN', 'offline', 10)},
            '2026-10-02T01:00:00+00:00',
        )
        self.db.execute(
            'CREATE TABLE IF NOT EXISTS rounds('
            'id INTEGER PRIMARY KEY,timestamp TEXT,status TEXT,reason TEXT,latency_ms INTEGER)'
        )
        self.db.execute(
            "INSERT INTO rounds VALUES(1,'legacy-time','PASS','legacy row',4)"
        )
        self.db.commit()


class LifecycleMigrationTests(LifecycleDatabaseTestCase):
    def test_migration_archives_existing_data_and_creates_ready_event(self):
        self.seed_existing_data()
        from lifecycle import migrate_lifecycle

        current = migrate_lifecycle(self.db, '2026-10-02T02:00:00+00:00')

        events = self.db.execute(
            'SELECT id,name,state,kind FROM competition_events ORDER BY id'
        ).fetchall()
        self.assertEqual(events, [
            (1, 'Pre-competition practice', 'ARCHIVED', 'practice-import'),
            (2, 'Competition 1', 'READY', 'competition'),
        ])
        self.assertEqual((current.id, current.name, current.state), (2, 'Competition 1', 'READY'))
        self.assertEqual(
            self.db.execute('SELECT DISTINCT event_id FROM scoring_rounds').fetchall(),
            [(1,)],
        )
        self.assertEqual(
            self.db.execute('SELECT DISTINCT event_id FROM service_checks').fetchall(),
            [(1,)],
        )
        self.assertEqual(
            self.db.execute(
                'SELECT event_id,service_id,consecutive_failures,total_points,total_sla_deductions '
                'FROM event_service_state'
            ).fetchall(),
            [(1, 'shop01-https', 1, 0, 0)],
        )

    def test_migration_is_repeatable(self):
        self.seed_existing_data()
        from lifecycle import migrate_lifecycle

        first = migrate_lifecycle(self.db, '2026-10-02T02:00:00+00:00')
        before = {
            table: self.db.execute(f'SELECT COUNT(*) FROM {table}').fetchone()[0]
            for table in ('competition_events', 'scorer_settings', 'event_service_state',
                          'scoring_rounds', 'service_checks')
        }
        second = migrate_lifecycle(self.db, '2026-10-02T03:00:00+00:00')
        after = {
            table: self.db.execute(f'SELECT COUNT(*) FROM {table}').fetchone()[0]
            for table in before
        }

        self.assertEqual(first.id, second.id)
        self.assertEqual(before, after)

    def test_legacy_rounds_are_untouched(self):
        self.seed_existing_data()
        from lifecycle import migrate_lifecycle

        migrate_lifecycle(self.db, '2026-10-02T02:00:00+00:00')

        self.assertEqual(
            self.db.execute('SELECT * FROM rounds').fetchall(),
            [(1, 'legacy-time', 'PASS', 'legacy row', 4)],
        )


class LifecycleTransitionTests(LifecycleDatabaseTestCase):
    def setUp(self):
        super().setUp()
        from lifecycle import migrate_lifecycle
        self.current = migrate_lifecycle(self.db, '2026-10-02T02:00:00+00:00')

    def test_start_stop_and_resume_preserve_state(self):
        from lifecycle import transition_event
        self.db.execute(
            'INSERT INTO event_service_state('
            'event_id,service_id,consecutive_failures,total_points,total_sla_deductions,last_status,last_timestamp'
            ') VALUES(?,?,?,?,?,?,?)',
            (self.current.id, 'dc01-ssh', 3, 7, 5, 'DOWN', 'old'),
        )
        self.db.commit()

        started = transition_event(self.db, 'start', '2026-10-02T03:00:00+00:00')
        stopped = transition_event(self.db, 'stop', '2026-10-02T04:00:00+00:00')
        resumed = transition_event(self.db, 'start', '2026-10-02T05:00:00+00:00')

        self.assertEqual((started.state, stopped.state, resumed.state), ('RUNNING', 'STOPPED', 'RUNNING'))
        self.assertEqual(resumed.started_at, '2026-10-02T03:00:00+00:00')
        self.assertEqual(resumed.last_resumed_at, '2026-10-02T05:00:00+00:00')
        self.assertEqual(
            self.db.execute(
                'SELECT consecutive_failures,total_points,total_sla_deductions '
                'FROM event_service_state WHERE event_id=? AND service_id=?',
                (self.current.id, 'dc01-ssh'),
            ).fetchone(),
            (3, 7, 5),
        )

    def test_reset_archives_and_creates_zero_ready_event(self):
        from lifecycle import transition_event
        self.db.execute(
            'INSERT INTO event_service_state('
            'event_id,service_id,consecutive_failures,total_points,total_sla_deductions'
            ') VALUES(?,?,?,?,?)',
            (self.current.id, 'dc01-ssh', 4, 10, 5),
        )
        self.db.commit()

        replacement = transition_event(self.db, 'reset', '2026-10-02T06:00:00+00:00')

        old = self.db.execute(
            'SELECT state,archived_at FROM competition_events WHERE id=?',
            (self.current.id,),
        ).fetchone()
        self.assertEqual(old, ('ARCHIVED', '2026-10-02T06:00:00+00:00'))
        self.assertEqual((replacement.name, replacement.state), ('Competition 2', 'READY'))
        self.assertEqual(
            self.db.execute('SELECT COUNT(*) FROM event_service_state WHERE event_id=?', (replacement.id,)).fetchone()[0],
            0,
        )
        self.assertEqual(
            self.db.execute('SELECT total_points FROM event_service_state WHERE event_id=?', (self.current.id,)).fetchone()[0],
            10,
        )

    def test_unknown_action_rolls_back(self):
        from lifecycle import LifecycleError, transition_event
        before = self.db.execute('SELECT id,name,state FROM competition_events ORDER BY id').fetchall()

        with self.assertRaises(LifecycleError):
            transition_event(self.db, 'erase', '2026-10-02T06:00:00+00:00')

        self.assertEqual(
            self.db.execute('SELECT id,name,state FROM competition_events ORDER BY id').fetchall(),
            before,
        )

    def test_rapid_resets_serialize_without_reusing_event(self):
        from lifecycle import transition_event

        second = transition_event(self.db, 'reset', '2026-10-02T06:00:00+00:00')
        third = transition_event(self.db, 'reset', '2026-10-02T06:00:01+00:00')

        self.assertNotEqual(second.id, third.id)
        self.assertEqual((second.name, third.name), ('Competition 2', 'Competition 3'))
        self.assertEqual(
            self.db.execute(
                "SELECT name,state FROM competition_events WHERE kind='competition' ORDER BY id"
            ).fetchall(),
            [('Competition 1', 'ARCHIVED'), ('Competition 2', 'ARCHIVED'), ('Competition 3', 'READY')],
        )


class ScoringLifecycleTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.database = self.root / 'state' / 'results.sqlite3'
        self.public = self.root / 'public'
        self.config = self.root / 'config.json'
        self.config.write_text(json.dumps({
            'services': [{
                'id': 'test-ssh', 'host_name': 'test01', 'service_name': 'SSH',
                'probe': 'banner', 'host': '127.0.0.1', 'port': 9,
                'banner_prefix': 'SSH-', 'points': 1, 'sla_penalty': 5,
            }]
        }))

    def event(self):
        from lifecycle import get_current_event
        with sqlite3.connect(self.database) as db:
            return get_current_event(db)

    def test_ready_event_skips_all_probes_and_round_writes(self):
        with mock.patch.object(scorer, 'run_probe', side_effect=AssertionError('probe called')):
            result = scorer.run_scoring_round(self.config, self.database, self.public)

        self.assertFalse(result['recorded'])
        self.assertEqual(result['event_state'], 'READY')
        with sqlite3.connect(self.database) as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM scoring_rounds').fetchone()[0], 0)

    def test_ready_timer_render_preserves_dashboard_control_token(self):
        token = 'organizer-control-token-value-1234567890'
        self.database.parent.mkdir(parents=True)
        (self.database.parent / 'control-token').write_text(token, encoding='ascii')

        scorer.run_scoring_round(self.config, self.database, self.public)

        page = (self.public / 'index.html').read_text(encoding='utf-8')
        self.assertIn(
            f'<meta name="summit-control-token" content="{token}">',
            page,
        )

    def test_stopped_event_skips_all_probes_and_round_writes(self):
        scorer.run_scoring_round(self.config, self.database, self.public)
        from lifecycle import transition_event
        with sqlite3.connect(self.database) as db:
            transition_event(db, 'start', '2026-10-02T03:00:00+00:00')
            transition_event(db, 'stop', '2026-10-02T04:00:00+00:00')

        with mock.patch.object(scorer, 'run_probe', side_effect=AssertionError('probe called')):
            result = scorer.run_scoring_round(self.config, self.database, self.public)

        self.assertFalse(result['recorded'])
        self.assertEqual(result['event_state'], 'STOPPED')
        with sqlite3.connect(self.database) as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM scoring_rounds').fetchone()[0], 0)

    def test_new_event_has_independent_sla_counters(self):
        scorer.run_scoring_round(self.config, self.database, self.public)
        from lifecycle import get_current_event, transition_event
        with sqlite3.connect(self.database) as db:
            first = get_current_event(db)
            for _ in range(4):
                scorer.apply_scoring_result(db, SERVICE, 'DOWN', event_id=first.id)
            db.commit()
            replacement = transition_event(db, 'reset', '2026-10-02T05:00:00+00:00')
            result = scorer.apply_scoring_result(db, SERVICE, 'DOWN', event_id=replacement.id)
            db.commit()

            self.assertEqual(scorer.get_failure_count(db, SERVICE['id'], first.id), 4)
            self.assertEqual(result['consecutive_failures'], 1)
            self.assertEqual(scorer.get_failure_count(db, SERVICE['id'], replacement.id), 1)

    def test_current_event_totals_exclude_archived_events(self):
        scorer.run_scoring_round(self.config, self.database, self.public)
        from lifecycle import get_current_event, transition_event
        with sqlite3.connect(self.database) as db:
            first = get_current_event(db)
            scorer.apply_scoring_result(db, SERVICE, 'PASS', event_id=first.id)
            db.commit()
            replacement = transition_event(db, 'reset', '2026-10-02T05:00:00+00:00')
            scorer.apply_scoring_result(db, SERVICE, 'PASS', event_id=replacement.id)
            db.commit()

            totals = db.execute(
                'SELECT event_id,total_points FROM event_service_state ORDER BY event_id'
            ).fetchall()
            self.assertEqual(totals, [(first.id, 5), (replacement.id, 5)])


class ScoringRaceTests(LifecycleDatabaseTestCase):
    def setUp(self):
        super().setUp()
        from lifecycle import migrate_lifecycle, transition_event
        self.event = migrate_lifecycle(self.db, '2026-10-02T02:00:00+00:00')
        transition_event(self.db, 'start', '2026-10-02T03:00:00+00:00')
        self.observations = {SERVICE['id']: ('PASS', 'ok', 2)}

    def test_stop_during_probes_discards_entire_round(self):
        from lifecycle import transition_event
        transition_event(self.db, 'stop', '2026-10-02T04:00:00+00:00')

        round_id = scorer.record_round(
            self.db, [SERVICE], self.observations,
            '2026-10-02T04:00:01+00:00', expected_event_id=self.event.id,
        )

        self.assertIsNone(round_id)
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM scoring_rounds').fetchone()[0], 0)
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM service_checks').fetchone()[0], 0)
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM event_service_state').fetchone()[0], 0)

    def test_reset_during_probes_discards_entire_round(self):
        from lifecycle import transition_event
        replacement = transition_event(self.db, 'reset', '2026-10-02T04:00:00+00:00')

        round_id = scorer.record_round(
            self.db, [SERVICE], self.observations,
            '2026-10-02T04:00:01+00:00', expected_event_id=self.event.id,
        )

        self.assertIsNone(round_id)
        self.assertNotEqual(replacement.id, self.event.id)
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM scoring_rounds').fetchone()[0], 0)
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM service_checks').fetchone()[0], 0)
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM event_service_state').fetchone()[0], 0)


if __name__ == '__main__':
    unittest.main()
