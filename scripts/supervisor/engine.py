"""Supervisor engine: drives PENDING -> ... -> AWAITING_HUMAN with explicit limits.

All side effects are injected (runner, snapshotter, authorizer, which), so the whole
route can be exercised with fake CLIs.  The engine never sets human_approval and never
launches anything unless the caller chose execute mode *and* the authorizer allows it.
"""

from __future__ import annotations

import fnmatch
import hashlib
import json
import re
import shutil
import threading
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

import agent_handoff as handoff

from . import contract, prompts
from .config import AgentConfig, SupervisorConfig, resolve_executable
from .runner import IsolationError, ProcessCleanupError, ProcessOutcome, ProcessRunner, ProcessSpec, Runner
from .states import ROUTE, TERMINAL, Decision, InvalidTransition, State, check_transition, decide
from .store import RunStore, StoreError, now_iso
from .workspace import Snapshot, SnapshotError, Snapshotter, changed_paths, ownership_violations, take_snapshot

EXTRA_SECRET = re.compile(r"(?i)(bearer\s+[A-Za-z0-9._~+/=-]{12,}|sk-[A-Za-z0-9_-]{16,}|gh[pousr]_[A-Za-z0-9]{20,}|AIza[0-9A-Za-z_-]{20,})")


def redact(text: str) -> str:
    """02B key=value masking plus bare tokens that appear in CLI output (M6b)."""
    return EXTRA_SECRET.sub("[REDACTED]", handoff.redact(text))


@dataclass(frozen=True)
class AuthRequest:
    task_id: str
    run_id: str
    role: str
    model: str
    executable: str
    iteration: int
    argv_preview: list[str]


Authorizer = Callable[[AuthRequest], bool]


def sha(text: str | bytes) -> str:
    return hashlib.sha256(text if isinstance(text, bytes) else text.encode("utf-8")).hexdigest()


