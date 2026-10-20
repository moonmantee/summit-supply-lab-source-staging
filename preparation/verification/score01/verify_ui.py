import urllib.request
for name in ['index.html', 'history.html', 'scoreboard.css', 'scoreboard.js']:
    with urllib.request.urlopen('http://127.0.0.1:8766/' + name) as response:
        assert response.status == 200
        assert response.read()
    print(name, 'HTTP 200')
