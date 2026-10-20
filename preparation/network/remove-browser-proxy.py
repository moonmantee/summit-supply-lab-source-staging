from pathlib import Path
from datetime import datetime, timezone
import re
stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
roots=[Path.home()/'.mozilla/firefox',Path.home()/'snap/firefox/common/.mozilla/firefox']
for root in roots:
    if not root.is_dir(): continue
    for profile in root.iterdir():
        if not profile.is_dir(): continue
        target=profile/'user.js'
        prefs=profile/'prefs.js'
        text=target.read_text() if target.exists() else ''
        current=prefs.read_text() if prefs.exists() else ''
        if 'BEGIN SUMMIT PROXY' not in text and '10.77.70.10' not in text+current: continue
        if target.exists(): target.with_name('user.js.pre-proxy-retirement-'+stamp).write_text(text)
        text=re.sub(r'// BEGIN SUMMIT PROXY.*?// END SUMMIT PROXY','',text,flags=re.S)
        text=re.sub(r'^user_pref\("network\.proxy\.(?:type|http|http_port|ssl|ssl_port|no_proxies_on)",.*?;\s*$','',text,flags=re.M)
        target.write_text(text.rstrip()+'\n// Proxy retired: route directly through range-fw.\nuser_pref("network.proxy.type", 0);\n')
        print('Direct browser networking configured:',target,'; restart Firefox if open')
