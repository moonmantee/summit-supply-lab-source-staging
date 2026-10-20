import sqlite3
import tempfile
import unittest
from pathlib import Path
import scorer
from lifecycle import get_current_event, migrate_lifecycle, transition_event


class ReportingTests(unittest.TestCase):
    def render(self, count):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        folder = Path(self.temp.name)
        with sqlite3.connect(':memory:') as db:
            db.execute('CREATE TABLE rounds(id INTEGER PRIMARY KEY,timestamp TEXT,status TEXT,reason TEXT,latency_ms INTEGER)')
            for i in range(1, count + 1):
                state = ['PASS', 'FAIL', 'INVALID'][(i - 1) % 3]
                db.execute('INSERT INTO rounds VALUES(?,?,?,?,?)', (i, '2026-09-08T04:00:00+00:00', state, '<script>alert("unsafe")</script>', i))
            scorer.render_report(db, folder)
        return folder

    def test_all_checks_have_history_rows(self):
        folder = self.render(75)
        self.assertTrue((folder / 'history.html').exists(), 'History page must exist')
        history = (folder / 'history.html').read_text()
        self.assertEqual(history.count('data-check='), 75)
        self.assertIn('data-check="1"', history)
        self.assertIn('data-check="75"', history)

    def test_arrows_and_invalid_are_distinct(self):
        folder = self.render(3)
        history = (folder / 'history.html').read_text()
        self.assertIn('↑', history)
        self.assertIn('↓', history)
        self.assertIn('INVALID', history)
        self.assertIn('data-status="INVALID"', history)

    def test_error_details_are_escaped(self):
        folder = self.render(3)
        history = (folder / 'history.html').read_text()
        self.assertNotIn('<script>alert(', history)
        self.assertIn('&lt;script&gt;', history)

    def test_history_has_search_status_and_pagination(self):
        folder = self.render(75)
        history = (folder / 'history.html').read_text()
        for marker in ['id="search"', 'id="status-filter"', 'id="next"', 'id="previous"']:
            self.assertIn(marker, history)

    def test_empty_database_is_renderable(self):
        folder = self.render(0)
        self.assertIn('No checks yet', (folder / 'index.html').read_text())
        self.assertTrue((folder / 'history.html').exists())

    def test_multi_service_score_sla_and_failure_counters_are_rendered(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        folder = Path(self.temp.name)
        services = [
            {'id': 'shop01-https', 'host_name': 'shop01', 'service_name': 'HTTPS storefront',
             'points': 5, 'sla_penalty': 15},
            {'id': 'dc01-ssh', 'host_name': 'dc01', 'service_name': 'SSH',
             'points': 1, 'sla_penalty': 5},
        ]
        with sqlite3.connect(':memory:') as db:
            scorer.initialize_schema(db)
            for number in range(5):
                scorer.record_round(db, services, {
                    'shop01-https': ('DOWN', 'offline', 10),
                    'dc01-ssh': ('PASS', 'ok', 2),
                }, f'2026-10-01T12:0{number}:00+00:00')
            scorer.render_report(db, folder, services)
        status = (folder / 'index.html').read_text()
        history = (folder / 'history.html').read_text()
        self.assertIn('HTTPS storefront', status)
        self.assertIn('dc01', status)
        self.assertIn('5', status)
        self.assertIn('15', status)
        self.assertIn('0 / 5', status)
        self.assertEqual(history.count('data-check='), 10)

    def test_invalid_does_not_appear_as_down(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        folder = Path(self.temp.name)
        services = [{'id': 'bad', 'host_name': 'host', 'service_name': 'Test',
                     'points': 1, 'sla_penalty': 5}]
        with sqlite3.connect(':memory:') as db:
            scorer.initialize_schema(db)
            scorer.record_round(db, services, {'bad': ('INVALID', 'bad config', 0)},
                                '2026-10-01T12:00:00+00:00')
            scorer.render_report(db, folder, services)
        status = (folder / 'index.html').read_text()
        self.assertIn('INVALID', status)
        self.assertIn('0 / 5', status)


EVENT_SERVICES = [
    {'id': 'shop01-https', 'host_name': 'shop01', 'service_name': 'HTTPS storefront',
     'points': 5, 'sla_penalty': 15},
    {'id': 'dc01-ssh', 'host_name': 'dc01', 'service_name': 'SSH',
     'points': 1, 'sla_penalty': 5},
]


class EventReportingTestCase(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name)
        self.db = sqlite3.connect(':memory:')
        self.addCleanup(self.db.close)
        scorer.initialize_schema(self.db)
        self.event = migrate_lifecycle(self.db, '2026-10-02T01:00:00+00:00')

    def start(self):
        self.event = transition_event(self.db, 'start', '2026-10-02T01:01:00+00:00')
        return self.event

    def record(self, when, statuses):
        observations = {
            service['id']: (statuses[service['id']], f'{service["id"]} <reason>', 10)
            for service in EVENT_SERVICES
        }
        return scorer.record_round(
            self.db, EVENT_SERVICES, observations, when,
            expected_event_id=self.event.id,
        )

    def render(self, token='test-token'):
        scorer.render_report(self.db, self.folder, EVENT_SERVICES, control_token=token)
        return (self.folder / 'index.html').read_text(), (self.folder / 'history.html').read_text()


class EventStatusTests(EventReportingTestCase):
    def test_status_page_shows_event_state_and_valid_buttons(self):
        ready, _ = self.render()
        self.assertIn('data-event-state="READY"', ready)
        self.assertIn('id="start-control"', ready)
        self.assertIn('id="stop-control" disabled', ready)
        self.assertIn('id="reset-control"', ready)

        self.start()
        running, _ = self.render()
        self.assertIn('data-event-state="RUNNING"', running)
        self.assertIn('id="start-control" disabled', running)
        self.assertIn('id="stop-control"', running)

        transition_event(self.db, 'stop', '2026-10-02T01:02:00+00:00')
        stopped, _ = self.render()
        self.assertIn('data-event-state="STOPPED"', stopped)
        self.assertIn('id="start-control"', stopped)
        self.assertIn('id="stop-control" disabled', stopped)

    def test_archived_totals_do_not_leak_into_current_event(self):
        self.start()
        self.record('2026-10-02T01:02:00+00:00', {
            'shop01-https': 'PASS', 'dc01-ssh': 'PASS',
        })
        archived_id = self.event.id
        replacement = transition_event(self.db, 'reset', '2026-10-02T01:03:00+00:00')

        status, _ = self.render()

        self.assertIn(f'data-event-id="{replacement.id}"', status)
        self.assertIn('data-total-points="0"', status)
        self.assertIn('data-total-sla="0"', status)
        self.assertEqual(
            self.db.execute(
                'SELECT SUM(total_points) FROM event_service_state WHERE event_id=?',
                (archived_id,),
            ).fetchone()[0],
            6,
        )

    def test_control_token_and_all_dynamic_text_are_escaped(self):
        self.db.execute(
            'UPDATE competition_events SET name=? WHERE id=?',
            ('<script>event</script>', self.event.id),
        )
        self.db.commit()
        self.start()
        self.record('2026-10-02T01:02:00+00:00', {
            'shop01-https': 'DOWN', 'dc01-ssh': 'INVALID',
        })

        status, _ = self.render('token"><script>alert(1)</script>')

        self.assertNotIn('<script>event</script>', status)
        self.assertIn('&lt;script&gt;event&lt;/script&gt;', status)
        self.assertNotIn('token"><script>', status)
        self.assertIn('token&quot;&gt;&lt;script&gt;', status)
        self.assertNotIn('shop01-https <reason>', status)


class HistoryGridTests(EventReportingTestCase):
    def seed_three_rounds(self):
        self.start()
        self.record('2026-10-02T01:02:00+00:00', {
            'shop01-https': 'PASS', 'dc01-ssh': 'DOWN',
        })
        self.record('2026-10-02T01:04:00+00:00', {
            'shop01-https': 'DOWN', 'dc01-ssh': 'INVALID',
        })
        sparse_round = self.db.execute(
            'INSERT INTO scoring_rounds(timestamp,event_id) VALUES(?,?)',
            ('2026-10-02T01:06:00+00:00', self.event.id),
        ).lastrowid
        self.db.execute(
            '''INSERT INTO service_checks(
                round_id,timestamp,service_id,host_name,service_name,status,reason,latency_ms,
                awarded_points,sla_deduction,consecutive_failures,event_id)
               VALUES(?,?,?,?,?,?,?,?,?,?,?,?)''',
            (sparse_round, '2026-10-02T01:06:00+00:00', 'shop01-https', 'shop01',
             'HTTPS storefront', 'PASS', 'quoted " <unsafe>', 7, 5, 0, 0, self.event.id),
        )
        self.db.commit()

    def test_grid_has_service_headers_and_timestamp_rows(self):
        self.seed_three_rounds()
        _, history = self.render()
        self.assertIn('data-service-id="shop01-https"', history)
        self.assertIn('data-service-id="dc01-ssh"', history)
        self.assertEqual(history.count('data-grid-row='), 3)
        self.assertIn('2026-10-02T01:06:00+00:00', history)

    def test_grid_cells_show_up_down_invalid_and_blank(self):
        self.seed_three_rounds()
        _, history = self.render()
        self.assertIn('data-grid-status="PASS"', history)
        self.assertIn('data-grid-status="DOWN"', history)
        self.assertIn('data-grid-status="INVALID"', history)
        self.assertIn('class="grid-empty"', history)

    def test_grid_tooltips_escape_reason_and_show_scoring_details(self):
        self.seed_three_rounds()
        _, history = self.render()
        self.assertNotIn('quoted " <unsafe>', history)
        self.assertIn('quoted &quot; &lt;unsafe&gt;', history)
        self.assertIn('Latency: 7 ms', history)
        self.assertIn('Points: +5', history)
        self.assertIn('SLA: -0', history)
        self.assertIn('Window: 0 / 5', history)

    def test_archived_event_navigation_and_pages(self):
        self.seed_three_rounds()
        archived = self.event
        replacement = transition_event(self.db, 'reset', '2026-10-02T01:07:00+00:00')
        _, current_history = self.render()

        archived_path = self.folder / f'history-event-{archived.id}.html'
        current_path = self.folder / f'history-event-{replacement.id}.html'
        self.assertTrue(archived_path.exists())
        self.assertTrue(current_path.exists())
        self.assertIn(f'history-event-{archived.id}.html', current_history)
        self.assertIn('ARCHIVED', archived_path.read_text())
        self.assertIn('READY', current_path.read_text())

    def test_grid_is_bounded_to_latest_100_rounds(self):
        self.start()
        for number in range(105):
            self.record(f'2026-10-02T{number // 60:02d}:{number % 60:02d}:00+00:00', {
                'shop01-https': 'PASS', 'dc01-ssh': 'PASS',
            })

        _, history = self.render()

        self.assertEqual(history.count('data-grid-row='), 100)
        self.assertEqual(history.count('data-check='), 210)

    def test_grid_styles_keep_headers_and_timestamps_visible(self):
        css = (Path(__file__).resolve().parent / 'scoreboard.css').read_text()
        self.assertIn('.history-grid', css)
        self.assertIn('position:sticky', css)
        self.assertIn('.control-panel', css)


if __name__ == '__main__':
    unittest.main()
