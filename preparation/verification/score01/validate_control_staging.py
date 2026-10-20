#!/usr/bin/env python3
"""Exercise the real control HTTP handler against the disposable staging copy."""

from __future__ import annotations

import json
import sqlite3
from threading import Thread
from urllib.request import Request, urlopen

import scoreboard_server
import scorer


def post(port: int, token: str, action: str) -> dict[str, object]:
    request = Request(
        f"http://127.0.0.1:{port}/api/control",
        data=json.dumps({"action": action}).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Origin": f"http://127.0.0.1:{port}",
            "X-Summit-Control-Token": token,
        },
        method="POST",
    )
    with urlopen(request, timeout=10) as response:
        assert response.status == 200
        return json.load(response)


def counts() -> tuple[int, int, int]:
    with sqlite3.connect(scoreboard_server.ControlHandler.database_path) as db:
        current_id = db.execute(
            "SELECT current_event_id FROM scorer_settings WHERE id=1"
        ).fetchone()[0]
        rounds = db.execute(
            "SELECT COUNT(*) FROM scoring_rounds WHERE event_id=?", (current_id,)
        ).fetchone()[0]
        checks = db.execute(
            "SELECT COUNT(*) FROM service_checks WHERE event_id=?", (current_id,)
        ).fetchone()[0]
        state_rows = db.execute(
            "SELECT COUNT(*) FROM event_service_state WHERE event_id=?", (current_id,)
        ).fetchone()[0]
        return rounds, checks, state_rows


def main() -> None:
    token = scoreboard_server.prepare_server()
    scoreboard_server.ControlHandler.control_token = token
    server = scoreboard_server.ThreadingHTTPServer(
        ("127.0.0.1", 0), scoreboard_server.ControlHandler
    )
    port = server.server_address[1]
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        started = post(port, token, "start")
        assert started["state"] == "RUNNING"
        running_round = scorer.run_scoring_round()
        assert running_round["recorded"] is True
        assert counts()[0] == 1

        stopped = post(port, token, "stop")
        assert stopped["state"] == "STOPPED"
        before_stopped_run = counts()
        stopped_round = scorer.run_scoring_round()
        assert stopped_round["recorded"] is False
        assert counts() == before_stopped_run

        reset = post(port, token, "reset")
        assert reset["state"] == "READY"
        assert reset["name"] == "Competition 2"
        assert counts() == (0, 0, 0)
        print(
            {
                "start": started,
                "recorded_round": running_round["round_id"],
                "stop": stopped,
                "reset": reset,
            }
        )
        print("staging control API validation: PASS")
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


if __name__ == "__main__":
    main()
