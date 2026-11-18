"""E3 persistence for change events, task runs and proposals."""

from __future__ import annotations

import json
import sqlite3
import uuid
import hashlib
from pathlib import Path


class StateStore:
    def __init__(self, root: Path) -> None:
        self.path = root / ".kbkit" / "state.sqlite"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(self.path)
        self.connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS change_events (
                event_id TEXT PRIMARY KEY, source_kind TEXT NOT NULL, source_ref TEXT NOT NULL,
                observed_at TEXT NOT NULL, before_hash TEXT, after_hash TEXT, cursor TEXT
            );
            CREATE TABLE IF NOT EXISTS task_runs (
                run_id TEXT PRIMARY KEY, task_id TEXT NOT NULL, started_at TEXT NOT NULL,
                finished_at TEXT, status TEXT NOT NULL, input_cursor TEXT, report_ref TEXT
            );
            CREATE TABLE IF NOT EXISTS proposals (
                proposal_id TEXT PRIMARY KEY, risk_level TEXT NOT NULL, reason TEXT NOT NULL,
                diff_ref TEXT, owner TEXT, due_at TEXT, status TEXT NOT NULL, payload TEXT NOT NULL
            );
            """
        )
        self.connection.commit()

    def record_event(self, source_kind: str, source_ref: str, before_hash: str | None, after_hash: str | None, cursor: str | None, commit: bool = True) -> str:
        event_id = str(uuid.uuid4())
        self.connection.execute(
            "INSERT INTO change_events VALUES (?, ?, ?, datetime('now'), ?, ?, ?)",
            (event_id, source_kind, source_ref, before_hash, after_hash, cursor),
        )
        if commit:
            self.connection.commit()
        return event_id

    def start_task(self, task_id: str, cursor: str | None = None) -> str:
        run_id = str(uuid.uuid4())
        self.connection.execute(
            "INSERT INTO task_runs(run_id, task_id, started_at, status, input_cursor) VALUES (?, ?, datetime('now'), ?, ?)",
            (run_id, task_id, "running", cursor),
        )
        self.connection.commit()
        return run_id

    def finish_task(self, run_id: str, status: str, report_ref: str | None = None) -> None:
        if status not in {"succeeded", "failed", "partial"}:
            raise ValueError("invalid task status")
        self.connection.execute(
            "UPDATE task_runs SET finished_at = datetime('now'), status = ?, report_ref = ? WHERE run_id = ?",
            (status, report_ref, run_id),
        )
        self.connection.commit()

    def create_proposal(self, risk_level: str, reason: str, payload: dict, diff_ref: str | None = None) -> str:
        if risk_level not in {"low", "medium", "high"}:
            raise ValueError("invalid risk level")
        proposal_id = str(uuid.uuid4())
        encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        self.connection.execute(
            "INSERT INTO proposals VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (proposal_id, risk_level, reason, diff_ref, None, None, "pending", encoded),
        )
        self.connection.commit()
        return proposal_id

    def set_proposal_status(self, proposal_id: str, status: str) -> None:
        if status not in {"approved", "rejected", "applied", "expired", "conflicted"}:
            raise ValueError("invalid proposal status")
        self.connection.execute("UPDATE proposals SET status = ? WHERE proposal_id = ?", (status, proposal_id))
        self.connection.commit()

    def list_proposals(self, status: str | None = None) -> list[tuple]:
        if status is None:
            return list(self.connection.execute("SELECT proposal_id, risk_level, reason, status, payload FROM proposals ORDER BY rowid"))
        return list(self.connection.execute("SELECT proposal_id, risk_level, reason, status, payload FROM proposals WHERE status = ? ORDER BY rowid", (status,)))

    def get_proposal(self, proposal_id: str) -> tuple | None:
        return self.connection.execute("SELECT proposal_id, risk_level, reason, status, payload FROM proposals WHERE proposal_id = ?", (proposal_id,)).fetchone()

    def has_open_proposal(self, reason: str, payload: dict) -> bool:
        encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        rows = self.connection.execute(
            "SELECT payload FROM proposals WHERE reason = ? AND status IN ('pending', 'approved')",
            (reason,),
        )
        for (stored,) in rows:
            try:
                if json.dumps(json.loads(stored), ensure_ascii=False, sort_keys=True, separators=(",", ":")) == encoded:
                    return True
            except json.JSONDecodeError:
                continue
        return False

    def expire_missing_findings(self, active_findings: list[dict]) -> int:
        """Expire pending lint proposals whose finding is no longer present."""
        active = {
            json.dumps(item, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
            for item in active_findings
        }
        rows = self.connection.execute(
            "SELECT proposal_id, payload FROM proposals WHERE status = 'pending'"
        ).fetchall()
        expired = 0
        for proposal_id, stored in rows:
            try:
                payload = json.loads(stored)
            except json.JSONDecodeError:
                continue
            if "rule" not in payload:
                continue
            fingerprint = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
            if fingerprint not in active:
                self.connection.execute(
                    "UPDATE proposals SET status = 'expired' WHERE proposal_id = ?",
                    (proposal_id,),
                )
                expired += 1
        self.connection.commit()
        return expired

    def record_session_artifact(self, session_ref: str, content: str, retention: str, consent: bool) -> str:
        if not consent:
            raise ValueError("session artifact requires explicit consent")
        artifact_id = str(uuid.uuid4())
        artifact_dir = self.path.parent / "artifacts"
        artifact_dir.mkdir(parents=True, exist_ok=True)
        content_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()
        (artifact_dir / f"{artifact_id}.txt").write_text(content, encoding="utf-8")
        self.connection.execute(
            "CREATE TABLE IF NOT EXISTS session_artifacts (artifact_id TEXT PRIMARY KEY, session_ref TEXT, captured_at TEXT, content_hash TEXT, retention TEXT, consent INTEGER)"
        )
        self.connection.execute("INSERT INTO session_artifacts VALUES (?, ?, datetime('now'), ?, ?, ?)", (artifact_id, session_ref, content_hash, retention, int(consent)))
        self.connection.commit()
        return artifact_id

    def close(self) -> None:
        self.connection.close()
