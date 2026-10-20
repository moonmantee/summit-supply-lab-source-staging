"""Organizer controls through the coordinator's private management socket."""
import argparse
import json
import os
import uuid
from panel_client import AdminClient


def checked(client, request):
    result = client.call(request)
    if not result['ok']: raise ValueError(result['error']['message'])
    return result['data']


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=('status','load','start','pause','resume','stop'))
    parser.add_argument('profile', nargs='?')
    args = parser.parse_args()
    if os.geteuid() != 0: raise ValueError('Organizer root required')
    client = AdminClient()
    status = checked(client, {'op':'status','args':{}})
    if args.command == 'status':
        print(json.dumps(status)); return
    fields = {}
    if args.command == 'load':
        if not args.profile: raise ValueError('Choose a profile ID')
        if args.profile in ('first3h-rehearsal','first3h-sql01-rehearsal','first3h-linux-rehearsal'):
            raise ValueError('Historical timed-repair profiles remain disabled')
        profile = checked(client, {'op':'profiles.read','args':{'profile_id':args.profile,'revision':None}})
        fields = {'profile_id':profile['id'],'revision':profile['revision']}
    request = {'op':'exercise.'+args.command,'args':fields,
               'expected_exercise_id':status['exercise']['id'] if status['exercise'] else None,
               'expected_lifecycle_revision':status['lifecycle_revision'], 'idempotency_key':uuid.uuid4().hex}
    print(json.dumps(checked(client, request)))

if __name__ == '__main__': main()