class Supervisor:
    def __init__(self, root: Path, config: SupervisorConfig, *, runner: Runner | None = None, authorizer: Authorizer | None = None, snapshotter: Snapshotter = take_snapshot,
                 which: Callable[[str], str | None] = shutil.which, run_id: str | None = None, cancel_event: threading.Event | None = None) -> None:
        self.root = root.resolve()
        self.config = config
        self.runner = runner or ProcessRunner()
        self.authorizer: Authorizer = authorizer or (lambda request: False)
        self.snapshotter = snapshotter
        self.which = which
        self.fixed_run_id = run_id
        self.cancel_event = cancel_event or threading.Event()
        self.journal = handoff.Journal(self.root)

    # ---- planning (no process, no writes) --------------------------------------------
    def plan(self, task_id: str, start_role: str = "coordenador") -> dict[str, Any]:
        self._check_role(start_role)
        steps = []
        for role in ROUTE[ROUTE.index(start_role):]:
            agent = self.config.agents.get(role)
            if agent is None:
                steps.append({"role": role, "configured": False, "problems": ["papel sem configuração"]})
                continue
            executable = resolve_executable(agent, self.which)
            adapter = contract.adapter_for(agent.provider)
            try:
                argv = adapter.build_argv(agent, executable or agent.executable, task_id=task_id, cwd=str(self.root), prompt="<prompt>", prompt_file="<prompt_file>")
            except contract.AdapterError as exc:
                argv = []
                problems = [str(exc)]
            else:
                problems = [] if executable else [f"executável {agent.executable!r} não encontrado no PATH"]
            steps.append({"role": role, "configured": True, "provider": agent.provider, "model": agent.model, "executable": executable, "argv_preview": argv,
                          "prompt_via": agent.prompt_via, "timeout_seconds": agent.timeout_seconds, "writes": list(agent.ownership), "problems": problems})
        ready = all(s.get("configured") and not s["problems"] for s in steps)
        return {"task_id": task_id, "dry_run": True, "process_started": False, "limits": {"max_iterations": self.config.limits.max_iterations, "max_attempts": self.config.limits.max_attempts, "retry_on": list(self.config.limits.retry_on)}, "steps": steps, "ready": ready}

    # ---- run lifecycle -----------------------------------------------------------------
    def start(self, task_id: str, request: str, start_role: str = "coordenador", mode: str = "execute") -> dict[str, Any]:
        self._check_role(start_role)
        missing = [r for r in ROUTE[ROUTE.index(start_role):] if r not in self.config.agents]
        if missing:
            raise StoreError(f"papéis sem configuração: {', '.join(missing)}")
        run_id = self.fixed_run_id or f"{now_iso().replace(':', '-').replace('.', '-')}-{uuid.uuid4().hex[:6]}"
        store = RunStore(self.root, task_id, run_id)
        lock = store.acquire()
        try:
            run: dict[str, Any] = {"format": 1, "run_id": run_id, "task_id": task_id, "mode": mode, "config_digest": self.config.digest, "state": State.PENDING.value, "created_at": now_iso(), "request": redact(request),
                                   "start_role": start_role, "steps": [self._new_step(0, start_role, 0, None)], "current": 0, "reason": None}
            try:
                snap = self.snapshotter(self.root)
            except SnapshotError as exc:
                return self._finish_blocked(store, run, "baseline_unavailable", str(exc))
            run["baseline"] = run["last_snapshot"] = snap.to_json()
            store.save_state(run)
            store.append_event("run_created", {"start_role": start_role, "mode": mode, "head": snap.head, "config_digest": self.config.digest})
            return self._drive(store, run)
        finally:
            store.release(lock)

    def resume(self, task_id: str, run_id: str) -> dict[str, Any]:
        store = RunStore(self.root, task_id, run_id)
        run = store.load_state()
        if run["state"] in {s.value for s in TERMINAL}:
            raise StoreError(f"execução já terminal ({run['state']}); abra uma nova execução")
        if run["config_digest"] != self.config.digest:
            raise StoreError("configuração mudou desde o início da execução; retomada recusada")
        if not store.verify_events():
            raise StoreError("cadeia de eventos inconsistente; reconciliação humana necessária")
        lock = store.acquire()
        try:
            return self._resume_locked(store, run)
        finally:
            store.release(lock)

    def _resume_locked(self, store: RunStore, run: dict[str, Any]) -> dict[str, Any]:
        state, step = run["state"], self._step(run)
        try:
            now = self.snapshotter(self.root)
        except SnapshotError as exc:
            return self._finish_blocked(store, run, "baseline_unavailable", str(exc))
        mid_step = state in (State.RUNNING.value, State.VALIDATING.value)
        reference = Snapshot.from_json(step["snapshot_before"] if mid_step and step.get("snapshot_before") else run["last_snapshot"])
        if now.head != reference.head:
            return self._finish_blocked(store, run, "drift", f"HEAD mudou ({reference.head[:12]} -> {now.head[:12]})")
        if not mid_step and now.digest() != reference.digest():
            return self._finish_blocked(store, run, "drift", "árvore de trabalho difere do último snapshot registrado")
        if mid_step:
            problems = ownership_violations(step["role"], changed_paths(reference, now), self.config.agents[step["role"]].ownership, False)
            if problems:
                return self._finish_blocked(store, run, "ownership_violation", "; ".join(problems))
        if state == State.RUNNING.value and step["attempts"]:
            last = step["attempts"][-1]
            if not last.get("completed"):
                pid = last.get("pid")
                if pid and handoff.pid_alive(int(pid)):
                    return self._finish_blocked(store, run, "process_possibly_alive", f"PID {pid} ainda existe; identidade não comprovável, reconcilie manualmente")
                last.update({"completed": True, "classification": "interrupted", "ended_at": now_iso()})
                store.append_event("attempt_interrupted", {"step": step["index"], "attempt": last["n"]})
                if len(step["attempts"]) >= self.config.limits.max_attempts:
                    return self._finish_blocked(store, run, "attempt_limit", "tentativa interrompida e limite de tentativas atingido")
            else:  # crash after the attempt finished but before the state moved on: reconcile, never relaunch blindly
                kind = last.get("classification") or ("ok" if last.get("exit_code") == 0 else "process_failed")
                limits = self.config.limits
                if kind == "ok":
                    store.append_event("resumed_reconciled", {"step": step["index"], "attempt": last["n"], "to": "VALIDATING"})
                    self._set(store, run, State.VALIDATING, "reconciled", "tentativa concluída antes da queda; validando sem relançar")
                    return self._drive(store, run)
                if kind == "cancelled":
                    self._set(store, run, State.ABORTED, "cancelled", "tentativa cancelada antes da queda")
                    return run
                if kind == "spawn_failed":
                    return self._finish_blocked(store, run, "spawn_failed", "falha de spawn registrada antes da queda")
                if kind not in limits.retry_on or len(step["attempts"]) >= limits.max_attempts:
                    self._set(store, run, State.FAILED, kind, f"{kind} sem tentativas restantes (limite {limits.max_attempts})")
                    return run
        store.append_event("resumed", {"state": state, "step": step["index"]})
        return self._drive(store, run)

    def abort(self, task_id: str, run_id: str) -> dict[str, Any]:
        store = RunStore(self.root, task_id, run_id)
        run = store.load_state()
        if run["state"] in {s.value for s in TERMINAL}:
            return run
        store.request_cancel()  # a live supervisor stops its child; otherwise finalize below
        try:
            lock = store.acquire()
        except StoreError:
            return run  # live supervisor will observe the flag
        try:
            run = store.load_state()
            self._set(store, run, State.ABORTED, "abort", "cancelamento solicitado por operador")
            return run
        finally:
            store.release(lock)

    # ---- the loop ---------------------------------------------------------------------
    def _drive(self, store: RunStore, run: dict[str, Any]) -> dict[str, Any]:
        while True:
            state = State(run["state"])
            if state in TERMINAL:
                return run
            if self._cancelled(store):
                self._set(store, run, State.ABORTED, "cancelled", "cancelamento solicitado")
                return run
            step = self._step(run)
            try:
                if state is State.PENDING:
                    self._prepare(store, run, step)
                elif state is State.AWAITING_AUTHORIZATION:
                    if not self._authorize(store, run, step):
                        return run  # resting state: resume once the human authorizes
                elif state is State.RUNNING:
                    self._attempt(store, run, step)
                elif state is State.VALIDATING:
                    self._validate_and_record(store, run, step)
                elif state is State.RECORDED:
                    self._advance(store, run, step)
            except ProcessCleanupError as exc:  # the child may still be alive: keep its PID, never retry
                if step["attempts"]:
                    last = step["attempts"][-1]
                    last.update({"pid": last.get("pid") or exc.pid, "completed": True, "classification": "process_unkillable"})
                self._finish_blocked(store, run, "process_unkillable", str(exc))
            except IsolationError as exc:
                self._finish_blocked(store, run, "isolation_unavailable", str(exc))
            except (SnapshotError, StoreError, OSError, InvalidTransition) as exc:
                self._finish_blocked(store, run, "supervisor_error", f"{exc.__class__.__name__}: {exc}")

    # ---- steps ------------------------------------------------------------------------
    def _prepare(self, store: RunStore, run: dict[str, Any], step: dict[str, Any]) -> None:
        agent = self._agent(step)
        executable = resolve_executable(agent, self.which)
        if executable is None:
            self._finish_blocked(store, run, "executable_missing", f"{agent.executable!r} não encontrado no PATH (papel {agent.role}); sem fallback de provider")
            return
        prompt = prompts.build_prompt(step["role"], run["task_id"], step["iteration"], run["request"], step["previous"], agent.ownership)
        step["prompt"] = redact(prompt)
        step["prompt_sha256"] = sha(step["prompt"])
        step["executable"] = executable
        step["snapshot_before"] = self.snapshotter(self.root).to_json()
        self._set(store, run, State.AWAITING_AUTHORIZATION, "prepared", f"passo {step['index']} {step['role']} preparado")

    def _authorize(self, store: RunStore, run: dict[str, Any], step: dict[str, Any]) -> bool:
        agent = self._agent(step)
        argv = self._argv(agent, step, run, prompt="<prompt>", prompt_file="<prompt_file>")
        request = AuthRequest(run["task_id"], run["run_id"], step["role"], agent.model, step["executable"], step["iteration"], argv)
        if not self.authorizer(request):
            store.append_event("authorization_pending", {"step": step["index"], "role": step["role"]})
            store.save_state(run)
            return False
        store.append_event("authorized", {"step": step["index"], "role": step["role"], "model": agent.model})
        self._set(store, run, State.RUNNING, "authorized", "execução autorizada")
        return True

    def _argv(self, agent: AgentConfig, step: dict[str, Any], run: dict[str, Any], *, prompt: str, prompt_file: str) -> list[str]:
        adapter = contract.adapter_for(agent.provider)
        return adapter.build_argv(agent, step["executable"], task_id=run["task_id"], cwd=str(self.root), prompt=prompt, prompt_file=prompt_file)

    def _attempt(self, store: RunStore, run: dict[str, Any], step: dict[str, Any]) -> None:
        agent, limits = self._agent(step), self.config.limits
        if step["attempts"] and not step["attempts"][-1].get("completed"):
            step["attempts"][-1].update({"completed": True, "classification": "interrupted"})
        n = len(step["attempts"]) + 1
        if n > limits.max_attempts:  # hard guard: no path may launch beyond the configured limit
            self._finish_blocked(store, run, "attempt_limit", f"tentativa {n} excede max_attempts={limits.max_attempts}")
            return
        folder = store.dir / "steps" / f"{step['index']:02d}-{step['role']}" / f"attempt-{n}"
        folder.mkdir(parents=True, exist_ok=True)
        prompt_file = folder / "prompt.md"
        handoff.atomic_write(prompt_file, step["prompt"])
        attempt = {"n": n, "started_at": now_iso(), "pid": None, "completed": False, "dir": self._rel(folder)}
        step["attempts"].append(attempt)
        store.save_state(run)

        def started(pid: int) -> None:
            attempt["pid"] = pid
            store.append_event("process_started", {"step": step["index"], "attempt": n, "pid": pid})
            store.save_state(run)

        argv = self._argv(agent, step, run, prompt=step["prompt"], prompt_file=str(prompt_file))
        spec = ProcessSpec(argv, str(self.root), self._env(agent), step["prompt"] if agent.prompt_via == "stdin" else None, agent.timeout_seconds, agent.max_output_bytes)
        outcome = self.runner.run(spec, lambda: self._cancelled(store), started)
        self._store_outcome(folder, attempt, outcome, agent, argv)
        if outcome.cancelled:
            attempt["classification"] = "cancelled"
        elif outcome.error:
            attempt["classification"] = "spawn_failed"
        elif outcome.timed_out:
            attempt["classification"] = "timeout"
        elif outcome.exit_code != 0:
            attempt["classification"] = "process_failed"
        else:
            attempt["classification"] = "ok"
        attempt["completed"] = True
        store.append_event("process_finished", {"step": step["index"], "attempt": n, "exit_code": outcome.exit_code, "classification": attempt["classification"], "duration": outcome.duration_seconds})
        store.save_state(run)
        kind = attempt["classification"]
        if kind == "ok":
            self._set(store, run, State.VALIDATING, "process_ok", "processo concluído; validando resultado")
        elif kind == "cancelled":
            self._set(store, run, State.ABORTED, "cancelled", "processo cancelado; árvore encerrada")
        else:
            problems = self._ownership_problems(step, agent)
            if problems:
                self._finish_blocked(store, run, "ownership_violation", "; ".join(problems))
            elif kind == "spawn_failed":
                self._finish_blocked(store, run, "spawn_failed", outcome.error or "")
            elif kind in limits.retry_on and n < limits.max_attempts:
                store.append_event("retry", {"step": step["index"], "after": kind, "next_attempt": n + 1})
                self._set(store, run, State.RUNNING, "retry", f"nova tentativa após {kind}")
            else:
                self._set(store, run, State.FAILED, kind, f"{kind} sem tentativas restantes (limite {limits.max_attempts})")

    def _store_outcome(self, folder: Path, attempt: dict[str, Any], outcome: ProcessOutcome, agent: AgentConfig, argv: list[str]) -> None:
        out = redact(outcome.stdout.decode("utf-8", "replace"))
        err = redact(outcome.stderr.decode("utf-8", "replace"))
        handoff.atomic_write(folder / "stdout.log", out)
        handoff.atomic_write(folder / "stderr.log", err)
        meta = {"pid": outcome.pid, "exit_code": outcome.exit_code, "timed_out": outcome.timed_out, "cancelled": outcome.cancelled, "duration_seconds": outcome.duration_seconds,
                "isolation": outcome.isolation, "stdout_truncated": outcome.stdout_truncated, "stderr_truncated": outcome.stderr_truncated, "error": outcome.error,
                "model_configured": agent.model, "runtime_model_verified": False, "argv": [redact(a) if len(a) < 300 else "<omitted>" for a in argv]}
        handoff.atomic_write(folder / "meta.json", json.dumps(meta, ensure_ascii=False, indent=2) + "\n")
        attempt.update({"exit_code": outcome.exit_code, "ended_at": now_iso(), "stdout_sha256": sha(out), "stderr_sha256": sha(err), "duration_seconds": outcome.duration_seconds, "isolation": outcome.isolation})

    def _validate_and_record(self, store: RunStore, run: dict[str, Any], step: dict[str, Any]) -> None:
        agent, attempt = self._agent(step), step["attempts"][-1]
        folder = self.root / attempt["dir"]
        raw_stdout = (folder / "stdout.log").read_bytes()  # bytes: text mode would rewrite CRLF and break the hash
        stdout = raw_stdout.decode("utf-8")
        if sha(raw_stdout) != attempt.get("stdout_sha256"):
            self._finish_blocked(store, run, "log_integrity", "stdout.log não confere com o hash registrado")
            return
        text = contract.adapter_for(agent.provider).extract_text(stdout)
        result, errors = contract.validate_contract(step["role"], run["task_id"], contract.extract_results(text), agent.required_criteria)
        if result is None:
            self._finish_blocked(store, run, "contract_invalid", "; ".join(errors))
            return
        before = Snapshot.from_json(step["snapshot_before"])
        after = self.snapshotter(self.root)
        changed = changed_paths(before, after)
        problems = ownership_violations(step["role"], changed, agent.ownership, before.head != after.head)
        if step["role"] == "code":
            hidden = sorted(set(changed) - set(result["changed_files"]))  # an identical rewrite leaves no diff, so extra declarations are fine
            if hidden:
                problems.append(f"Git observou alterações não declaradas em changed_files: {hidden}")
            problems += [f"changed_files declara fora do ownership: {path}" for path in sorted(set(result["changed_files"]) - set(changed)) if not any(fnmatch.fnmatch(path, g) for g in agent.ownership)]
        if problems:
            self._finish_blocked(store, run, "ownership_violation", "; ".join(problems))
            return
        decision = decide(step["role"], result, step["iteration"], self.config.limits.max_iterations)
        result = {k: v for k, v in result.items() if k != "metadata"}  # never trust agent-supplied metadata
        result["metadata"] = {"supervisor": {"run_id": run["run_id"], "step": step["index"], "iteration": step["iteration"], "attempt": attempt["n"], "provider": agent.provider, "model_configured": agent.model,
                                             "runtime_model_verified": False, "decision": decision.kind, "workspace_changed": changed, "stdout_sha256": attempt["stdout_sha256"], "stderr_sha256": attempt["stderr_sha256"]},
                              "criteria": [e["criterion"] for e in result["evidence"] if isinstance(e, dict) and isinstance(e.get("criterion"), str)]}
        prompt_log = redact(f"Prompt enviado a {step['role']} (sha256 {step['prompt_sha256']}); logs em {attempt['dir']}.\n\n{step['prompt']}").strip()
        resume = redact(prompts.resume_text(result, run["run_id"], step["index"], step["iteration"], agent.model)).strip()
        session = f"sup-{run['run_id']}-s{step['index']:02d}-a{attempt['n']}"[:128]
        files = self._existing_record(step["role"], run["task_id"], session)  # crash between record and RECORDED: adopt, never duplicate
        if files is None:
            try:
                files = self.journal.record(step["role"], run["task_id"], session, result, prompt_log, resume)
            except (ValueError, RuntimeError, OSError) as exc:
                self._finish_blocked(store, run, "persistence_failed", str(exc))
                return
        else:
            store.append_event("record_adopted", {"step": step["index"], "result": files["result"]})
        problem = self._verify_recorded(run["task_id"], files, result)
        if problem:
            self._finish_blocked(store, run, "persistence_uncertain", problem)
            return
        step.update({"result_path": files["result"], "resume_path": files["resume"], "prompt_log_path": files["prompt_log"], "decision": decision.__dict__})
        run["last_snapshot"] = after.to_json()
        self._set(store, run, State.RECORDED, "recorded", f"{step['role']} registrado em {files['result']}")

    def _existing_record(self, role: str, task_id: str, session: str) -> dict[str, str] | None:
        directory = self.journal.role_dir(role)
        if not directory.is_dir():
            return None
        for path in sorted(directory.glob(f"AGENT_RESULT_*_{task_id}_{session}.json")):
            try:
                artifacts = handoff.load_json(path).get("metadata", {}).get("artifacts", {})
                return {"result": self._rel(path), "prompt_log": artifacts["prompt_log"], "resume": artifacts["resume"]}
            except (OSError, ValueError, KeyError):
                return None
        return None

    def _verify_recorded(self, task_id: str, files: dict[str, str], submitted: dict[str, Any]) -> str | None:
        """Re-read every artifact and the index; any mismatch means the record cannot be trusted."""
        try:
            paths = {k: self.root / v for k, v in files.items()}
            stored = handoff.load_json(paths["result"])
            meta = stored.get("metadata", {})
            body = {k: v for k, v in stored.items() if k != "metadata"}
            expected = {k: v for k, v in submitted.items() if k != "metadata"}
            if body != expected or meta.get("content_sha256") != sha(json.dumps(body, sort_keys=True, ensure_ascii=False)):
                return "AGENT_RESULT relido difere do enviado ou do hash"
            log_text = handoff.decode_text(paths["prompt_log"].read_bytes())
            header = "# Registro não confiável\n\n"
            if not log_text.startswith(header) or sha(log_text[len(header):].strip()) != meta.get("prompt_log_sha256"):
                return "prompt-log não confere com o hash"
            if sha(paths["resume"].read_bytes()) != meta.get("resume_sha256"):
                return "prompt-resume não confere com o hash"
            if self.journal.latest(task_id)["result"] != files["result"]:
                return "índice não aponta para o resultado recém-registrado"
        except (OSError, ValueError, KeyError) as exc:
            return f"releitura falhou: {exc}"
        return None

    def _advance(self, store: RunStore, run: dict[str, Any], step: dict[str, Any]) -> None:
        decision = Decision(**step["decision"])
        if decision.kind == "human":
            self._set(store, run, State.AWAITING_HUMAN, "awaiting_human", "rota concluída; aprovação humana pendente (human_approval permanece pending)")
        elif decision.kind == "limit":
            self._set(store, run, State.ITERATION_LIMIT_EXCEEDED, "iteration_limit", decision.reason)
        elif decision.kind == "blocked":
            self._finish_blocked(store, run, "agent_blocked", decision.reason)
        else:
            result = handoff.load_json(self.root / step["result_path"])
            resume = handoff.decode_text((self.root / step["resume_path"]).read_bytes())
            package = prompts.package_from(result, step["result_path"], resume)
            if len(run["steps"]) != step["index"] + 1:
                raise StoreError("estado inconsistente: já existe passo após o atual")
            run["steps"].append(self._new_step(step["index"] + 1, decision.role or "", decision.iteration, package))
            run["current"] = step["index"] + 1
            self._set(store, run, State.PENDING, "next_step", f"{decision.reason}: {decision.role}")

    # ---- helpers ----------------------------------------------------------------------
    def _ownership_problems(self, step: dict[str, Any], agent: AgentConfig) -> list[str]:
        before = Snapshot.from_json(step["snapshot_before"])
        after = self.snapshotter(self.root)
        return ownership_violations(step["role"], changed_paths(before, after), agent.ownership, before.head != after.head)

    def _env(self, agent: AgentConfig) -> dict[str, str]:
        import os

        wanted = {name.upper() for name in agent.env_allow}
        return {k: v for k, v in os.environ.items() if k.upper() in wanted}

    def _cancelled(self, store: RunStore) -> bool:
        return self.cancel_event.is_set() or store.cancel_flag.exists()

    def _set(self, store: RunStore, run: dict[str, Any], target: State, kind: str, detail: str) -> None:
        check_transition(State(run["state"]), target)
        run["state"] = target.value
        if target in TERMINAL:
            run["reason"] = {"code": kind, "detail": detail}
        store.save_state(run)
        store.append_event("state", {"to": target.value, "code": kind, "detail": detail})

    def _finish_blocked(self, store: RunStore, run: dict[str, Any], code: str, detail: str) -> dict[str, Any]:
        if run["state"] not in {s.value for s in TERMINAL}:
            self._set(store, run, State.BLOCKED, code, detail)
        return run

    def _new_step(self, index: int, role: str, iteration: int, previous: dict[str, Any] | None) -> dict[str, Any]:
        return {"index": index, "role": role, "iteration": iteration, "previous": previous, "attempts": []}

    @staticmethod
    def _step(run: dict[str, Any]) -> dict[str, Any]:
        return run["steps"][run["current"]]

    def _agent(self, step: dict[str, Any]) -> AgentConfig:
        return self.config.agents[step["role"]]

    def _rel(self, path: Path) -> str:
        return str(path.relative_to(self.root)).replace("\\", "/")

    @staticmethod
    def _check_role(role: str) -> None:
        if role not in ROUTE:
            raise StoreError(f"papel inválido: {role}")
