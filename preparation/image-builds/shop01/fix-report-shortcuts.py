from pathlib import Path

desktop = Path('/home/jwang/Desktop')
for label, report in [('Summit-Scoring-Report.html', 'ScoringReport.html'),
                      ('Summit-ReadMe.html', 'ReadMe.html')]:
    shortcut = desktop / label
    if not shortcut.is_symlink() or str(shortcut.readlink()) != '/opt/aeacus/assets/' + report:
        raise SystemExit('Unexpected shortcut; review before replacing: ' + str(shortcut))
    shortcut.unlink()
    url = 'http://127.0.0.1:8765/' + report
    shortcut.write_text(
        '<!doctype html><html lang="en"><head><meta charset="utf-8">'
        '<meta http-equiv="refresh" content="0;url=' + url + '">'
        '<title>Summit practice report</title></head><body>'
        '<p><a href="' + url + '">Open the live Summit practice report</a></p>'
        '</body></html>', encoding='utf-8')
    print('Repaired', label)
