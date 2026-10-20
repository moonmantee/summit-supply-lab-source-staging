import json
import pathlib
import sys
import tempfile
import unittest
ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'payload/controller'))
from legacy.state import Store
from panel_catalog import PanelError
try:
    from panel_store import PanelStore
except ImportError: PanelStore = None


class StorageTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(PanelStore, 'revision storage not implemented')
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.store = Store(pathlib.Path(self.tmp.name) / 'state.db')
        self.old = self.store.create_exercise(3)
        self.free = 256 * 1024 * 1024
        self.panel = PanelStore(self.store, lambda: 100, lambda: self.free)
        self.doc = dict(name='Original', duration=10800, events=[])
        self.panel.initialize([], {'accepted': self.doc})

    def write(self, profile='accepted', revision=1, doc=None):
        with self.store.transaction() as tx:
            return self.panel.write_profile(tx, profile, revision, doc or self.doc)

    def test_idempotent_import(self):
        self.panel.initialize([], {'accepted': self.doc})
        self.assertEqual(len(self.panel.list_profiles()), 1)
        self.assertEqual(self.panel.read_profile('accepted', 1)['document'], self.doc)

    def test_low_disk_rejects_without_history_loss(self):
        self.free -= 1
        with self.assertRaises(PanelError): self.write()
        self.assertEqual(self.panel.read_profile('accepted', None)['revision'], 1)
        with self.store.transaction() as tx, self.assertRaises(PanelError):
            self.panel.load_snapshot(tx, 'accepted', 1, 3)
        self.assertEqual(self.store.status(self.old)['state'], 'DISARMED')

    def test_pruning_pins_original_and_snapshot(self):
        with self.store.transaction() as tx: snapshot = self.panel.load_snapshot(tx, 'accepted', 1, 3)
        for revision in range(1, 25): self.write(revision=revision)
        self.assertEqual(self.panel.read_profile('accepted', None)['revision'], 25)
        self.assertEqual(self.panel.read_profile('accepted', 1)['document'], self.doc)
        self.assertEqual(self.panel.read_snapshot(snapshot['exercise_id'])['document'], self.doc)
        with self.store.transaction() as tx:
            self.assertEqual(tx.execute('SELECT count(*) FROM panel_revisions').fetchone()[0], 20)

    def test_load_transaction_rollback(self):
        with self.assertRaises(RuntimeError), self.store.transaction() as tx:
            self.panel.load_snapshot(tx, 'accepted', 1, 3)
            raise RuntimeError('power loss')
        self.assertEqual(self.store.status(self.old)['state'], 'DISARMED')
        self.assertEqual(self.panel.read_snapshot(self.old)['document']['events'], [])

    def test_unknown_historical_schedule_not_fabricated(self):
        self.assertIsNone(self.panel.read_snapshot('unknown'))

    def test_profile_and_revision_conflicts(self):
        self.write()
        with self.assertRaises(PanelError): self.write(revision=1)
        for i in range(63): self.write(None, None, dict(self.doc, name=str(i)))
        with self.assertRaises(PanelError): self.write(None, None)

if __name__ == '__main__': unittest.main()
