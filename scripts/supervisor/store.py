"""RunStore: atomic state.json, hash-chained events.jsonl, per-task and per-run locks.

Lives under .chat-decisions/runs/<task_id>/<run_id>/ (private, git-ignored).
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
import re
from pathlib import Path
from typing import Any

import agent_handoff as handoff

SAFE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")


class StoreError(RuntimeError):
    pass


def now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


class RunStore:
    def __init__(self, root: Path, task_id: str, run_id: str) -> None:
        for label, value in (("task_id", task_id), ("run_id", run_id)):
            if not SAFE.fullmatch(value):
                raise StoreError(f"{label} inválido")
        self.root = root
        self.task_id, self.run_id = task_id, run_id
        self.dir = root / ".chat-decisions" / "runs" / task_id / run_id
        self.state_path = self.dir / "state.json"
        self.events_path = self.dir / "events.jsonl"

    # --- locks -------------------------------------------------------------------
    def acquire(self) -> Path:
        """One live supervisor per task: refuse while another process owns the lock."""
        lock = self.dir.parent / "active.lock"
        lock.parent.mkdir(parents=True, exist_ok=True)
        for _ in range(2):
            try:
                fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            except FileExistsError:
                if handoff.Journal._stale(lock):
                    lock.unlink(missing_ok=True)
                    continue
                raise StoreError(f"já existe uma execução ativa para {self.task_id}: {lock}")
            os.write(fd, f"pid={os.getpid()} run={self.run_id}\n".encode())
            os.close(fd)
            return lock
        raise StoreError(f"não foi possível adquirir {lock}")

    @staticmethod
    def release(lock: Path) -> None:
        lock.unlink(missing_ok=True)

    # --- state ---------------------------------------------------------------------
    def save_state(self, state: dict[str, Any]) -> None:
        self.dir.mkdir(parents=True, exist_ok=True)
        state["updated_at"] = now_iso()
        handoff.atomic_write(self.state_path, json.dumps(state, ensure_ascii=False, indent=2, sort_keys=True) + "\n")

    def load_state(self) -> dict[str, Any]:
        try:
            return handoff.load_json(self.state_path)
        except (OSError, ValueError) as exc:
            raise StoreError(f"state.json ilegível: {exc}") from exc

    # --- events (append-only, hash chained) ----------------------------------------
    def _last_hash(self) -> tuple[int, str]:
        if not self.events_path.exists():
            return 0, "0" * 64
        last = None
        for line in self.events_path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                last = json.loads(line)
        return (last["seq"], last["hash"]) if last else (0, "0" * 64)

    def append_event(self, kind: str, data: dict[str, Any]) -> None:
        self.dir.mkdir(parents=True, exist_ok=True)
        seq, prev = self._last_hash()
        body = {"seq": seq + 1, "ts": now_iso(), "type": kind, "data": data, "prev": prev}
        digest = hashlib.sha256(json.dumps(body, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()
        with self.events_path.open("a", encoding="utf-8", newline="\n") as handle:
            handle.write(json.dumps({**body, "hash": digest}, ensure_ascii=False) + "\n")
            handle.flush()
            os.fsync(handle.fileno())

    def read_events(self) -> list[dict[str, Any]]:
        if not self.events_path.exists():
            return []
        return [json.loads(line) for line in self.events_path.read_text(encoding="utf-8").splitlines() if line.strip()]

    def verify_events(self) -> bool:
        prev = "0" * 64
        for event in self.read_events():
            body = {k: event[k] for k in ("seq", "ts", "type", "data", "prev")}
            if event["prev"] != prev or event["hash"] != hashlib.sha256(json.dumps(body, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest():
                return False
            prev = event["hash"]
        return True

    # --- cancellation flag (cross-process abort) -----------------------------------
    @property
    def cancel_flag(self) -> Path:
        return self.dir / "cancel.flag"

    def request_cancel(self) -> None:
        self.dir.mkdir(parents=True, exist_ok=True)
        self.cancel_flag.write_text(now_iso(), encoding="utf-8")


def list_runs(root: Path, task_id: str | None = None) -> list[tuple[str, str]]:
    base = root / ".chat-decisions" / "runs"
    if not base.is_dir():
        return []
    out = []
    for task_dir in sorted(p for p in base.iterdir() if p.is_dir() and (task_id is None or p.name == task_id)):
        out.extend((task_dir.name, run.name) for run in sorted(task_dir.iterdir()) if (run / "state.json").is_file())
    return out
