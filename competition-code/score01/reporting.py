"""Static multi-service status and audit views over the scoring database."""
import html
from pathlib import Path

HERE = Path(__file__).resolve().parent
LABELS = {
    'PASS': ('up', '↑', 'UP'),
    'DOWN': ('down', '↓', 'DOWN'),
    'FAIL': ('down', '↓', 'DOWN'),
    'INVALID': ('invalid', '—', 'INVALID'),
}


def badge(status):
    style, arrow, label = LABELS.get(status, ('invalid', '—', 'UNKNOWN'))
    return f'<span class="badge {style}" data-status="{html.escape(status)}"><span class="arrow" aria-hidden="true">{arrow}</span> {label}</span>'


def frame(title, content, timestamp, history=False):
    active_status, active_history = ('', 'active') if history else ('active', '')
    safe_time = html.escape(timestamp or '', quote=True)
    return f'''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta http-equiv="refresh" content="30"><title>{title} | Summit Scoring</title><link rel="stylesheet" href="scoreboard.css"><script src="scoreboard.js" defer></script></head>
<body data-last-check="{safe_time}"><header><div class="nav-wrap"><a class="brand" href="index.html">Summit <strong>Scoring</strong></a><nav aria-label="Main navigation"><a class="{active_status}" href="index.html">Service status</a><a class="{active_history}" href="history.html">Check history</a></nav><span class="team">BLUE TEAM 1</span></div></header>
<main><div id="stale" role="status" hidden><strong>Scoring results are stale.</strong> Check score01 and its timer. The last results below do not establish current service health.</div>{content}</main>
<footer>Private CCDC practice range · Checks every two minutes · Five consecutive DOWN checks trigger the listed SLA<br>INVALID means the scorer could not evaluate a service and does not advance its SLA counter. Times shown in UTC.</footer></body></html>'''


def _table_exists(db, name):
    return db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)).fetchone() is not None


def _write_pages(public, status_page, history_page):
    for name, content in [('index.html', status_page), ('history.html', history_page),
                          ('scoreboard.css', (HERE / 'scoreboard.css').read_text()),
                          ('scoreboard.js', (HERE / 'scoreboard.js').read_text())]:
        temporary = public / (name + '.tmp')
        temporary.write_text(content, encoding='utf-8')
        temporary.replace(public / name)


def _legacy_report(db, public):
    rows = db.execute('SELECT id,timestamp,status,reason,latency_ms FROM rounds ORDER BY id DESC').fetchall()
    counts = dict(db.execute('SELECT status,COUNT(*) FROM rounds GROUP BY status'))
    passed, failed, invalid = counts.get('PASS', 0), counts.get('FAIL', 0) + counts.get('DOWN', 0), counts.get('INVALID', 0)
    valid = passed + failed
    percentage = f'{100 * passed / valid:.1f}%' if valid else '—'
    latest = rows[0] if rows else None
    timestamp = latest[1] if latest else ''
    summary = f'''<div class="page-heading"><div><p class="eyebrow">SUMMIT SUPPLY / LEGACY</p><h1>Service status</h1><p class="subheading">Preserved single-service history.</p></div><a class="button" href="history.html">View all checks →</a></div>
<div class="stats"><section><span>Legacy points</span><strong>{passed}<small> / {valid}</small></strong></section><section><span>Checks passed</span><strong>{percentage}</strong></section><section><span>Down checks</span><strong>{failed}</strong></section><section><span>Invalid checks</span><strong>{invalid}</strong></section></div>'''
    if latest:
        check_id, when, status, reason, latency = latest
        current = f'''<tr><th scope="row"><strong>shop01</strong><span class="muted block">HTTPS · legacy catalog</span></th><td class="current-state">{badge(status)}<div class="status">{html.escape(status)}</div></td><td><time>{html.escape(when)}</time></td><td>{latency} ms</td><td><a href="history.html?check={check_id}">Check #{check_id} →</a></td></tr>'''
        details = f'<p class="last-detail">{html.escape(reason)}</p>'
    else:
        current = '<tr><td colspan="5">No checks yet. Waiting for the first scoring round.</td></tr>'
        details = ''
    table = f'''<section class="panel"><div class="panel-title"><h2>Legacy service health</h2><div class="legend">{badge('PASS')} {badge('DOWN')} {badge('INVALID')}</div></div><div class="table-scroll"><table><thead><tr><th>Service</th><th>State</th><th>Last checked (UTC)</th><th>Response</th><th>Details</th></tr></thead><tbody>{current}</tbody></table></div>{details}</section>'''
    history_rows = ''.join(f'''<tr data-check="{check_id}" data-status="{html.escape(status, quote=True)}"><td class="check-number">#{check_id}</td><td><time>{html.escape(when)}</time></td><td>shop01 <span class="muted">/ HTTPS</span></td><td>{badge(status)}</td><td>{latency} ms</td><td class="reason">{html.escape(reason)}</td></tr>''' for check_id, when, status, reason, latency in rows)
    history = _history_content(history_rows, len(rows), 'Legacy HTTPS checks')
    _write_pages(public, frame('Service status', summary + table, timestamp), frame('Check history', history, timestamp, True))


