import urllib.request
import urllib.error

for name, marker in [('ScoringReport.html', '50 out of 50'), ('ReadMe.html', 'Business requirements')]:
    with urllib.request.urlopen('http://127.0.0.1:8765/' + name, timeout=5) as r:
        assert r.status == 200
        assert marker in r.read().decode()
    print(name, 'HTTP 200 and expected content verified')
for path in ['scoring.dat', 'scoring.conf', '../scoring.dat']:
    try:
        urllib.request.urlopen('http://127.0.0.1:8765/' + path, timeout=5)
    except urllib.error.HTTPError as e:
        assert e.code == 404
    else:
        raise AssertionError('Unexpected scoring-file exposure: ' + path)
print('Scoring configuration paths return 404')
