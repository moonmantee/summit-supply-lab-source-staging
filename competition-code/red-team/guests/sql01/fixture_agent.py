"""Visible unprivileged CALDERA contact; fixed pilot checks and event-ID broker calls."""
import argparse
import base64
import json
import os
import pathlib
import socket
from fixture_contract import parse_command,strict_json
from pilot_agent import poll,answer_instruction

def local_request(body):
    data=json.dumps(body).encode()+b'\n'
    if len(data)>512:raise ValueError('Oversize broker request')
    with socket.socket(socket.AF_UNIX,socket.SOCK_STREAM) as connection:
        connection.settimeout(20)
        connection.connect('/run/summit-caldera-broker/broker.sock')
        connection.sendall(data)
        with connection.makefile('rb') as stream:
            response=stream.readline(4097)
    if len(response)>4096 or not response.endswith(b'\n'):raise ValueError('Invalid broker reply')
    return strict_json(response)

def answer_fixture(instruction):
    if (instruction.get('executor')!='summit-pilot' or instruction.get('payloads')
            or instruction.get('uploads') or instruction.get('deadman')):
        return answer_instruction(instruction)
    try:command=base64.b64decode(instruction['command'],validate=True).decode()
    except Exception:return answer_instruction(instruction)
    if not command.startswith('summit-fixture '):return answer_instruction(instruction)
    try:
        exercise,event=parse_command(command)
        result=local_request({'exercise':exercise,'id':event})
        status=0 if result.get('outcome')=='APPLIED' and result.get('acknowledged') is True else 1
    except Exception:result={'outcome':'REJECTED','acknowledged':False};status=1
    return {'id':instruction['id'],'pid':os.getpid(),'status':status,'exit_code':str(status),
            'output':base64.b64encode(json.dumps(result).encode()).decode(),'stderr':''}

def heartbeat():
    try:local_request({'status':True})
    except Exception:pass

def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--config',required=True)
    parser.add_argument('--polls',type=int);args=parser.parse_args()
    if args.polls is not None and not 1<=args.polls<=300:raise ValueError('Invalid finite poll count')
    config=strict_json(pathlib.Path(args.config).read_bytes())
    poll(config,args.polls,instruction_handler=answer_fixture,before_poll=heartbeat)

if __name__=='__main__':main()