def _history_content(rows, count, subtitle='Every service transaction and scoring decision.'):
    return f'''<div class="page-heading"><div><p class="eyebrow">SUMMIT SUPPLY / AUDIT TRAIL</p><h1>Check history</h1><p class="subheading">{html.escape(subtitle)}</p></div><span class="record-total">{count:,} checks recorded</span></div>
<section class="panel"><div class="filters"><label>Search checks<input id="search" type="search" placeholder="Host, service, time, check, or error…"></label><label>Result<select id="status-filter"><option value="">All results</option><option value="PASS">↑ Up</option><option value="DOWN">↓ Down</option><option value="FAIL">↓ Legacy down</option><option value="INVALID">— Invalid</option></select></label><a class="clear" href="history.html">Clear filters</a></div>
<div class="table-scroll"><table id="history-table"><thead><tr><th>Check</th><th>Time (UTC)</th><th>Service</th><th>Result</th><th>Points</th><th>SLA</th><th>Failure window</th><th>Response</th><th>Details / error</th></tr></thead><tbody>{rows}</tbody></table></div><p id="empty-results" hidden>No checks match these filters.</p><div class="pagination"><span id="page-summary" aria-live="polite">{count} recorded checks</span><div><button id="previous" type="button">← Previous</button><button id="next" type="button">Next →</button></div></div></section><p class="footnote">↑ Up earns the configured points. ↓ Down earns zero and advances that service's failure window. — Invalid leaves its window unchanged.</p>'''


