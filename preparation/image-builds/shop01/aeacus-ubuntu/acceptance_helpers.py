import re


def scenario_fingerprint(root):
    import hashlib
    files=[root/name for name in ('competition-manifest.json','build_config.py','ReadMe.conf')]
    files+=sorted(p for p in (root/'probes').glob('*.py') if not p.name.startswith('test_'))
    return {str(p.relative_to(root)):hashlib.sha256(p.read_bytes()).hexdigest() for p in files}


def require_state(data, secure):
    rows=data.get('checks',[])
    if (data.get('count')!=40 or data.get('total_points')!=100 or
        data.get('expected_points')!=(100 if secure else 0) or len(rows)!=40 or
        {r.get('id') for r in rows}!=set(range(1,41)) or
        any(r.get('status')!=('PASS' if secure else 'FAIL') for r in rows)):
        raise ValueError('Expected all forty '+('PASS / 100 points' if secure else 'FAIL / zero points'))

def secure_pam(auth, account, password):
    def replace(pattern,replacement,text):
        text,count=re.subn(pattern,replacement,text,flags=re.M)
        if count!=1: raise ValueError('Unknown original PAM layout')
        return text
    password=replace(r'^password\s+requisite\s+pam_pwquality[.]so[^\n]*$',
        'password requisite pam_pwquality.so retry=1 local_users_only minlen=14 enforcing=1 dcredit=0 ucredit=0 lcredit=0 ocredit=0',password)
    password=replace(r'^(password\s+\[success=2 default=ignore\]\s+pam_unix[.]so[^\n]*)$',
        lambda m:'password [success=ok default=1] pam_localuser.so\npassword required pam_pwhistory.so use_authtok remember=5\n'+m[1].replace('obscure ',''),password)
    auth=replace(r'^auth\s+\[success=2 default=ignore\]\s+pam_unix[.]so nullok$',
        'auth [success=ok default=1] pam_localuser.so\nauth required pam_faillock.so preauth silent\nauth [success=3 default=ignore] pam_unix.so nullok',auth)
    auth=replace(r'^auth\s+\[success=1 default=ignore\]\s+pam_sss[.]so use_first_pass$',
        'auth [success=2 default=ignore] pam_sss.so use_first_pass\nauth [default=die] pam_faillock.so authfail',auth)
    auth=replace(r'^(auth\s+required\s+pam_permit[.]so[^\n]*)$',r'auth required pam_faillock.so authsucc\n\1',auth)
    return auth,'account required pam_faillock.so\n'+account,password

def secure_apache(original):
    if original.count('<VirtualHost')!=2 or '<VirtualHost *:443>' not in original:
        raise ValueError('Unknown original Apache virtual hosts')
    head,closing=original.rsplit('</VirtualHost>',1)
    if 'SSLEngine on' not in head.rsplit('<VirtualHost',1)[1]:
        raise ValueError('Original HTTPS virtual host required')
    return head+'''
    <Directory /var/www/summit/training-fixtures/listing>
        Options -Indexes
        Require all granted
    </Directory>
    <Directory /var/www/summit/training-fixtures>
        <FilesMatch "^(public-backup[.]sql|[.]private-note)$">
            Require all denied
        </FilesMatch>
    </Directory>
    <Location /server-status>
        SetHandler server-status
        Require all denied
    </Location>
    <Directory /var/www/summit/training-fixtures/cgi>
        Options +ExecCGI
        AddHandler cgi-script .cgi
        Require all denied
    </Directory>
    <Directory /var/www/summit/training-fixtures/ssi>
        Options -Includes
        AddType text/html .shtml
        AddOutputFilter INCLUDES .shtml
        Require all granted
    </Directory>
'''+ '</VirtualHost>'+closing
