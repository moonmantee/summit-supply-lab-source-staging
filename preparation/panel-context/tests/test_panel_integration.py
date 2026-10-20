import os
import pathlib
import socket
import sys
import unittest
from types import SimpleNamespace
from unittest.mock import patch
from aiohttp import web
from aiohttp.test_utils import TestClient,TestServer
import test_panel_service as service_fixture
from panel_client import AdminClient
from panel_socket import AdminServer
ROOT=pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'payload/caldera'));sys.path.append(str(ROOT/'upstream-test-support'))
from plugins.ccdc import api


@unittest.skipUnless(hasattr(socket,'SO_PEERCRED'),'Linux required')
class IntegrationTests(unittest.IsolatedAsyncioTestCase):
    async def test_http_socket_snapshot_lifecycle(self):
        fixture=service_fixture.ServiceTests('test_empty_start_and_score_gates');fixture.setUp();self.addCleanup(fixture.doCleanups)
        path=str(pathlib.Path(fixture.tmp.name)/'admin.sock')
        server=AdminServer(path,fixture.svc,{os.getuid()});server.start();self.addCleanup(server.close)
        auth=SimpleNamespace(user_map={'organizer':SimpleNamespace(permissions=('red','app'))},get_config=lambda key:None)
        app=web.Application();api.register_routes({'app_svc':SimpleNamespace(application=app),'auth_svc':auth},AdminClient(path))
        client=TestClient(TestServer(app));await client.start_server();self.addAsyncCleanup(client.close)
        async def identity(request):return 'organizer'
        with patch.object(api,'authorized_userid',identity):
            for action,want in [('load','DISARMED'),('start','RUNNING'),('pause','PAUSED'),('resume','RUNNING'),('stop','STOPPED')]:
                status=await (await client.get('/plugin/ccdc/api/status')).json();status=status['data']
                args={'profile_id':'test','revision':1} if action=='load' else {}
                body={'args':args,'expected_exercise_id':status['exercise']['id'],'expected_lifecycle_revision':status['lifecycle_revision'],'idempotency_key':action+'a'*20}
                response=await client.post('/plugin/ccdc/api/exercise/'+action,json=body,headers={'Origin':str(client.make_url('/')).rstrip('/'),'X-CCDC-Request':'1'})
                self.assertEqual(response.status,200,await response.text())
                status=(await (await client.get('/plugin/ccdc/api/status')).json())['data']
                self.assertEqual(status['exercise']['state'],want)
            self.assertEqual(fixture.engine.scenario,[fixture.event])

if __name__=='__main__':unittest.main()