def _render_unscoped_report(db, public, services=None):
    public = Path(public)
    public.mkdir(parents=True, exist_ok=True)
    has_new = _table_exists(db, 'service_checks') and db.execute('SELECT 1 FROM service_checks LIMIT 1').fetchone()
    if not has_new:
        if not _table_exists(db, 'rounds'):
            db.execute('CREATE TABLE rounds(id INTEGER PRIMARY KEY,timestamp TEXT,status TEXT,reason TEXT,latency_ms INTEGER)')
        _legacy_report(db, public)
        return

    checks = db.execute('''SELECT id,round_id,timestamp,service_id,host_name,service_name,status,reason,
                                  latency_ms,awarded_points,sla_deduction,consecutive_failures
                           FROM service_checks ORDER BY id DESC''').fetchall()
    latest_by_service = {}
    for row in checks:
        latest_by_service.setdefault(row[3], row)
    service_map = {service['id']: service for service in (services or [])}
    order = [service['id'] for service in (services or [])]
    order.extend(service_id for service_id in latest_by_service if service_id not in order)
    total_points = db.execute('SELECT COALESCE(SUM(awarded_points),0) FROM service_checks').fetchone()[0]
    total_sla = db.execute('SELECT COALESCE(SUM(sla_deduction),0) FROM service_checks').fetchone()[0]
    passed = sum(1 for row in checks if row[6] == 'PASS')
    down = sum(1 for row in checks if row[6] in ('DOWN', 'FAIL'))
    invalid = sum(1 for row in checks if row[6] == 'INVALID')
    valid = passed + down
    percentage = f'{100 * passed / valid:.1f}%' if valid else '—'
    timestamp = checks[0][2]
    summary = f'''<div class="page-heading"><div><p class="eyebrow">SUMMIT SUPPLY / OPERATIONS</p><h1>Service status</h1><p class="subheading">CCDC availability points and independent SLA windows.</p></div><a class="button" href="history.html">View all checks →</a></div>
<div class="stats"><section><span>Net score</span><strong>{total_points - total_sla}</strong></section><section><span>Availability points</span><strong>{total_points}</strong></section><section><span>SLA deductions</span><strong>{total_sla}</strong></section><section><span>Checks passed</span><strong>{percentage}</strong></section></div>'''
    current_rows = []
    details = []
    for service_id in order:
        row = latest_by_service.get(service_id)
        if not row:
            continue
        check_id, _, when, _, host_name, service_name, status, reason, latency, _, _, failures = row
        configured = service_map.get(service_id, {})
        points = configured.get('points', '?')
        penalty = configured.get('sla_penalty', '?')
        current_rows.append(f'''<tr><th scope="row"><strong>{html.escape(host_name)}</strong><span class="muted block">{html.escape(service_name)}</span></th><td class="current-state">{badge(status)}<div class="status">{html.escape(status)}</div></td><td>+{points} / SLA −{penalty}</td><td>{failures} / 5</td><td><time>{html.escape(when)}</time></td><td>{latency} ms</td><td><a href="history.html?check={check_id}">Check #{check_id} →</a></td></tr>''')
        details.append(f'<li><strong>{html.escape(host_name)} / {html.escape(service_name)}:</strong> {html.escape(reason)}</li>')
    service_table = f'''<section class="panel"><div class="panel-title"><h2>Service health</h2><div class="legend">{badge('PASS')} {badge('DOWN')} {badge('INVALID')}</div></div><div class="table-scroll"><table><thead><tr><th>Service</th><th>State</th><th>Points / SLA</th><th>Down window</th><th>Last checked (UTC)</th><th>Response</th><th>Details</th></tr></thead><tbody>{''.join(current_rows)}</tbody></table></div><ul class="last-detail">{''.join(details)}</ul></section>'''
    timeline = ''.join(f'<a class="round {LABELS.get(row[6], LABELS["INVALID"])[0]}" href="history.html?check={row[0]}" title="Check #{row[0]} · {html.escape(row[4], quote=True)} / {html.escape(row[5], quote=True)} · {row[6]}" aria-label="Check {row[0]}: {row[6]}">{LABELS.get(row[6], LABELS["INVALID"])[1]}</a>' for row in reversed(checks[:60]))
    timeline_panel = f'''<section class="panel"><div class="panel-title"><h2>Recent service results</h2><span class="muted">Oldest → newest · last 60</span></div><div class="timeline">{timeline}</div></section><p class="footnote">Host-hardening and forensic points remain in Aeacus; this dashboard scores service availability and SLAs.</p>'''
    history_rows = ''.join(f'''<tr data-check="{row[0]}" data-status="{html.escape(row[6], quote=True)}"><td class="check-number">#{row[0]}</td><td><time>{html.escape(row[2])}</time></td><td>{html.escape(row[4])} <span class="muted">/ {html.escape(row[5])}</span></td><td>{badge(row[6])}</td><td>+{row[9]}</td><td>−{row[10]}</td><td>{row[11]} / 5</td><td>{row[8]} ms</td><td class="reason">{html.escape(row[7])}</td></tr>''' for row in checks)
    history_content = _history_content(history_rows, len(checks))
    _write_pages(public, frame('Service status', summary + service_table + timeline_panel, timestamp),
                 frame('Check history', history_content, timestamp, True))


