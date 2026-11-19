"""Deterministic fake provider CLI for the 02C supervisor tests (no network, no provider).

It reads the prompt from stdin, then behaves according to --scenario.  Counters live in
--state-file so a scenario can fail N times and then succeed across separate processes.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

STATUS = {"coordenador": ("planned", "Orquestrador"), "orquestrador": ("ready", "Code"), "code": ("implemented", "Reviewer"), "reviewer": ("reviewed", "QA"), "qa": ("tested", "Gate"), "gate": ("evaluated", "HUMAN")}


def result(role: str, task_id: str, *, verdict: str | None = None, changed: list[str] | None = None, **override) -> dict:
    status, nxt = STATUS[role]
    value = {"protocol": "AGENT_RESULT", "role": role, "task_id": task_id, "status": status, "verdict": verdict, "next_agent": nxt, "scope_changed": False, "blocking_issue": False,
             "changed_files": changed or [], "evidence": [{"criterion": f"{role}-criterio", "command": "fake", "cwd": None, "version": "fake-1", "stdout_log": None, "stderr_log": None, "exit_code": 0, "semantic_verdict": "pass"}],
             "limitations": ["CLI fake determinística"], "commit_performed": False, "push_performed": False, "human_approval": "pending"}
    value.update(override)
    return value


def bump(state_file: str | None) -> int:
    if not state_file:
        return 1
    path = Path(state_file)
    count = int(path.read_text()) + 1 if path.exists() else 1
    path.write_text(str(count))
    return count


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--scenario", default="pass")
    ap.add_argument("--role", required=True)
    ap.add_argument("--task-id", required=True)
    ap.add_argument("--state-file")
    ap.add_argument("--fail-times", type=int, default=1)
    ap.add_argument("--write", help="path (relative to cwd) the fake agent creates")
    ap.add_argument("--declare", help="changed_files entry to declare (defaults to --write)")
    ap.add_argument("--pid-file")
    args = ap.parse_args()
    sys.stdin.buffer.read()  # consume the prompt like a real CLI
    role, task = args.role, args.task_id
    n = bump(args.state_file)
    changed = None
    if args.write:
        Path(args.write).parent.mkdir(parents=True, exist_ok=True)
        Path(args.write).write_text(f"written by fake {role} #{n}\n", encoding="utf-8")
        changed = [] if args.declare == "-" else [args.declare or args.write]  # "-" = write without declaring it
    scenario = args.scenario
    if scenario == "exit1":
        print("falha deliberada", file=sys.stderr)
        return 3
    if scenario == "flaky":
        if n <= args.fail_times:
            print("falha transitória", file=sys.stderr)
            return 1
        scenario = "pass"
    if scenario == "hang":
        child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(600)"])
        if args.pid_file:
            Path(args.pid_file).write_text(f"{os.getpid()} {child.pid}")
        time.sleep(600)
        return 0
    if scenario == "garbage":
        print("sem JSON aqui")
        return 0
    if scenario == "nan":
        print('{"protocol": "AGENT_RESULT", "x": NaN}')
        return 0
    if scenario == "two":
        print(json.dumps(result(role, task)), json.dumps(result(role, task)))
        return 0
    if scenario == "wrong_role":
        other = "gate" if role != "gate" else "qa"
        print(json.dumps(result(other, task)))
        return 0
    if scenario == "approve":
        print(json.dumps(result(role, task, human_approval="approved")))
        return 0
    if scenario == "commit":
        print(json.dumps(result(role, task, commit_performed=True)))
        return 0
    if scenario == "secret":
        print("log token=SUPERSECRET123 e Bearer abcdefghijklmnopqrstuvwxyz")
    verdict = "pass" if role in ("reviewer", "qa", "gate") else None
    if scenario == "judge_fail_once" and role in ("reviewer", "qa", "gate") and n <= args.fail_times:
        print(json.dumps(result(role, task, verdict="fail", status="changes_required", next_agent="Code")))
        return 0
    if scenario == "always_fail" and role in ("reviewer", "qa", "gate"):
        print(json.dumps(result(role, task, verdict="fail", status="changes_required", next_agent="Code")))
        return 0
    if scenario == "inconclusive" and role in ("reviewer", "qa", "gate"):
        print(json.dumps(result(role, task, verdict="inconclusive")))
        return 0
    print(f"Relatório do {role} (execução {n}).")
    print("```json")
    print(json.dumps(result(role, task, verdict=verdict, changed=changed)))
    print("```")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
