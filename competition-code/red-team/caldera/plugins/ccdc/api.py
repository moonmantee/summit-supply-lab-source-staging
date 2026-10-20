"""Authenticated narrow API; all control authority remains in the coordinator."""
import asyncio
import json
from aiohttp import web
from aiohttp_security import authorized_userid
from app.utility.config_util import verify_hash
from .client import Client

LIMIT = 256 * 1024


def strict_json(raw):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result: raise ValueError('Duplicate field')
            result[key] = value
        return result
    def invalid(value): raise ValueError('Nonfinite value')
    return json.loads(raw, object_pairs_hook=pairs, parse_constant=invalid)


async def authenticated_actor(request, auth):
    key = request.headers.get('KEY')
    if key is not None:
        hashed = auth.get_config('api_key_red')
        if not hashed or not verify_hash(hashed, key): raise web.HTTPForbidden(text='Red authorization required')
        return 'api:red'
    identity = await authorized_userid(request)
    if identity is None: raise web.HTTPUnauthorized(text='Sign in required')
    user = auth.user_map.get(identity)
    if user is None or 'red' not in user.permissions: raise web.HTTPForbidden(text='Red authorization required')
    return 'session:' + identity


async def socket_call(client, request, actor):
    return await asyncio.to_thread(client.call, request, actor)


def register_routes(services, client=None):
    app, auth = services['app_svc'].application, services['auth_svc']
    client = client or Client()
    semaphore = asyncio.Semaphore(4)

    async def handler(request):
        actor = await authenticated_actor(request, auth)
        op = request.match_info.route.resource.get_info().get('path', '')
        path = request.path
        prefix = '/plugin/ccdc/api/'
        tail = path[len(prefix):]
        mutating = request.method != 'GET'
        profile_id = request.match_info.get('profile_id')
        if tail in ('bootstrap', 'status'): op = tail
        elif tail == 'profiles': op = 'profiles.list' if not mutating else 'profiles.create'
        elif profile_id:
            op = 'profiles.duplicate' if tail.endswith('/duplicate') else 'profiles.read' if not mutating else 'profiles.save'
        else:
            action = request.match_info.get('action')
            if action not in ('load', 'start', 'pause', 'resume', 'stop'): raise web.HTTPNotFound()
            op = 'exercise.'+action
        if mutating:
            if request.headers.get('X-CCDC-Request') != '1': raise web.HTTPForbidden(text='Request header required')
            origin = request.headers.get('Origin')
            if actor != 'api:red' or origin is not None:
                if origin != request.scheme+'://'+request.host: raise web.HTTPForbidden(text='Same origin required')
            if request.headers.get('Sec-Fetch-Site') not in (None, 'same-origin', 'none'):
                raise web.HTTPForbidden(text='Same origin required')
            if request.content_type != 'application/json': raise web.HTTPUnsupportedMediaType()
            if request.content_length and request.content_length > LIMIT: raise web.HTTPRequestEntityTooLarge(max_size=LIMIT, actual_size=request.content_length)
            raw = bytearray()
            async for chunk in request.content.iter_chunked(16384):
                raw.extend(chunk)
                if len(raw)>LIMIT: raise web.HTTPRequestEntityTooLarge(max_size=LIMIT, actual_size=len(raw))
            try:
                body = strict_json(raw)
                if not isinstance(body, dict) or set(body) != {'args','expected_exercise_id','expected_lifecycle_revision','idempotency_key'} or not isinstance(body['args'], dict): raise ValueError()
                if profile_id:
                    if 'profile_id' in body['args']: raise ValueError()
                    body['args']['profile_id'] = profile_id
                envelope = dict(body, op=op)
            except (ValueError, TypeError): raise web.HTTPBadRequest(text='Invalid request fields')
        else:
            args = {}
            if profile_id:
                try: revision = int(request.query['revision']) if 'revision' in request.query else None
                except ValueError: raise web.HTTPBadRequest(text='Invalid revision')
                args = {'profile_id':profile_id, 'revision':revision}
            envelope = {'op':op, 'args':args}
        try:
            async with semaphore: result = await socket_call(client, envelope, actor)
        except (OSError, ValueError, TimeoutError):
            result = dict(ok=False, error=dict(code='unavailable', message='Controller unavailable; last displayed state may be stale', rows=[]))
        code = 200 if result['ok'] else {'invalid':400,'conflict':409,'unauthorized':403,'unavailable':503,'low_disk':507,'limit':413}.get(result['error']['code'],400)
        return web.json_response(result, status=code, headers={'Cache-Control':'no-store'})

    base = '/plugin/ccdc/api'
    for tail in ('bootstrap','status','profiles'): app.router.add_get(base+'/'+tail, handler)
    app.router.add_post(base+'/profiles', handler)
    app.router.add_get(base+'/profiles/{profile_id}', handler)
    app.router.add_put(base+'/profiles/{profile_id}', handler)
    app.router.add_post(base+'/profiles/{profile_id}/duplicate', handler)
    app.router.add_post(base+'/exercise/{action}', handler)
