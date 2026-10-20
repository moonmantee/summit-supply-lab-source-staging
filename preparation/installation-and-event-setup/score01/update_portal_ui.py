from pathlib import Path
import json
base=Path(__file__).resolve().parent
p=base/'portal-web/app.js'; s=p.read_text(encoding='utf-8')
a=s.index('function scoreboard()'); b=s.index('function services()',a)
s=s[:a]+'''function scoreboard(){return title('Scoreboard','The existing Summit service scoreboard, with automatically graded inject services.')+`<iframe class="existing-scoreboard" title="Summit service scoreboard" src="/portal/scoreboard/index.html"></iframe><section class="panel"><h2>Task completion points</h2><p>${num(state.scores.inject_points)} earned completion points · ${num(state.scores.total)} combined total including net service availability.</p>${state.injects.filter(c=>c.completed_at).map(c=>`<p>${esc(c.code+' · '+c.title)} — ${c.earned_points} points</p>`).join('')}</section>`;}
'''+s[b:]
s=s.replace('White Team verifies this task manually. Select Ready for verification when the requirements are met.', '${c.automatic?`Automatic service grading: ${c.auto_streak}/3 consecutive passing rounds. ${c.needs_configuration?\'Organizer configuration required before release.\':\'Completion points require three consecutive passes before the deadline. The new service continues earning availability points and receiving SLA deductions afterward.\'}`:\'White Team verifies this task manually. Select Ready for verification when the requirements are met.\'}')
s=s.replace('<button data-team-action="ready"', '${!c.automatic?`<button data-team-action="ready"')
s=s.replace("Ready for verification'}</button></div>", "Ready for verification'}</button>`:''}</div>")
s=s.replace("if(!c.released_at)return", "if(!c.released_at)return")
s=s.replace('<button data-release="${c.id}">Release to team</button>', '<form class="service-form" data-id="${c.id}"><label>Private service probe configuration (JSON; stored only on score01)<textarea name="service" placeholder=\'{"probe":"ftp_share","host":"10.77.30.20","username":"inventory_reader","password":"...","file":"inventory.csv","sha256":"...","points":2,"sla_penalty":7}\'></textarea></label><button class="secondary">Configure automatic check</button></form><button data-release="${c.id}" ${c.needs_configuration?\'disabled\':\'\'}>Release to team</button>')
s=s.replace("if(c.completed_at)return", "if(c.automatic&&c.released_at)return `<p class=\"muted\">Automatic check: ${esc(c.auto_status||'Not checked')} · ${c.auto_streak}/3 consecutive passing rounds. Service: ${esc(c.service_summary?.name)} · ${c.service_summary?.points} points each passing round; ${c.service_summary?.sla_penalty} SLA penalty per five consecutive DOWN rounds.</p>`;if(c.completed_at)return")
s=s.replace('<label class="wide">Title<input', '<label class="wide">Grading<select name="automatic"><option value="true">Automatic service check (configure before release)</option><option value="false">Manual review</option></select></label><label class="wide">Title<input')
s=s.replace("!e.target.matches('.grade-form')", "!e.target.matches('.grade-form,.service-form')")
s=s.replace("f.points=Number(f.points);", "f.points=Number(f.points);f.automatic=f.automatic==='true';")
s=s.replace("else payload={action:'grade'", "else if(e.target.matches('.service-form'))payload={action:'service',id:Number(e.target.dataset.id),service:JSON.parse(f.service)};else payload={action:'grade'")
p.write_text(s,encoding='utf-8',newline='\n')
css=base/'portal-web/style.css'
css.write_text(css.read_text()+ '\n.existing-scoreboard{display:block;width:100%;height:1150px;border:0;border-radius:12px;margin-bottom:24px;background:#f5f7fa}\n',encoding='utf-8',newline='\n')
p=base/'portal-injects.json'; cards=json.loads(p.read_text())
acceptance={
'I01':'Automatic service: exact orders.corp.summit.test A record equals 10.77.30.10 over UDP and TCP to dc01. Three consecutive passing scoring rounds before the deadline award completion points. The DNS service then continues availability scoring.',
'I02':'Automatic service: inventory_reader retrieves the supplied inventory.csv with its exact SHA256 through passive FTP; upload of a disposable new file is denied; anonymous inventory retrieval is denied. Three consecutive passing rounds before the deadline award completion points. This is a new service in addition to baseline FTP. Preserve existing data and configure all inventory access as read-only; overwrite/delete restrictions remain operational policy and are not tested by destructive file operations.',
'I03':'Automatic service: authenticated STARTTLS SMTP submission on 587 to dispatch@corp.summit.test delivers a fresh uniquely tagged message to the operations mailbox, searchable through trusted IMAPS on 993 within eight seconds. Three consecutive passing rounds before the deadline award completion points. White Team must configure the mailbox credentials, lab DNS name and trusted certificate file before release.',
'I04':'Automatic service: trusted certificate chain, DNS name and validity for forum01.corp.summit.test on 443; HTTP / redirects to https://forum01.corp.summit.test/; HTTPS / returns HTTP 200 containing the configured forum marker. Three consecutive passing rounds before the deadline award completion points. HTTPS becomes a separate scored service. Preserve the functional forum and database; login/posting workflows remain operational policy and are not claimed by this availability probe.'}
for card in cards:
    card['automatic']=True; card['acceptance']=acceptance[card['code']]
    card['description']=card['description'].replace('White Team must attach the fixture and account details before release.','Download the inventory and dedicated account details attached to this task.').replace('White Team must attach the certificate package before release.','Download the attached lab-only PEM certificate package and installation instructions.')
p.write_text(json.dumps(cards,indent=2)+'\n',encoding='utf-8')
