#!/usr/bin/env python3
"""Validate lifecycle migration against a disposable copy of the live database."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import scoreboard_server
import scorer


def scalar(db: sqlite3.Connection, sql: str, params: tuple = ()) -> int:
    return int(db.execute(sql, params).fetchone()[0])


def snapshot(database: Path) -> dict[str, object]:
    with sqlite3.connect(database) as db:
        db.row_factory = sqlite3.Row
        events = [
            dict(row)
            for row in db.execute(
                "SELECT id, name, state FROM competition_events ORDER BY id"
            )
        ]
        current_id = scalar(
            db,
            "SELECT current_event_id FROM scorer_settings WHERE id = 1",
        )
        return {
            "events": events,
            "rounds_by_event": [
                tuple(row)
                for row in db.execute(
                    "SELECT event_id, COUNT(*) FROM scoring_rounds "
                    "GROUP BY event_id ORDER BY event_id"
                )
            ],
            "checks_by_event": [
                tuple(row)
                for row in db.execute(
                    "SELECT event_id, COUNT(*) FROM service_checks "
                    "GROUP BY event_id ORDER BY event_id"
                )
            ],
            "current_state_rows": scalar(
                db,
                "SELECT COUNT(*) FROM event_service_state WHERE event_id = ?",
                (current_id,),
            ),
            "current_rounds": scalar(
                db,
                "SELECT COUNT(*) FROM scoring_rounds WHERE event_id = ?",
                (current_id,),
            ),
            "current_checks": scalar(
                db,
                "SELECT COUNT(*) FROM service_checks WHERE event_id = ?",
                (current_id,),
            ),
        }


def main() -> None:
    database = Path("state/results.sqlite3")
    result = scoreboard_server.prepare_server()
    before = snapshot(database)

    assert before["events"][-1]["name"] == "Competition 1"
    assert before["events"][-1]["state"] == "READY"
    assert before["events"][0]["state"] == "ARCHIVED"
    assert before["current_state_rows"] == 0
    assert before["current_rounds"] == 0
    assert before["current_checks"] == 0

    first = scorer.run_scoring_round()
    second = scorer.run_scoring_round()
    after = snapshot(database)

    assert first["event_state"] == "READY" and first["recorded"] is False
    assert second["event_state"] == "READY" and second["recorded"] is False
    assert after == before

    print({"prepare": result, "snapshot": after})
    print("staging migration and READY no-op validation: PASS")


if __name__ == "__main__":
    main()
