import time


class Engine:
    def __init__(self, store, scenario, clock=None, wall_clock=None):
        self.store, self.scenario = store, scenario
        self.clock = clock or time.monotonic
        self.wall_clock = wall_clock or (clock if clock is not None else time.time)

    def recover_restart(self):
        with self.store.transaction() as c:
            c.execute("UPDATE dispatch SET outcome='REVOKED' WHERE outcome='DISPATCHED' "
                      "AND exercise IN (SELECT id FROM exercises WHERE state='RUNNING')")
            c.execute("UPDATE exercises SET state='PAUSED',last_tick=NULL WHERE state='RUNNING'")

    @staticmethod
    def revoke(c, eid):
        c.execute("UPDATE dispatch SET outcome='REVOKED' WHERE exercise=? AND outcome='DISPATCHED'", (eid,))

    def heartbeat(self, scoring_state):
        with self.store.transaction() as c:
            ids = [r['id'] for r in c.execute("SELECT id FROM exercises WHERE state='RUNNING'")]
        for eid in ids:
            self.next_event(eid, '__monitor__', scoring_state)

    def _tick(self, c, e):
        now = self.clock()
        if e['state'] == 'RUNNING':
            delta = now - e['last_tick']
            if delta < 0:
                e['state'] = 'STOPPED'
            else:
                e['elapsed'] += delta
                if e['elapsed'] >= e['duration']:
                    e['state'] = 'FINISHED'
            e['last_tick'] = now
            c.execute('UPDATE exercises SET state=?,elapsed=?,last_tick=? WHERE id=?',
                      (e['state'], e['elapsed'], now, e['id']))
            if e['state'] != 'RUNNING':
                self.revoke(c, e['id'])
        return now

    def transition(self, eid, action):
        with self.store.transaction() as c:
            row = c.execute('SELECT * FROM exercises WHERE id=?', (eid,)).fetchone()
            if row is None:
                raise ValueError('unknown exercise')
            e = dict(row)
            self._tick(c, e)
            valid = {'start': ('DISARMED', 'PAUSED'), 'pause': ('RUNNING',),
                     'stop': ('DISARMED', 'RUNNING', 'PAUSED')}
            if action not in valid or e['state'] not in valid[action]:
                raise ValueError('invalid lifecycle transition')
            target = {'start': 'RUNNING', 'pause': 'PAUSED', 'stop': 'STOPPED'}[action]
            c.execute('UPDATE exercises SET state=?,last_tick=? WHERE id=?',
                      (target, self.clock() if action == 'start' else None, eid))
            if target != 'RUNNING':
                self.revoke(c, eid)
            self.store.audit(c, eid, None, target)
        return self.store.status(eid)

    def next_event(self, eid, guest, scoring_state):
        with self.store.transaction() as c:
            row = c.execute('SELECT * FROM exercises WHERE id=?', (eid,)).fetchone()
            if row is None:
                raise ValueError('unknown exercise')
            e = dict(row)
            now = self._tick(c, e)
            if e['state'] != 'RUNNING':
                return None
            if scoring_state is None or scoring_state['id'] != e['scoring_event_id']:
                c.execute("UPDATE exercises SET state='STOPPED',last_tick=NULL WHERE id=?", (eid,))
                self.revoke(c, eid)
                self.store.audit(c, eid, None, 'EVENT_MISMATCH_OR_UNAVAILABLE')
                return None
            if scoring_state['state'] != 'RUNNING':
                c.execute("UPDATE exercises SET state='PAUSED',last_tick=NULL WHERE id=?", (eid,))
                self.revoke(c, eid)
                return None
            due = [a for a in self.scenario if a['guest'] == guest and a['at'] <= e['elapsed']]
            newest = max(due, key=lambda x: (x['at'], x['id']))['id'] if due else None
            for action in sorted(self.scenario, key=lambda x: (x['at'], x['id'])):
                if action['guest'] != guest or e['elapsed'] < action['at']:
                    continue
                if c.execute('SELECT 1 FROM dispatch WHERE exercise=? AND event=?', (eid, action['id'])).fetchone():
                    continue
                expired = e['elapsed'] >= action['at'] + action['window']
                missed = action['id'] != newest
                expires = self.wall_clock() + min(15, max(0, action['at'] + action['window'] - e['elapsed']))
                outcome = 'EXPIRED' if expired else 'MISSED' if missed else 'DISPATCHED'
                c.execute('INSERT INTO dispatch VALUES(?,?,?,?,?)',
                          (eid, action['id'], guest, outcome, expires))
                self.store.audit(c, eid, action['id'], outcome)
                if not expired and not missed:
                    event={'exercise': eid, 'id': action['id'], 'guest': guest,
                           'action': action['action'], 'target': action['target'], 'expires': expires}
                    if action['action'] in ('service_stop','service_disable','service_config','service_executable','service_definition','business_stop','business_disable','business_restart_off','business_binary_rename','business_launch_fault'):event['duration']=action['duration']
                    return event
        return None
