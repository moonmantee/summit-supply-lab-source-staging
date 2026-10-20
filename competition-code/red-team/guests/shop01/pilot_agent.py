"""Visible, finite CALDERA-compatible pilot. Fixed read-only checks; no shell or payloads."""
import argparse
import base64
import getpass
import json
import itertools
import os
import pathlib
import platform
import socket
import ssl
import time
import urllib.request


def fixed_check(command):
    if command == 'summit-pilot hostname':
        return 0, socket.gethostname()
    if command == 'summit-pilot os':
        return 0, platform.system() + ' ' + platform.release()
    if command == 'summit-pilot marker':
        return 0, 'SUMMIT CALDERA PILOT OK'
    return 1, 'Unsupported pilot instruction'


def answer_instruction(instruction):
    status, output = 1, 'Unsupported pilot instruction'
    if (instruction.get('executor') == 'summit-pilot' and not instruction.get('payloads')
            and not instruction.get('uploads') and not instruction.get('deadman')):
        try:
            command = base64.b64decode(instruction['command'], validate=True).decode()
            status, output = fixed_check(command)
        except Exception:
            pass
    return {'id': instruction['id'], 'pid': os.getpid(), 'status': status, 'exit_code': str(status),
            'output': base64.b64encode(output.encode()).decode(), 'stderr': ''}


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        raise ValueError('Pilot endpoint redirects are forbidden')


def poll(config, polls, instruction_handler=answer_instruction, before_poll=None):
    endpoint = config['endpoint']
    if endpoint != 'https://10.77.70.20:8771/beacon':
        raise ValueError('Unexpected pilot endpoint')
    context = ssl.create_default_context(cafile=config['ca'])
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    context.load_cert_chain(config['certificate'], config['key'])
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}),
                                        urllib.request.HTTPSHandler(context=context), NoRedirect())
    profile = {'paw': config['paw'], 'host': socket.gethostname(), 'group': 'summit-pilot',
               'platform': 'linux', 'architecture': platform.machine(), 'username': getpass.getuser(),
               'location': str(pathlib.Path(__file__).resolve()), 'pid': os.getpid(), 'ppid': os.getppid(),
               'executors': ['summit-pilot'], 'privilege': 'User', 'exe_name': 'summit-caldera-pilot',
               'contact': 'http', 'deadman_enabled': False, 'available_contacts': ['http']}
    pending = []
    answers = {}
    for _ in (range(polls) if polls is not None else itertools.count()):
        if before_poll:
            before_poll()
        request = urllib.request.Request(endpoint, base64.b64encode(json.dumps({**profile, 'results': pending}).encode()),
                                         headers={'Content-Type': 'text/plain'})
        with opener.open(request, timeout=8) as response:
            if response.status != 200:
                raise RuntimeError('Contact rejected')
            blob = response.read(131073)
        if len(blob) > 131072:
            raise ValueError('Oversize response')
        message = json.loads(base64.b64decode(blob, validate=True))
        if message.get('paw') != config['paw'] or message.get('new_contact') or message.get('executor_change'):
            raise ValueError('Unexpected identity/contact/executor change')
        pending = []
        instructions = json.loads(message.get('instructions', '[]'))
        if len(instructions) > 16:
            raise ValueError('Oversize instruction batch')
        for item in instructions:
            item = json.loads(item) if isinstance(item, str) else item
            if item['id'] not in answers:
                answers[item['id']] = instruction_handler(item)
            pending.append(answers[item['id']])
            print(json.dumps({'link': item['id'], 'status': answers[item['id']]['status']}), flush=True)
        if len(answers) > 256:
            raise RuntimeError('Pilot result limit reached')
        time.sleep(2)
    if pending:
        raise RuntimeError('Pilot ended with unacknowledged results; rerun only after reconciliation')
    print('Pilot finished; no background service or fixture action remains.', flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', required=True)
    parser.add_argument('--polls', type=int, default=60)
    args = parser.parse_args()
    if not 1 <= args.polls <= 300:
        raise SystemExit('Pilot polls must be between1 and300')
    with open(args.config) as file:
        config = json.load(file)
    poll(config, args.polls)
