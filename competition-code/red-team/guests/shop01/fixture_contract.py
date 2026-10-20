"""Fixed event-ID contract shared by the coordinator, agent and privileged broker."""
import json
import re
import ssl
import urllib.request

IDENTIFIER=re.compile(r'[A-Za-z0-9_-]{1,64}\Z')

def identifiers(exercise,event):
    if not all(isinstance(value,str) and IDENTIFIER.fullmatch(value) for value in (exercise,event)):
        raise ValueError('Invalid event identity')
    return exercise,event

def parse_command(command):
    parts=command.split(' ')
    if len(parts)!=3 or parts[0]!='summit-fixture': raise ValueError('Unsupported fixture instruction')
    return identifiers(parts[1],parts[2])

def strict_json(blob):
    def pairs(values):
        result={}
        for key,value in values:
            if key in result: raise ValueError('Duplicate JSON member')
            result[key]=value
        return result
    def invalid(value): raise ValueError('Nonfinite JSON value')
    return json.loads(blob,object_pairs_hook=pairs,parse_constant=invalid)

class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs): raise ValueError('Redirect forbidden')

def authorization_transport(config):
    if config['endpoint']!='https://10.77.70.20:8772': raise ValueError('Unexpected authorization origin')
    context=ssl.create_default_context(cafile=config['ca'])
    context.minimum_version=ssl.TLSVersion.TLSv1_2
    context.load_cert_chain(config['certificate'],config['key'])
    opener=urllib.request.build_opener(urllib.request.ProxyHandler({}),
        urllib.request.HTTPSHandler(context=context),NoRedirect())
    def call(route,payload):
        if route not in ('/event','/accept','/ack','/status'): raise ValueError('Unknown authorization route')
        body=json.dumps(payload,allow_nan=False).encode()
        if len(body)>512: raise ValueError('Oversize authorization request')
        request=urllib.request.Request(config['endpoint']+route,body,headers={'Content-Type':'application/json'})
        with opener.open(request,timeout=4) as response:
            blob=response.read(4097)
            if response.status!=200 or len(blob)>4096: raise ValueError('Authorization rejected')
        result=strict_json(blob)
        if not isinstance(result,dict): raise ValueError('Invalid authorization response')
        return result
    return call
