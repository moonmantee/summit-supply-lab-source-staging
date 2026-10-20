import json
import pathlib
import sys
import tempfile
import unittest
ROOT=pathlib.Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'payload/controller'))
from legacy.state import Store
from panel_store import PanelStore
import fixture_coordinator as coordinator


class RestartTests(unittest.TestCase):
    def test_committed_snapshot_survives_missing_or_invalid_legacy_file(self):
        self.assertTrue(hasattr(coordinator,'restore_snapshot'),'startup still requires legacy scenario')
        with tempfile.TemporaryDirectory() as tmp:
            root=pathlib.Path(tmp);store=Store(root/'state.db');store.create_exercise(3)
            event=dict(id='event1',guest='shop01',action='notice',target='desktop',at=0,window=15)
            panel=PanelStore(store,free_bytes=lambda:10**9);panel.initialize([] ,{'saved':dict(name='Saved',duration=10800,events=[event])})
            with store.transaction() as tx:panel.load_snapshot(tx,'saved',1,3)
            config=dict(scenario=str(root/'missing.json'),guests={'shop01':{'targets':['desktop']}})
            _,scenario=coordinator.restore_snapshot(store,config)
            self.assertEqual(scenario,[event])
            pathlib.Path(config['scenario']).write_text('{truncated')
            _,scenario=coordinator.restore_snapshot(store,config)
            self.assertEqual(scenario,[event])

if __name__=='__main__':unittest.main()
