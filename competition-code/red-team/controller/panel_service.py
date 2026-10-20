"""Management operations serialized with guest dispatch and acceptance."""
import hashlib
import json
import re
import time
from panel_catalog import PanelError, build_catalog, validate_profile
from panel_store import encode

READS = {'bootstrap', 'status', 'profiles.list', 'profiles.read'}
FIELDS = {'bootstrap': set(), 'status': set(), 'profiles.list': set(),
          'profiles.read': {'profile_id', 'revision'}, 'profiles.create': {'document'},
          'profiles.save': {'profile_id', 'expected_profile_revision', 'document'},
          'profiles.duplicate': {'profile_id', 'expected_profile_revision', 'name'},
          'exercise.load': {'profile_id', 'revision'}, 'exercise.start': set(),
          'exercise.pause': set(), 'exercise.resume': set(), 'exercise.stop': set()}


class PanelService:
    def __init__(self, core, panel_store, clock=time.time, guests=None, score_details=None):
        self.core, self.ps, self.clock = core, panel_store, clock
        self.guests = guests or core.guests
        self.score_details = score_details

    def catalog(self): return build_catalog(self.guests, self.guests)

    @staticmethod
    def current(tx):
        row = tx.execute('SELECT * FROM exercises ORDER BY rowid DESC LIMIT 1').fetchone()
        return dict(row) if row else None

    def status(self, tx):
        exercise = self.current(tx)
        if exercise: exercise.pop('last_tick', None)
        snapshot = None
        if exercise:
            row = tx.execute('SELECT * FROM panel_snapshots WHERE exercise=?', (exercise['id'],)).fetchone()
            if row: snapshot = dict(profile_id=row['profile'], revision=row['revision'], document=json.loads(row['document']))
        events = [dict(row) for row in tx.execute('SELECT event,outcome FROM dispatch WHERE exercise=?', (exercise['id'] if exercise else '',))]
        score = self.core.score()
        scoring = dict(available=score is not None, fresh=score is not None, id=score['id'] if score else None,
                       state=score['state'] if score else None, age=None)
        if self.score_details:
            try: scoring.update(self.score_details())
            except Exception: pass
        health = []
        for guest in self.guests:
            report = self.core.health_reports.get(guest)
            age = max(0, self.clock() - report[0]) if report else None
            health.append(dict(guest=guest, enrolled=True, healthy=self.core.healthy(guest), age=age,
                               business_enabled=self.guests[guest].get('business_enabled') is True,
                               hour4_enabled=self.guests[guest].get('hour4_enabled') is True))
        return dict(exercise=exercise, lifecycle_revision=tx.execute('SELECT lifecycle_revision FROM panel_meta WHERE id=1').fetchone()[0],
                    snapshot=snapshot, outcomes=events, scoring=scoring, guests=health)

    def handle(self, request, actor):
        try:
            if not isinstance(request, dict) or not isinstance(actor, str) or not 1 <= len(actor) <= 128:
                raise PanelError('invalid', 'Invalid management request')
            op, args = request.get('op'), request.get('args')
            if not isinstance(op, str) or op not in FIELDS or not isinstance(args, dict):
                raise PanelError('invalid', 'Unsupported operation')
            fields = {'op', 'args'} if op in READS else {'op', 'args', 'expected_exercise_id', 'expected_lifecycle_revision', 'idempotency_key'}
            if set(request) != fields or set(args) != FIELDS[op]:
                raise PanelError('invalid', 'Unexpected or missing request fields')
            with self.core.lock:
                self.core.engine.heartbeat(self.core.score())
                if op in READS:
                    if op == 'profiles.list': data = {'profiles': self.ps.list_profiles()}
                    elif op == 'profiles.read': data = self.ps.read_profile(args['profile_id'], args['revision'])
                    else:
                        with self.ps.store.transaction() as tx: data = self.status(tx)
                        if op == 'bootstrap': data.update(catalog=self.catalog(), profiles=self.ps.list_profiles())
                    return {'ok': True, 'data': data}
                key = request['idempotency_key']
                if not isinstance(key, str) or not re.fullmatch('[A-Za-z0-9_-]{16,64}', key):
                    raise PanelError('invalid', 'Invalid idempotency key')
                digest = hashlib.sha256(encode(dict(request=request, actor=actor)).encode()).hexdigest()
                new_scenario = None
                with self.ps.store.transaction() as tx:
                    tx.execute('DELETE FROM panel_idempotency WHERE created<?', (self.clock() - 86400,))
                    prior = tx.execute('SELECT body,result FROM panel_idempotency WHERE key=?', (key,)).fetchone()
                    if prior:
                        if prior['body'] != digest: raise PanelError('conflict', 'Idempotency key was used for a different request')
                        return json.loads(prior['result'])
                    current = self.current(tx)
                    revision = tx.execute('SELECT lifecycle_revision FROM panel_meta WHERE id=1').fetchone()[0]
                    if (type(request['expected_lifecycle_revision']) is not int or request['expected_lifecycle_revision'] != revision
                        or request['expected_exercise_id'] != (current['id'] if current else None)):
                        raise PanelError('conflict', 'Exercise changed; refresh before controlling it')
                    if op == 'profiles.create':
                        data = self.ps.write_profile(tx, None, None, validate_profile(args['document'], self.catalog()))
                    elif op == 'profiles.save':
                        data = self.ps.write_profile(tx, args['profile_id'], args['expected_profile_revision'], validate_profile(args['document'], self.catalog()))
                    elif op == 'profiles.duplicate':
                        original = self.ps.read_profile(args['profile_id'], None, tx)
                        if type(args['expected_profile_revision']) is not int or original['revision'] != args['expected_profile_revision']: raise PanelError('conflict', 'Profile changed')
                        document = dict(original['document'], name=args['name'])
                        data = self.ps.write_profile(tx, None, None, validate_profile(document, self.catalog()))
                    elif op == 'exercise.load':
                        profile = self.ps.read_profile(args['profile_id'], args['revision'], tx)
                        validate_profile(profile['document'], self.catalog())
                        score = self.core.score()
                        if score is None: raise PanelError('invalid', 'A fresh scoring event is required to load')
                        data = self.ps.load_snapshot(tx, args['profile_id'], args['revision'], score['id'])
                        new_scenario = data['document']['events']
                    else:
                        if current is None: raise PanelError('invalid', 'Load a profile first')
                        action = op.split('.')[1]
                        expected_states = {'start': ('DISARMED',), 'resume': ('PAUSED',), 'pause': ('RUNNING',), 'stop': ('DISARMED', 'RUNNING', 'PAUSED')}
                        if current['state'] not in expected_states[action]: raise PanelError('conflict', 'Invalid lifecycle transition')
                        if action in ('start', 'resume'):
                            row = tx.execute('SELECT document FROM panel_snapshots WHERE exercise=?', (current['id'],)).fetchone()
                            if not row: raise PanelError('invalid', 'Load a validated profile first')
                            document = validate_profile(json.loads(row['document']), self.catalog())
                            if not document['events']: raise PanelError('invalid', 'An empty profile cannot start')
                            if self.core.score() != {'id': current['scoring_event_id'], 'state': 'RUNNING'}:
                                raise PanelError('invalid', 'Matching fresh RUNNING scoring event required')
                        target = {'start':'RUNNING', 'resume':'RUNNING', 'pause':'PAUSED', 'stop':'STOPPED'}[action]
                        tx.execute('UPDATE exercises SET state=?,last_tick=? WHERE id=?',
                                   (target, self.core.engine.clock() if target == 'RUNNING' else None, current['id']))
                        if target != 'RUNNING': self.core.engine.revoke(tx, current['id'])
                        self.ps.store.audit(tx, current['id'], None, target)
                        data = {'exercise_id': current['id'], 'state': target}
                    result = {'ok': True, 'data': data}
                    tx.execute('INSERT INTO panel_admin_audit(created,actor,op,exercise) VALUES(?,?,?,?)',
                               (self.clock(), actor, op, data.get('exercise_id', current['id'] if current else None)))
                    tx.execute('DELETE FROM panel_admin_audit WHERE id NOT IN (SELECT id FROM panel_admin_audit ORDER BY id DESC LIMIT 10000)')
                    tx.execute('INSERT INTO panel_idempotency VALUES(?,?,?,?)', (key, digest, encode(result), self.clock()))
                    tx.execute('DELETE FROM panel_idempotency WHERE key NOT IN (SELECT key FROM panel_idempotency ORDER BY created DESC,rowid DESC LIMIT 10000)')
                if new_scenario is not None: self.core.engine.scenario = new_scenario
                return result
        except PanelError as error:
            return {'ok': False, 'error': dict(code=error.code, message=error.message, rows=error.rows)}
        except (ValueError, TypeError, KeyError):
            return {'ok': False, 'error': dict(code='invalid', message='Invalid management arguments', rows=[])}