def _atomic_write(path, content):
    temporary = path.with_suffix(path.suffix + '.tmp')
    temporary.write_text(content, encoding='utf-8')
    temporary.replace(path)


def _event_frame(title, content, timestamp, event, history=False, control_token=''):
    active_status, active_history = ('', 'active') if history else ('active', '')
    token = html.escape(control_token, quote=True)
    safe_time = html.escape(timestamp or '', quote=True)
    state = html.escape(event.state, quote=True)
    return f'''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta http-equiv="refresh" content="30"><meta name="summit-control-token" content="{token}"><title>{html.escape(title)} | Summit Scoring</title><link rel="stylesheet" href="scoreboard.css"><script src="scoreboard.js" defer></script></head>
<body data-last-check="{safe_time}" data-event-state="{state}" data-event-id="{event.id}"><header><div class="nav-wrap"><a class="brand" href="index.html">Summit <strong>Scoring</strong></a><nav aria-label="Main navigation"><a class="{active_status}" href="index.html">Service status</a><a class="{active_history}" href="history.html">Check history</a></nav><span class="team">BLUE TEAM 1</span></div></header>
<main><div id="stale" role="status" hidden><strong>Scoring results are stale.</strong> Check score01 and its timer. The last results below do not establish current service health.</div>{content}</main>
<footer>Private CCDC practice range · Checks every two minutes while RUNNING · Five consecutive DOWN checks trigger the listed SLA<br>Stop freezes counters. Reset archives the current event. INVALID does not advance an SLA counter. Times shown in UTC.</footer></body></html>'''


def _event_totals(db, event_id):
    row = db.execute(
        '''SELECT COALESCE(SUM(total_points),0),COALESCE(SUM(total_sla_deductions),0)
           FROM event_service_state WHERE event_id=?''',
        (event_id,),
    ).fetchone()
    return row[0], row[1]


def _event_checks(db, event_id):
    return db.execute(
        '''SELECT id,round_id,timestamp,service_id,host_name,service_name,status,reason,
                  latency_ms,awarded_points,sla_deduction,consecutive_failures
           FROM service_checks WHERE event_id=? ORDER BY id DESC''',
        (event_id,),
    ).fetchall()


def _service_list(services, checks):
    result = [dict(service) for service in (services or [])]
    known = {service['id'] for service in result}
    for row in checks:
        if row[3] not in known:
            result.append({
                'id': row[3], 'host_name': row[4], 'service_name': row[5],
                'points': '?', 'sla_penalty': '?',
            })
            known.add(row[3])
    return result


def _event_navigation(events, current_event_id, selected_event_id):
    links = []
    for item in events:
        target = 'history.html' if item.id == current_event_id else f'history-event-{item.id}.html'
        active = ' active' if item.id == selected_event_id else ''
        links.append(
            f'<a class="event-link{active}" href="{target}">'
            f'{html.escape(item.name)} <span>{html.escape(item.state)}</span></a>'
        )
    return '<nav class="event-selector" aria-label="Competition events">' + ''.join(links) + '</nav>'


def _event_summary(event, points, deductions):
    return f'''<section class="event-summary"><div><p class="eyebrow">COMPETITION EVENT</p><h1>{html.escape(event.name)}</h1><p class="subheading">State: <strong class="event-state state-{event.state.lower()}">{html.escape(event.state)}</strong></p></div><dl><div><dt>Started</dt><dd>{html.escape(event.started_at or 'Not started')}</dd></div><div><dt>Stopped</dt><dd>{html.escape(event.stopped_at or '—')}</dd></div></dl></section>
<div class="stats" data-total-points="{points}" data-total-sla="{deductions}"><section><span>Net score</span><strong>{points - deductions}</strong></section><section><span>Availability points</span><strong>{points}</strong></section><section><span>SLA deductions</span><strong>{deductions}</strong></section><section><span>Event state</span><strong class="state-word">{html.escape(event.state)}</strong></section></div>'''


