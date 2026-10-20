import pathlib
import sys
import unittest
from types import SimpleNamespace
from unittest.mock import patch
from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer
ROOT=pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'payload/caldera'))
sys.path.append(str(ROOT/'upstream-test-support'))
try:
    from plugins.ccdc import api
except ImportError: api=None


class ApiTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.assertIsNotNone(api, 'CCDC API missing')
        self.requests=[]
        owner=self
        class Client:
            def call(self, request, actor):
                owner.requests.append((request,actor))
                return {'ok':True,'data':{'safe':True}}
        self.auth=SimpleNamespace(user_map={'organizer':SimpleNamespace(permissions=('red','app')), 'blue':SimpleNamespace(permissions=('blue','app'))},get_config=lambda key:None)
        app=web.Application(); api.register_routes({'app_svc':SimpleNamespace(application=app),'auth_svc':self.auth},Client())
        self.client=TestClient(TestServer(app)); await self.client.start_server(); self.addAsyncCleanup(self.client.close)
        async def identity(request): return request.headers.get('Test-Identity')
        self.patch=patch.object(api,'authorized_userid',identity); self.patch.start(); self.addCleanup(self.patch.stop)

    async def test_anonymous_blue_and_red(self):
        for user,status in [(None,401),('blue',403),('organizer',200)]:
            headers={'Test-Identity':user} if user else {}
            response=await self.client.get('/plugin/ccdc/api/status',headers=headers)
            self.assertEqual(response.status,status)
        self.assertEqual(self.requests[-1][1],'session:organizer')

    async def test_mutation_protections(self):
        base={'Test-Identity':'organizer','X-CCDC-Request':'1','Origin':str(self.client.make_url('/')).rstrip('/')}
        body={'expected_exercise_id':'old','expected_lifecycle_revision':1,'idempotency_key':'a'*32,'args':{}}
        for changes,status in [({'Origin':'https://evil.test'},403),({'X-CCDC-Request':''},403),({'Origin':''},403),({'Sec-Fetch-Site':'cross-site'},403)]:
            response=await self.client.post('/plugin/ccdc/api/exercise/pause',json=body,headers=dict(base,**changes))
            self.assertEqual(response.status,status)
        response=await self.client.post('/plugin/ccdc/api/exercise/pause',json=body,headers=base)
        self.assertEqual(response.status,200)
        self.assertEqual(self.requests[-1][0]['op'],'exercise.pause')
        response=await self.client.post('/plugin/ccdc/api/exercise/pause',json=dict(body,actor='root'),headers=base)
        self.assertEqual(response.status,400)

    async def test_non_json_and_unknown_action(self):
        headers={'Test-Identity':'organizer','X-CCDC-Request':'1','Origin':str(self.client.make_url('/')).rstrip('/')}
        self.assertEqual((await self.client.post('/plugin/ccdc/api/exercise/pause',data='{}',headers=headers)).status,415)
        self.assertEqual((await self.client.post('/plugin/ccdc/api/exercise/systemctl',json={},headers=headers)).status,404)

    async def test_unavailable_is_not_disarmed(self):
        with patch.object(api,'socket_call',side_effect=OSError('private path sentinel')):
            response=await self.client.get('/plugin/ccdc/api/status',headers={'Test-Identity':'organizer'})
        self.assertEqual(response.status,503)
        value=await response.text()
        self.assertNotIn('DISARMED',value); self.assertNotIn('private path sentinel',value)

    async def test_red_api_and_blue_api(self):
        from argon2 import PasswordHasher
        hashed=PasswordHasher().hash('test-red-key')
        self.auth.get_config=lambda key:hashed
        for key,status in [('test-red-key',200),('test-blue-key',403)]:
            response=await self.client.get('/plugin/ccdc/api/status',headers={'KEY':key})
            self.assertEqual(response.status,status)
        self.assertEqual(self.requests[-1][1],'api:red')

    async def test_oversized_and_duplicate_json(self):
        headers={'Test-Identity':'organizer','X-CCDC-Request':'1','Origin':str(self.client.make_url('/')).rstrip('/'),'Content-Type':'application/json'}
        response=await self.client.post('/plugin/ccdc/api/profiles',data='x'*262145,headers=headers)
        self.assertEqual(response.status,413)
        response=await self.client.post('/plugin/ccdc/api/profiles',data='{"args":{},"args":{}}',headers=headers)
        self.assertEqual(response.status,400)

if __name__=='__main__':unittest.main()
