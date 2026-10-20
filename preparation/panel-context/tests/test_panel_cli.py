import contextlib
import io
import pathlib
import sys
import unittest
from unittest.mock import patch
ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'payload/controller'))
import fixture_control


class CliTests(unittest.TestCase):
    def test_cli_is_socket_client(self):
        self.assertTrue(hasattr(fixture_control, 'AdminClient'), 'CLI still independently changes controller state')

    def test_load_uses_dynamic_known_profile(self):
        if not hasattr(fixture_control, 'AdminClient'): self.fail('socket client missing')
        calls = []
        class Client:
            def call(self, request):
                calls.append(request)
                if request['op']=='status': return dict(ok=True,data=dict(exercise={'id':'old'},lifecycle_revision=7))
                if request['op']=='profiles.read': return dict(ok=True,data=dict(id='first4h-all', revision=3))
                return dict(ok=True,data=dict(state='DISARMED'))
        with patch.object(fixture_control,'AdminClient',Client), patch.object(fixture_control.os,'geteuid',return_value=0,create=True), patch.object(sys,'argv',['fixture_control.py','load','first4h-all']), contextlib.redirect_stdout(io.StringIO()):
            fixture_control.main()
        self.assertEqual(calls[-1]['args'], {'profile_id':'first4h-all','revision':3})
        self.assertEqual(calls[-1]['expected_lifecycle_revision'],7)

if __name__=='__main__': unittest.main()
