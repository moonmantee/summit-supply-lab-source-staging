"""Pure transformations for the reviewed application weakness batch."""
import configparser
import copy
import re

KEYS=('browser.safebrowsing.phishing.enabled','browser.safebrowsing.malware.enabled','browser.safebrowsing.downloads.enabled')


def firefox_state(data,protected):
    result=copy.deepcopy(data)
    if not isinstance(result,dict):
        raise ValueError('Firefox policy must be an object')
    policies=result.setdefault('policies',{})
    if not isinstance(policies,dict):
        raise ValueError('Malformed Firefox policies')
    prefs=policies.setdefault('Preferences',{})
    if not isinstance(prefs,dict):
        raise ValueError('Malformed Firefox preferences')
    for key in KEYS:
        prefs[key]={'Value':protected,'Status':'locked'}
    return result


def dnf_state(original,blocked):
    try:
        cfg=configparser.ConfigParser(interpolation=None,strict=True)
        cfg.read_string(original)
        if not cfg.has_section('main'):
            raise ValueError('Missing DNF main section')
        if not blocked:
            return original
        existing=cfg.get('main','exclude',fallback='').strip()
        value=' '.join(v for v in (existing,'firefox gedit') if v)
        lines=original.splitlines(keepends=True)
        section=None
        start=None
        replaced=False
        for i,line in enumerate(lines):
            match=re.match(r'^\s*\[([^]]+)\]',line)
            if match:
                section=match.group(1)
                if section=='main':
                    start=i+1
            elif section=='main' and re.match(r'^\s*exclude\s*[=:]',line):
                lines[i]='exclude='+value+'\n'
                replaced=True
        if not replaced:
            lines.insert(start,'exclude='+value+'\n')
        result=''.join(lines)
        verify=configparser.ConfigParser(interpolation=None,strict=True)
        verify.read_string(result)
        if verify.get('main','exclude')!=value:
            raise ValueError('Failed DNF transformation')
        return result
    except configparser.Error as error:
        raise ValueError('Malformed DNF configuration') from error
