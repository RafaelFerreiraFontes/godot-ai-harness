#!/usr/bin/env python3
"""02C supervisor CLI: plan / run / resume / status / abort.

Safe by default: `plan` and `run --dry-run` never start a process or write anything;
`run --execute` starts provider CLIs only for roles named in --authorize (or confirmed
interactively with --confirm-each).  Approval of the final result is always human.
"""

from __future__ import annotations

import argparse
import json
import signal
import sys
import threading
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

if sys.version_info < (3, 11):  # tomllib; the PATH `python` here may be 3.10 — use `py -3`
    print(json.dumps({"error": "Python >= 3.11 é necessário (use py -3)"}), file=sys.stderr)
    raise SystemExit(2)

from supervisor.config import ROLES, ConfigError, load_config  # noqa: E402
from supervisor.engine import AuthRequest, Supervisor  # noqa: E402
from supervisor.monitor import status  # noqa: E402
from supervisor.states import ROUTE, State  # noqa: E402
from supervisor.store import StoreError  # noqa: E402


def emit(value: object) -> None:
    print(json.dumps(value, ensure_ascii=False, indent=2))


def make_authorizer(args: argparse.Namespace):
    allowed = {r.strip() for r in (args.authorize or "").split(",") if r.strip()}
    unknown = allowed - set(ROLES)
    if unknown:
        raise ConfigError([f"--authorize com papel inválido: {sorted(unknown)}"])

    def authorize(request: AuthRequest) -> bool:
        if args.confirm_each:
            answer = input(f"Autorizar {request.role} (modelo {request.model}, {request.executable})? [s/N] ")
            return answer.strip().lower() in ("s", "sim", "y", "yes")
        return request.role in allowed

    return authorize


def build(args: argparse.Namespace, *, authorizer=None, cancel=None) -> Supervisor:
    config = load_config(Path(args.config), test_mode=args.test_mode)
    return Supervisor(Path(args.root), config, authorizer=authorizer, cancel_event=cancel)


def exit_for(run: dict) -> int:
    return 1 if run["state"] in (State.BLOCKED.value, State.FAILED.value, State.ABORTED.value, State.ITERATION_LIMIT_EXCEEDED.value) else 0


def cmd_plan(args: argparse.Namespace) -> int:
    report = build(args).plan(args.task_id, args.from_role)
    emit(report)
    return 0 if report["ready"] else 1


def install_sigint(cancel: threading.Event) -> None:
    signal.signal(signal.SIGINT, lambda *_: cancel.set())


def cmd_run(args: argparse.Namespace) -> int:
    if args.dry_run == args.execute:
        raise ConfigError(["escolha exatamente um: --dry-run ou --execute"])
    if args.dry_run:
        return cmd_plan(args)
    request = Path(args.request).read_text(encoding="utf-8-sig") if args.request else ""
    cancel = threading.Event()
    install_sigint(cancel)
    run = build(args, authorizer=make_authorizer(args), cancel=cancel).start(args.task_id, request, args.from_role, "test" if args.test_mode else "execute")
    emit({"run_id": run["run_id"], "state": run["state"], "reason": run.get("reason")})
    return exit_for(run)


def cmd_resume(args: argparse.Namespace) -> int:
    if not args.confirm:
        raise ConfigError(["retomada exige --confirm explícito"])
    cancel = threading.Event()
    install_sigint(cancel)
    run = build(args, authorizer=make_authorizer(args), cancel=cancel).resume(args.task_id, args.run_id)
    emit({"run_id": run["run_id"], "state": run["state"], "reason": run.get("reason")})
    return exit_for(run)


def cmd_status(args: argparse.Namespace) -> int:
    emit(status(Path(args.root).resolve(), args.task_id, args.run_id))
    return 0


def cmd_abort(args: argparse.Namespace) -> int:
    run = build(args).abort(args.task_id, args.run_id)
    emit({"run_id": run["run_id"], "state": run["state"]})
    return 0


def parser() -> argparse.ArgumentParser:
    top = argparse.ArgumentParser(description=__doc__)
    top.add_argument("--root", default=".", help="raiz do worktree")
    sub = top.add_subparsers(dest="command", required=True)

    def common(p: argparse.ArgumentParser, task: bool = True) -> None:
        p.add_argument("--config", required=True)
        p.add_argument("--test-mode", action="store_true", help="aceita provider 'fake' (somente fixtures)")
        if task:
            p.add_argument("--task-id", required=True)

    plan = sub.add_parser("plan")
    common(plan)
    plan.add_argument("--from-role", choices=ROUTE, default="coordenador")
    plan.set_defaults(func=cmd_plan)
    run = sub.add_parser("run")
    common(run)
    run.add_argument("--from-role", choices=ROUTE, default="coordenador")
    run.add_argument("--request", help="arquivo com o pedido/plano (dado não confiável)")
    run.add_argument("--dry-run", action="store_true")
    run.add_argument("--execute", action="store_true")
    run.add_argument("--authorize", help="papéis autorizados a executar, separados por vírgula")
    run.add_argument("--confirm-each", action="store_true")
    run.set_defaults(func=cmd_run)
    resume = sub.add_parser("resume")
    common(resume)
    resume.add_argument("--run-id", required=True)
    resume.add_argument("--confirm", action="store_true")
    resume.add_argument("--authorize")
    resume.add_argument("--confirm-each", action="store_true")
    resume.set_defaults(func=cmd_resume)
    stat = sub.add_parser("status")
    stat.add_argument("--task-id")
    stat.add_argument("--run-id")
    stat.set_defaults(func=cmd_status)
    abort = sub.add_parser("abort")
    common(abort)
    abort.add_argument("--run-id", required=True)
    abort.set_defaults(func=cmd_abort)
    return top


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        return args.func(args)
    except (ConfigError, StoreError, OSError) as exc:
        errors = exc.errors if isinstance(exc, ConfigError) else [str(exc)]
        print(json.dumps({"error": errors}, ensure_ascii=False), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
