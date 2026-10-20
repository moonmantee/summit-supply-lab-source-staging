"""Preserve unrelated policy while replacing explicitly scoped settings."""
def update_policy(text,values):
    counts={key:0 for key in values}
    lines=[]
    for raw in text.splitlines():
        active=raw.split('#',1)[0].strip()
        key=active.split('=',1)[0].strip()
        if key in values:
            counts[key]+=1
            if counts[key]>1:
                raise ValueError('Duplicate active policy setting: '+key)
        else:
            lines.append(raw)
    lines+=['# Summit local password-policy scenario']
    lines+=[key if value is None else key+' = '+str(value) for key,value in values.items()]
    return '\n'.join(lines)+'\n'


def faillock_count(text,user):
    import re
    if not isinstance(text,str): raise ValueError('Unreadable failure tally')
    lines=[line.strip() for line in text.splitlines() if line.strip()]
    if not lines: return 0
    if len(lines)<2 or lines[0]!=user+':' or lines[1].split()!=['When','Type','Source','Valid']:
        raise ValueError('Unexpected tally identity/header')
    count=0
    for line in lines[2:]:
        match=re.fullmatch(r'\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\s+(?:SVC|TTY|RHOST)\s+\S+\s+([VI])',line)
        if match is None: raise ValueError('Unrecognized tally record')
        count+=match.group(1)=='V'
    return count
