from pathlib import Path
base=Path(__file__).resolve().parent
s=(base/'update_six_injects.py').read_text()
s=s.replace("'six-injects-'","'schedule-grace-'")
s=s.replace("['scorer.py','inject_services.py']","['scorer.py','inject_services.py','portal_store.py']")
s=s.replace("['scorer.py','inject_services.py','portal_server.py'", "['scorer.py','inject_services.py','portal_store.py','arm_inject_schedule.py','portal-web/app.js','portal_server.py'")
s=s.replace("assert unchanged==old,'Existing injects changed.'", "assert all(current[:len(previous)]==previous for current,previous in zip(unchanged,old)) and len(unchanged)==len(old),'Existing inject fields changed.'")
s=s.replace("        assert all(row[2] is None for row in rows),'Tasks must remain drafts.'", "        assert all(row[2] is None for row in rows),'Tasks must remain drafts.'\n    subprocess.run(['/usr/bin/python3',str(portal/'arm_inject_schedule.py')],check=True)")
(base/'update_schedule_grace.py').write_text(s,encoding='utf-8',newline='\n')
