#!/usr/bin/env bash
# Scoped, harmless Apache fixtures for objectives 30–37; keep PHP/database intact.
set -euo pipefail
umask 077
[[ $(id -u) == 0 && $(hostname -s) == shop01 ]] || { echo 'Run with sudo on shop01.'; exit 1; }
source_dir=$(cd -- "$(dirname -- "$0")" && pwd)
source "$source_dir/stage_common.sh"
[[ ! -e /var/www/summit/training-fixtures && ! -L /var/www/summit/training-fixtures ]] || { echo 'Fixture collision: refusing overwrite.'; exit 1; }
[[ -f /home/jwang/shop01-baseline.json ]] || exit 1
bash "$source_dir/validate-probes.sh"
backup_dir=$(mktemp -d /var/backups/summit-shop01-apache-XXXXXXXX)
site=/etc/apache2/sites-available/summit-shop.conf
cp "$site" "$backup_dir/original-site.conf"
chmod 600 "$backup_dir/original-site.conf"
getfacl -p "$site" > "$backup_dir/original-site.acl"
install -d -m 700 "$backup_dir/probes"
cp "$source_dir/probes/"*.py "$backup_dir/probes/"
cgi_original=0; include_original=0
[[ ! -L /etc/apache2/mods-enabled/cgi.load ]] || cgi_original=1
[[ ! -L /etc/apache2/mods-enabled/include.load ]] || include_original=1
printf '%s\n' "cgi_original=$cgi_original" "include_original=$include_original" > "$backup_dir/modules.txt"
rollback() {
  cat "$backup_dir/original-site.conf" > "$site" || return 1
  setfacl --restore="$backup_dir/original-site.acl" || return 1
  [[ $cgi_original == 1 ]] || a2dismod cgi >/dev/null || return 1
  [[ $include_original == 1 ]] || a2dismod include >/dev/null || return 1
  rm -rf -- /var/www/summit/training-fixtures || return 1
  apache2ctl -t || return 1
  systemctl reload apache2 || return 1
}
enable_rollback_trap
setup_fixtures() {
  install -d -m 755 /var/www/summit/training-fixtures/{listing,cgi,ssi,SUMMIT-ERROR-VALIDATION}
  printf '%s\n' 'Harmless directory-listing fixture.' > /var/www/summit/training-fixtures/listing/inventory-placeholder.txt
  printf '%s\n' 'Fictional account: sample_employee' 'Fictional credential: not-a-real-password' > /var/www/summit/training-fixtures/public-backup.sql
  printf '%s\n' 'Synthetic internal note; contains no real secret.' > /var/www/summit/training-fixtures/.private-note
  cat > /var/www/summit/training-fixtures/cgi/marker.cgi <<'EOF'
#!/usr/bin/env sh
printf 'Content-Type: text/plain\r\n\r\nSUMMIT-CGI-EXECUTED\n'
EOF
  printf '%s\n' 'Before <!--#include virtual="/training-fixtures/ssi/include.txt" --> After' > /var/www/summit/training-fixtures/ssi/marker.shtml
  printf '%s\n' SUMMIT-SSI-EXECUTED > /var/www/summit/training-fixtures/ssi/include.txt
  printf '%s\n' 'Harmless error-log validation fixture.' > /var/www/summit/training-fixtures/SUMMIT-ERROR-VALIDATION/marker.txt
  find /var/www/summit/training-fixtures -type f -exec chmod 644 {} +
  chmod 755 /var/www/summit/training-fixtures/cgi/marker.cgi
  chmod 000 /var/www/summit/training-fixtures/SUMMIT-ERROR-VALIDATION
  printf '%s\n' SUMMIT-SHOP-FIXTURES-V1 > /var/www/summit/training-fixtures/.ready
  chmod 644 /var/www/summit/training-fixtures/.ready
  a2enmod cgi include >/dev/null
}
render_site() {
  python3 - "$backup_dir/original-site.conf" "$site" "$1" <<'PY'
import pathlib,re,sys
original=pathlib.Path(sys.argv[1]).read_text(); mode=sys.argv[3]
assert original.count('<VirtualHost')==2 and '<VirtualHost *:443>' in original
head,closing=original.rsplit('</VirtualHost>',1)
assert 'SSLEngine on' in head.rsplit('<VirtualHost',1)[1]
secure=mode=='secure'
deny='Require all denied' if secure else 'Require all granted'
listing='-Indexes' if secure else '+Indexes'
snippet=f'''
    <Directory /var/www/summit/training-fixtures/listing>
        Options {listing}
        Require all granted
    </Directory>
    <Directory /var/www/summit/training-fixtures>
        <FilesMatch "^(public-backup[.]sql|[.]private-note)$">
            {deny}
        </FilesMatch>
    </Directory>
    <Location /server-status>
        SetHandler server-status
        {deny}
    </Location>
    <Directory /var/www/summit/training-fixtures/cgi>
        Options +ExecCGI
        AddHandler cgi-script .cgi
        {deny}
    </Directory>
    <Directory /var/www/summit/training-fixtures/ssi>
        Options {'-Includes' if secure else '+Includes'}
        AddType text/html .shtml
        AddOutputFilter INCLUDES .shtml
        Require all granted
    </Directory>
'''
text=head+snippet+'</VirtualHost>'+closing
if not secure:
    text,count=re.subn(r'(?m)^(\s*)CustomLog\s+[^\n]+$',r'\1CustomLog /dev/null combined',text)
    assert count==1, 'Unexpected CustomLog layout'
    text,count=re.subn(r'(?m)^(\s*)ErrorLog\s+[^\n]+$',r'\1ErrorLog /dev/null',text)
    assert count==1, 'Unexpected ErrorLog layout'
# Write into the retained file; never reset its mode/ACL or erase the separately
# staged Apache-configuration permission objective.
pathlib.Path(sys.argv[2]).write_text(text)
PY
  apache2ctl -t
  systemctl reload apache2
}
validate_error_log() {
  python3 - "$backup_dir" <<'PY'
import pathlib,sys,time
sys.path.insert(0,str(pathlib.Path(sys.argv[1])/'probes')); import web
path=pathlib.Path('/var/log/apache2/summit-error.log'); old=path.stat().st_size if path.exists() else 0
status,_=web.fetch('/training-fixtures/SUMMIT-ERROR-VALIDATION/marker.txt')
assert status==403, 'Error fixture must remain inaccessible'
assert web.wait_for_token(path,'SUMMIT-ERROR-VALIDATION')
deadline=time.monotonic()+1
while path.stat().st_size<=old and time.monotonic()<deadline: time.sleep(0.02)
assert path.stat().st_size>old, 'New controlled error was not delivered'
PY
}
assert_state() {
  python3 - "$backup_dir" "$1" "$2" <<'PY'
import json,pathlib,sys
root=pathlib.Path(sys.argv[1]); sys.path.insert(0,str(root/'probes')); import web
expected=sys.argv[3]=='PASS'; states={str(i):web.check(i) for i in range(30,38)}
with (root/'rehearsal.jsonl').open('a') as f: f.write(json.dumps({'phase':sys.argv[2],'states':states})+'\n')
bad=[i for i,v in states.items() if v is not expected]
assert not bad, 'Apache rehearsal mismatch for objective(s): '+','.join(bad)
assert web.fetch('/order-history.php')[0]==200, 'Order-history service failed'
print(sys.argv[2]+': '+sys.argv[3]+' for 30–37; PHP storefront/order history PASS')
PY
}
setup_fixtures
render_site secure
validate_error_log
assert_state secure PASS
render_site planted
assert_state planted FAIL
render_site secure
validate_error_log
assert_state repaired PASS
rollback
cmp -s "$backup_dir/original-site.conf" "$site"
echo 'Original Apache configuration/modules restored; legitimate logs retained.'
setup_fixtures
render_site planted
assert_state final-planted FAIL
bash "$source_dir/validate-probes.sh"
trap - ERR
install -o jwang -g jwang -m 600 "$backup_dir/rehearsal.jsonl" /home/jwang/shop01-apache-rehearsal.jsonl
echo "Eight Apache objectives staged/rehearsed. Private original configuration: $backup_dir"
echo 'Production scoring unchanged.'