def _control_panel(event):
    start_disabled = ' disabled' if event.state not in {'READY', 'STOPPED'} else ''
    stop_disabled = ' disabled' if event.state != 'RUNNING' else ''
    return f'''<section class="panel control-panel" data-event-state="{html.escape(event.state, quote=True)}"><div><h2>Competition controls</h2><p>Stop freezes the current score and SLA windows. Reset archives this event and creates a fresh READY event.</p></div><div class="control-actions"><button id="start-control"{start_disabled} data-action="start" type="button">Start</button><button id="stop-control"{stop_disabled} data-action="stop" type="button">Stop</button><button id="reset-control" data-action="reset" type="button">Reset &amp; archive</button></div><p id="control-message" role="status" aria-live="polite"></p></section>'''


def _status_page(db, services, event, control_token):
    checks = _event_checks(db, event.id)
    configured = _service_list(services, checks)
    latest = {}
    for row in checks:
        latest.setdefault(row[3], row)
    points, deductions = _event_totals(db, event.id)
    table_rows = []
    reasons = []
    for service in configured:
        row = latest.get(service['id'])
        if row:
            check_id, _, when, _, host_name, service_name, status, reason, latency, _, _, failures = row
            state_badge = badge(status) + f'<div class="status">{html.escape(status)}</div>'
            detail = f'<a href="history.html?check={check_id}">Check #{check_id} →</a>'
            reasons.append(
                f'<li><strong>{html.escape(host_name)} / {html.escape(service_name)}:</strong> '
                f'{html.escape(reason)}</li>'
            )
        else:
            host_name, service_name = service.get('host_name', service['id']), service.get('service_name', service['id'])
            when, latency, failures = 'Never', '—', 0
            state_badge = '<span class="badge invalid"><span class="arrow" aria-hidden="true">·</span> NOT CHECKED</span><div class="status">NOT CHECKED</div>'
            detail = 'Waiting for a RUNNING round'
        table_rows.append(f'''<tr><th scope="row"><strong>{html.escape(str(host_name))}</strong><span class="muted block">{html.escape(str(service_name))}</span></th><td class="current-state">{state_badge}</td><td>+{service.get('points','?')} / SLA −{service.get('sla_penalty','?')}</td><td>{failures} / 5</td><td><time>{html.escape(str(when))}</time></td><td>{latency}{' ms' if isinstance(latency, int) else ''}</td><td>{detail}</td></tr>''')
    service_table = f'''<section class="panel"><div class="panel-title"><h2>Service health</h2><div class="legend">{badge('PASS')} {badge('DOWN')} {badge('INVALID')}</div></div><div class="table-scroll"><table><thead><tr><th>Service</th><th>State</th><th>Points / SLA</th><th>Down window</th><th>Last checked (UTC)</th><th>Response</th><th>Details</th></tr></thead><tbody>{''.join(table_rows)}</tbody></table></div><ul class="last-detail">{''.join(reasons)}</ul></section>'''
    heading = _event_summary(event, points, deductions)
    history_link = '<p><a class="button" href="history.html">Open the round-by-service history grid →</a></p>'
    timestamp = checks[0][2] if checks else ''
    content = heading + _control_panel(event) + service_table + history_link
    return _event_frame('Service status', content, timestamp, event, control_token=control_token)


def render_event_history(db, services, event_id: int) -> str:
    from lifecycle import get_current_event, list_events
    events = list_events(db)
    event_by_id = {event.id: event for event in events}
    if event_id not in event_by_id:
        raise ValueError('unknown event ID')
    event = event_by_id[event_id]
    current = get_current_event(db)
    checks = _event_checks(db, event.id)
    configured = _service_list(services, checks)
    rounds = db.execute(
        '''SELECT id,timestamp FROM scoring_rounds WHERE event_id=?
           ORDER BY id DESC LIMIT 100''',
        (event.id,),
    ).fetchall()
    cell_map = {(row[1], row[3]): row for row in checks}
    header_cells = ''.join(
        f'<th data-service-id="{html.escape(service["id"], quote=True)}"><strong>{html.escape(str(service.get("host_name", service["id"])))}</strong><span>{html.escape(str(service.get("service_name", service["id"])))}</span></th>'
        for service in configured
    )
    grid_rows = []
    for round_id, timestamp in rounds:
        cells = []
        for service in configured:
            row = cell_map.get((round_id, service['id']))
            if row is None:
                cells.append('<td class="grid-empty" aria-label="No result">—</td>')
                continue
            status, reason, latency, awarded, deduction, failures = row[6], row[7], row[8], row[9], row[10], row[11]
            style, arrow, label = LABELS.get(status, LABELS['INVALID'])
            tooltip = html.escape(
                f'Reason: {reason} | Latency: {latency} ms | Points: +{awarded} | '
                f'SLA: -{deduction} | Window: {failures} / 5',
                quote=True,
            )
            cells.append(
                f'<td class="grid-state {style}" data-grid-status="{html.escape(status, quote=True)}" '
                f'title="{tooltip}"><span aria-hidden="true">{arrow}</span><span>{label}</span></td>'
            )
        grid_rows.append(
            f'<tr data-grid-row="{round_id}"><th scope="row"><time>{html.escape(timestamp)}</time></th>{"".join(cells)}</tr>'
        )
    if not grid_rows:
        grid_rows.append(
            f'<tr><td colspan="{len(configured) + 1}">No scoring rounds in this event.</td></tr>'
        )
    grid = f'''<section class="panel"><div class="panel-title"><h2>Round history grid</h2><span class="muted">Newest first · latest 100 rounds</span></div><div class="history-grid"><table><thead><tr><th>Timestamp (UTC)</th>{header_cells}</tr></thead><tbody>{''.join(grid_rows)}</tbody></table></div></section>'''
    detail_rows = ''.join(f'''<tr data-check="{row[0]}" data-status="{html.escape(row[6], quote=True)}"><td class="check-number">#{row[0]}</td><td><time>{html.escape(row[2])}</time></td><td>{html.escape(row[4])} <span class="muted">/ {html.escape(row[5])}</span></td><td>{badge(row[6])}</td><td>+{row[9]}</td><td>−{row[10]}</td><td>{row[11]} / 5</td><td>{row[8]} ms</td><td class="reason">{html.escape(row[7])}</td></tr>''' for row in checks)
    points, deductions = _event_totals(db, event.id)
    heading = _event_summary(event, points, deductions)
    navigation = _event_navigation(events, current.id, event.id)
    detail = _history_content(detail_rows, len(checks), 'Exact results for the selected competition event.')
    timestamp = rounds[0][1] if rounds else ''
    return _event_frame('Check history', heading + navigation + grid + detail, timestamp, event, history=True)


def _render_event_report(db, public, services, control_token):
    from lifecycle import get_current_event, list_events
    current = get_current_event(db)
    _atomic_write(public / 'index.html', _status_page(db, services, current, control_token))
    current_history = render_event_history(db, services, current.id)
    _atomic_write(public / 'history.html', current_history)
    for event in list_events(db):
        _atomic_write(
            public / f'history-event-{event.id}.html',
            render_event_history(db, services, event.id),
        )
    _atomic_write(public / 'scoreboard.css', (HERE / 'scoreboard.css').read_text())
    _atomic_write(public / 'scoreboard.js', (HERE / 'scoreboard.js').read_text())


def render_report(db, public, services=None, control_token=''):
    public = Path(public)
    public.mkdir(parents=True, exist_ok=True)
    if _table_exists(db, 'competition_events') and _table_exists(db, 'scorer_settings'):
        _render_event_report(db, public, services or [], control_token)
    else:
        _render_unscoped_report(db, public, services)
