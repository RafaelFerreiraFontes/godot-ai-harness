"""Tests for the 02C supervisor.  Only fake CLIs are executed: no provider, no network.

Run with: py -3 -m unittest tests.test_agent_supervisor   (or pytest, which also works)
"""

import json
import os
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

import agent_handoff as handoff  # noqa: E402
from supervisor import config as cfg  # noqa: E402
from supervisor import contract, monitor  # noqa: E402
from supervisor.engine import Supervisor, redact  # noqa: E402
from supervisor.runner import ProcessRunner, ProcessSpec  # noqa: E402
from supervisor.states import ROUTE, InvalidTransition, State, check_transition, decide  # noqa: E402
from supervisor.store import RunStore, StoreError  # noqa: E402

FAKE = ROOT / "tests" / "fakes" / "fake_agent.py"
CLI = SCRIPTS / "agent_supervisor.py"
ALLOW_ALL = lambda request: True  # noqa: E731


def git(cwd, *argv):
    subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@example.invalid", *argv], cwd=cwd, check=True, capture_output=True)


def make_repo(path: Path) -> Path:
    git(path, "init", "-q")
    (path / ".gitignore").write_text(".chat-decisions/\n", encoding="utf-8")
    (path / "base.txt").write_text("base\n", encoding="utf-8")
    git(path, "add", ".")
    git(path, "commit", "-q", "-m", "base")
    return path


def agent(role, scenario="pass", extra=(), ownership=(), **kw):
    args = [str(FAKE), "--scenario", scenario, "--role", "{role}", "--task-id", "{task_id}", *extra]
    return {"provider": "fake", "executable": sys.executable, "model": "fake-model", "args": args, "timeout_seconds": 30, "ownership": list(ownership), **kw}


def raw_config(per_role=None, limits=None, code_write="out/a.txt"):
    agents = {r: agent(r) for r in ROUTE}
    agents["code"] = agent("code", extra=["--write", code_write] if code_write else [], ownership=["out/*"])
    for role, value in (per_role or {}).items():
        agents[role] = value
    return {"run": {"max_iterations": 2, "max_attempts": 2, **(limits or {})}, "agents": agents}


class Base(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = make_repo((Path(self._tmp.name) / "repo").resolve() if (Path(self._tmp.name) / "repo").mkdir() is None else None)
        self.aux = Path(self._tmp.name) / "aux"  # fake-agent counters/pids live outside the repo
        self.aux.mkdir()

    def sup(self, raw=None, **kw):
        config = cfg.parse_config(raw or raw_config(), test_mode=True)
        kw.setdefault("authorizer", ALLOW_ALL)
        return Supervisor(self.root, config, **kw)

    def run_all(self, raw=None, **kw):
        return self.sup(raw, **kw).start("T-1", "pedido de teste")

    def reason(self, run):
        return (run.get("reason") or {}).get("code")

    def journal_results(self, role):
        return sorted((self.root / ".chat-decisions" / role).glob("AGENT_RESULT_*.json"))


class StateMachineTests(unittest.TestCase):
    def test_terminal_states_have_no_exit_and_route_is_fixed(self):
        for terminal in (State.AWAITING_HUMAN, State.BLOCKED, State.FAILED, State.ABORTED, State.ITERATION_LIMIT_EXCEEDED):
            with self.assertRaises(InvalidTransition):
                check_transition(terminal, State.RUNNING)
        with self.assertRaises(InvalidTransition):
            check_transition(State.PENDING, State.RUNNING)  # authorization cannot be skipped
        self.assertEqual(ROUTE, ("coordenador", "orquestrador", "code", "reviewer", "qa", "gate"))

    def test_decisions(self):
        ok = {"status": "reviewed", "verdict": "pass", "next_agent": "QA", "blocking_issue": False}
        self.assertEqual(decide("reviewer", ok, 0, 2).role, "qa")
        fail = {"status": "changes_required", "verdict": "fail", "next_agent": "Code", "blocking_issue": False}
        self.assertEqual((decide("qa", fail, 0, 2).role, decide("qa", fail, 0, 2).iteration), ("code", 1))
        self.assertEqual(decide("qa", fail, 2, 2).kind, "limit")
        self.assertEqual(decide("gate", {**ok, "status": "evaluated", "next_agent": "HUMAN"}, 0, 2).kind, "human")
        self.assertEqual(decide("gate", {**ok, "status": "evaluated", "next_agent": "Code"}, 0, 2).kind, "blocked")
        self.assertEqual(decide("reviewer", {**ok, "verdict": "inconclusive"}, 0, 2).kind, "blocked")
        self.assertEqual(decide("code", {"status": "implemented", "verdict": None, "next_agent": "Reviewer", "blocking_issue": True}, 0, 2).kind, "blocked")


class ConfigTests(unittest.TestCase):
    def errors(self, raw, test_mode=False):
        with self.assertRaises(cfg.ConfigError) as caught:
            cfg.parse_config(raw, test_mode=test_mode)
        return " | ".join(caught.exception.errors)

    def real(self, **override):
        agent_cfg = {"provider": "claude", "executable": "claude", "model": "claude-sonnet-5-5", "args": ["-p", "--model", "{model}"], "ownership": ["out/*"]}
        agent_cfg.update(override)
        return {"agents": {"code": agent_cfg}}

    def test_valid_real_config_and_example_file(self):
        self.assertEqual(cfg.parse_config(self.real()).agents["code"].model, "claude-sonnet-5-5")
        loaded = cfg.load_config(ROOT / "docs" / "harness" / "supervisor.example.toml")
        self.assertEqual(set(loaded.agents), set(ROUTE))
        self.assertEqual(loaded.agents["qa"].provider, "antigravity")

    def test_provider_and_model_family_are_enforced_without_fallback(self):
        self.assertIn("provider deve ser", self.errors(self.real(provider="codex")))
        self.assertIn("família", self.errors(self.real(model="gpt-6.1-sol")))
        self.assertIn("fora da matriz", self.errors(self.real(model="claude-haiku-5-5")))
        self.assertIn("alternate_justification", self.errors(self.real(model="claude-opus-5-5")))
        self.assertTrue(cfg.parse_config(self.real(model="claude-opus-5-5", alternate_justification="complexidade real")))

    def test_fake_provider_only_in_test_mode(self):
        raw = {"agents": {"reviewer": agent("reviewer")}}
        self.assertIn("modo de teste", self.errors(raw))
        self.assertTrue(cfg.parse_config(raw, test_mode=True))

    def test_bypass_flags_shells_shims_and_secrets_are_refused(self):
        for bad in (["--dangerously-skip-permissions"], ["--permission-mode", "bypassPermissions"], ["--permission-mode=auto"], ["--mode", "auto"], ["-c", "approval_policy=never"], ["--yolo"]):
            self.assertIn("recusado", self.errors(self.real(args=bad)), bad)
        self.assertIn("recusado", self.errors({"agents": {"reviewer": {"provider": "codex", "executable": "codex", "model": "gpt-6.1-sol", "args": ["exec", "--dangerously-bypass-approvals-and-sandbox"]}}}))
        self.assertIn("shell", self.errors(self.real(executable="powershell")))
        self.assertIn("shims", self.errors(self.real(executable="claude.cmd")))
        self.assertIn("sensível", self.errors(self.real(env_allow=["PATH", "ANTHROPIC_API_KEY"])))
        self.assertIn("placeholder desconhecido", self.errors(self.real(args=["{secret}"])))

    def test_codex_requires_explicit_read_only_and_code_requires_ownership(self):
        codex = {"provider": "codex", "executable": "codex", "model": "gpt-6.1-sol", "args": ["exec", "-m", "{model}"]}
        self.assertIn("read-only", self.errors({"agents": {"reviewer": codex}}))
        self.assertTrue(cfg.parse_config({"agents": {"reviewer": {**codex, "args": ["exec", "-m", "{model}", "-s", "read-only"]}}}))
        self.assertIn("ownership", self.errors(self.real(ownership=[])))
        self.assertIn("ownership", self.errors(self.real(ownership=["../x"])))

    def test_executable_and_model_are_bound_to_provider_and_validated_model(self):
        codex = {"provider": "codex", "model": "gpt-6.1-sol", "executable": "codex", "args": ["exec", "-m", "{model}", "-s", "read-only"]}
        self.assertIn("não pertence ao provider", self.errors({"agents": {"reviewer": {**codex, "executable": "claude.exe"}}}))
        self.assertIn("difere do modelo validado", self.errors({"agents": {"reviewer": {**codex, "args": ["exec", "-m", "gpt-UNAPPROVED", "-s", "read-only"]}}}))
        self.assertIn("exatamente uma vez", self.errors({"agents": {"reviewer": {**codex, "args": ["exec", "-s", "read-only"]}}}))
        self.assertIn("exatamente uma vez", self.errors({"agents": {"reviewer": {**codex, "args": ["exec", "-m", "{model}", "--model", "gpt-x", "-s", "read-only"]}}}))
        self.assertIn("override", self.errors({"agents": {"reviewer": {**codex, "args": ["exec", "-m", "{model}", "-c", "model=gpt-x", "-s", "read-only"]}}}))
        self.assertIn("não pertence ao provider", self.errors(self.real(executable="codex")))
        self.assertTrue(cfg.parse_config(self.real(args=["-p", "--model=claude-sonnet-5-5"])))

    def test_only_code_and_qa_caches_may_have_write_ownership(self):
        codex = {"provider": "codex", "model": "gpt-6.1-sol", "executable": "codex", "args": ["exec", "-m", "{model}", "-s", "read-only"]}
        self.assertIn("somente leitura", self.errors({"agents": {"reviewer": {**codex, "ownership": ["**"]}}}))
        self.assertIn("curinga", self.errors(self.real(ownership=["**"])))
        qa = {"provider": "antigravity", "model": "gemini-3.8-flash-medium", "executable": "agy", "args": ["--model", "{model}"]}
        self.assertIn("cache", self.errors({"agents": {"qa": {**qa, "ownership": ["src/*"]}}}))
        self.assertTrue(cfg.parse_config({"agents": {"qa": {**qa, "ownership": ["**/__pycache__/*"]}}}))

    def test_limits_and_unknown_role(self):
        self.assertIn("max_attempts", self.errors({**self.real(), "run": {"max_attempts": 0}}))
        self.assertIn("papel desconhecido", self.errors({"agents": {"intruso": {}}}))
        self.assertIn("retry_on", self.errors({**self.real(), "run": {"retry_on": ["contract_invalid"]}}))


class DryRunTests(Base):
    def test_plan_starts_no_process_and_writes_nothing(self):
        class Boom:
            def run(self, *a, **k):
                raise AssertionError("dry-run não pode iniciar processo")

        report = self.sup(runner=Boom()).plan("T-1")
        self.assertFalse(report["process_started"])
        self.assertTrue(report["ready"])
        self.assertEqual([s["role"] for s in report["steps"]], list(ROUTE))
        self.assertFalse((self.root / ".chat-decisions").exists())

    def test_plan_reports_missing_cli_and_unconfigured_role(self):
        report = self.sup(which=lambda name: None).plan("T-1")
        self.assertFalse(report["ready"])
        self.assertIn("não encontrado", report["steps"][0]["problems"][0])
        partial = cfg.parse_config({"agents": {"gate": agent("gate")}}, test_mode=True)
        self.assertFalse(Supervisor(self.root, partial).plan("T-1")["ready"])


class FullRouteTests(Base):
    def test_fake_route_runs_in_order_and_stops_at_human(self):
        run = self.run_all()
        self.assertEqual(run["state"], "AWAITING_HUMAN", run.get("reason"))
        self.assertEqual([s["role"] for s in run["steps"]], list(ROUTE))
        for role in ROUTE:
            files = self.journal_results(role)
            self.assertEqual(len(files), 1, role)
            result = handoff.load_json(files[0])
            self.assertEqual(result["human_approval"], "pending")
            self.assertFalse(result["commit_performed"] or result["push_performed"])
            self.assertEqual(handoff.validate({k: v for k, v in result.items()}), [])
            self.assertTrue(list((self.root / ".chat-decisions" / role).glob("prompt-log_*.md")))
            self.assertTrue(list((self.root / ".chat-decisions" / role).glob("prompt-resume_*.md")))
        index = handoff.load_json(self.root / ".chat-decisions" / "index.json")
        self.assertEqual(index["tasks"]["T-1"]["role"], "gate")
        self.assertEqual(index["tasks"]["T-1"]["next_agent"], "HUMAN")
        store = RunStore(self.root, "T-1", run["run_id"])
        self.assertTrue(store.verify_events())
        self.assertEqual((self.root / "out" / "a.txt").read_text(encoding="utf-8").strip(), "written by fake code #1")

    def test_human_is_a_resting_state_not_an_authorization(self):
        run = self.run_all()
        self.assertEqual(run["reason"]["code"], "awaiting_human")
        with self.assertRaises(StoreError):
            self.sup().resume("T-1", run["run_id"])
        self.assertEqual(handoff.load_json(self.journal_results("gate")[0])["human_approval"], "pending")

    def test_journal_is_compatible_with_02b_handoff_and_validate(self):
        run = self.run_all()
        self.assertEqual(run["state"], "AWAITING_HUMAN")
        done = subprocess.run([sys.executable, str(SCRIPTS / "agent_handoff.py"), "--root", str(self.root), "handoff", "--task-id", "T-1", "--to", "HUMAN"], capture_output=True, text=True)
        self.assertEqual(done.returncode, 0, done.stderr)
        package = json.loads(done.stdout)
        self.assertEqual(package["criteria"], ["gate-criterio"])
        self.assertTrue(package["baseline"]["available"])
        self.assertIn("Supervisor run", package["resume"])
        checked = subprocess.run([sys.executable, str(SCRIPTS / "agent_handoff.py"), "validate", str(self.journal_results("code")[0])], capture_output=True, text=True)
        self.assertEqual(checked.returncode, 0, checked.stdout)


class ConfigurabilityTests(Base):
    def test_models_and_executables_come_from_config(self):
        raw = raw_config()
        raw["agents"]["reviewer"]["model"] = "modelo-x"
        run = self.run_all(raw)
        self.assertEqual(run["state"], "AWAITING_HUMAN")
        recorded = handoff.load_json(self.journal_results("reviewer")[0])
        self.assertEqual(recorded["metadata"]["supervisor"]["model_configured"], "modelo-x")
        self.assertFalse(recorded["metadata"]["supervisor"]["runtime_model_verified"])

    def test_missing_cli_blocks_without_fallback(self):
        called = []

        class Spy:
            def run(self, *a, **k):
                called.append(a)

        run = self.sup(which=lambda name: None, runner=Spy()).start("T-1", "x")
        self.assertEqual((run["state"], self.reason(run)), ("BLOCKED", "executable_missing"))
        self.assertEqual(called, [])

    def test_unconfigured_role_in_route_is_refused_before_any_write(self):
        partial = cfg.parse_config({"agents": {"coordenador": agent("coordenador")}}, test_mode=True)
        with self.assertRaises(StoreError):
            Supervisor(self.root, partial).start("T-1", "x")
        self.assertFalse((self.root / ".chat-decisions").exists())


class AuthorizationTests(Base):
    def test_default_authorizer_denies_and_run_rests_before_any_process(self):
        config = cfg.parse_config(raw_config(), test_mode=True)
        run = Supervisor(self.root, config).start("T-1", "x")
        self.assertEqual(run["state"], "AWAITING_AUTHORIZATION")
        self.assertEqual(run["steps"][0]["attempts"], [])

    def test_per_role_authorization_pauses_then_resume_continues_without_duplicates(self):
        raw = raw_config(per_role={"coordenador": agent("coordenador", extra=["--state-file", str(self.aux / "c.count")])})
        first = self.sup(raw, authorizer=lambda r: r.role == "coordenador").start("T-1", "x")
        self.assertEqual(first["state"], "AWAITING_AUTHORIZATION")
        self.assertEqual(first["steps"][-1]["role"], "orquestrador")
        done = self.sup(raw).resume("T-1", first["run_id"])
        self.assertEqual(done["state"], "AWAITING_HUMAN", done.get("reason"))
        self.assertEqual(len(self.journal_results("coordenador")), 1)
        self.assertEqual((self.aux / "c.count").read_text(), "1")


class FailureTests(Base):
    def one(self, scenario, role="coordenador", limits=None, extra=()):
        raw = raw_config(per_role={role: agent(role, scenario, extra=extra, timeout_seconds=1.5)}, limits=limits)
        return self.run_all(raw)

    def test_process_failure_is_retried_up_to_the_limit_then_fails(self):
        run = self.one("exit1")
        self.assertEqual((run["state"], self.reason(run)), ("FAILED", "process_failed"))
        self.assertEqual(len(run["steps"][0]["attempts"]), 2)
        self.assertEqual(self.journal_results("coordenador"), [])

    def test_transient_failure_recovers_via_bounded_retry(self):
        run = self.one("flaky", extra=["--state-file", str(self.aux / "f.count"), "--fail-times", "1"])
        self.assertEqual(run["state"], "AWAITING_HUMAN", run.get("reason"))
        self.assertEqual([a["classification"] for a in run["steps"][0]["attempts"]], ["process_failed", "ok"])

    def test_no_retry_when_not_classified_as_retryable(self):
        run = self.one("exit1", limits={"retry_on": []})
        self.assertEqual(len(run["steps"][0]["attempts"]), 1)
        self.assertEqual(run["state"], "FAILED")

    def test_timeout_kills_the_whole_process_tree(self):
        pids = self.aux / "pids.txt"
        run = self.one("hang", limits={"max_attempts": 1}, extra=["--pid-file", str(pids)])
        self.assertEqual((run["state"], self.reason(run)), ("FAILED", "timeout"))
        self.assertTrue(run["steps"][0]["attempts"][0]["duration_seconds"] < 10)
        parent, child = map(int, pids.read_text().split())
        for pid in (parent, child):
            self.assertTrue(self.wait_dead(pid), f"PID {pid} sobreviveu ao timeout")

    def test_cancellation_aborts_and_kills_the_tree(self):
        pids = self.aux / "pids.txt"
        cancel = threading.Event()
        raw = raw_config(per_role={"coordenador": agent("coordenador", "hang", extra=["--pid-file", str(pids)], timeout_seconds=60)})
        threading.Timer(1.5, cancel.set).start()
        run = self.run_all(raw, cancel_event=cancel)
        self.assertEqual(run["state"], "ABORTED", run.get("reason"))
        self.assertEqual(run["steps"][0]["attempts"][0]["classification"], "cancelled")
        for pid in map(int, pids.read_text().split()):
            self.assertTrue(self.wait_dead(pid))

    def test_failure_in_on_start_still_kills_the_started_tree(self):
        seen = []

        def failing_on_start(pid):
            seen.append(pid)
            raise OSError("não consegui persistir o PID")

        spec = ProcessSpec([sys.executable, "-c", "import time; time.sleep(600)"], str(self.root), dict(os.environ), None, 60, 4096)
        with self.assertRaises(OSError):
            ProcessRunner().run(spec, lambda: False, failing_on_start)
        self.assertTrue(self.wait_dead(seen[0]), "filho sobreviveu à falha de on_start")

    def test_failed_job_assignment_kills_the_unassigned_child_and_never_hangs(self):
        import io
        from unittest.mock import patch

        from supervisor import runner as rr

        class Proc:
            def __init__(self):
                self.pid, self.alive, self.returncode = 123, True, None
                self.stdin, self.stdout, self.stderr = io.BytesIO(), io.BytesIO(), io.BytesIO()
                self.killed = 0

            def poll(self):
                return None if self.alive else 1

            def kill(self):
                self.killed += 1
                self.alive, self.returncode = False, 1

            def wait(self, timeout=None):
                if self.alive:
                    raise AssertionError("esperou processo vivo sem limite")
                return 1

        class Job:
            def __init__(self, fail):
                self.fail, self.assigned, self.closed = fail, False, False

            def assign(self, proc):
                if self.fail:
                    raise rr.IsolationError("assign failed")
                self.assigned = True

            def terminate(self):
                pass  # an unassigned (or empty) job terminates nothing

            def close(self):
                self.closed = True

        spec = ProcessSpec(["FAKE"], ".", {}, None, 1, 1024)
        for fail, expected_error in ((True, rr.IsolationError), (False, OSError)):
            proc, job = Proc(), Job(fail)
            with patch.object(rr.subprocess, "Popen", return_value=proc), patch.object(rr, "_WindowsJob", return_value=job), patch.object(rr.os, "name", "nt"):
                with self.assertRaises(expected_error):
                    rr.ProcessRunner().run(spec, lambda: False, lambda pid: (_ for _ in ()).throw(OSError("persistência falhou")))
            self.assertFalse(proc.alive, f"fail={fail}: filho continuou vivo")
            self.assertTrue(job.closed)

    def cleanup_doubles(self):
        import io

        from supervisor import runner as rr

        class Proc:
            pid, returncode = 123, None

            def __init__(self, kill_error=None, wait_times_out=False):
                self.stdin, self.stdout, self.stderr = io.BytesIO(), io.BytesIO(), io.BytesIO()
                self.kill_error, self.wait_times_out = kill_error, wait_times_out

            def poll(self):
                return None

            def kill(self):
                if self.kill_error:
                    raise self.kill_error

            def wait(self, timeout=None):
                if self.wait_times_out:
                    raise rr.subprocess.TimeoutExpired("FAKE", timeout)
                return 0

        class Job:
            closed = False

            def __init__(self, fail_assign=True):
                self.fail_assign = fail_assign

            def assign(self, proc):
                if self.fail_assign:
                    raise rr.IsolationError("assign failed")

            def terminate(self):
                pass

            def close(self):
                self.closed = True

        return rr, Proc, Job

    def test_kill_oserror_still_closes_job_and_pipes_and_reports_the_pid(self):
        from unittest.mock import patch

        rr, Proc, Job = self.cleanup_doubles()
        proc, job = Proc(kill_error=OSError("kill failed")), Job()
        with patch.object(rr.subprocess, "Popen", return_value=proc), patch.object(rr, "_WindowsJob", return_value=job), patch.object(rr.os, "name", "nt"):
            with self.assertRaises(rr.ProcessCleanupError) as caught:
                rr.ProcessRunner().run(ProcessSpec(["FAKE"], ".", {}, None, 1, 1024))
        self.assertEqual(caught.exception.pid, 123)
        self.assertIn("kill falhou", caught.exception.problems[0])
        self.assertTrue(job.closed)
        self.assertTrue(all(stream.closed for stream in (proc.stdin, proc.stdout, proc.stderr)))
        self.assertIsInstance(caught.exception.__context__, rr.IsolationError)  # the original error is not lost

    def test_wait_timeout_after_assign_failure_is_reported_not_swallowed(self):
        from unittest.mock import patch

        rr, Proc, Job = self.cleanup_doubles()
        proc, job = Proc(wait_times_out=True), Job()
        with patch.object(rr.subprocess, "Popen", return_value=proc), patch.object(rr, "_WindowsJob", return_value=job), patch.object(rr.os, "name", "nt"):
            with self.assertRaises(rr.ProcessCleanupError) as caught:
                rr.ProcessRunner().run(ProcessSpec(["FAKE"], ".", {}, None, 1, 1024))
        self.assertIn("não encerrou", caught.exception.problems[0])
        self.assertTrue(job.closed)

    def test_engine_blocks_with_pid_when_the_process_cannot_be_killed(self):
        from supervisor.runner import ProcessCleanupError

        class Unkillable:
            calls = 0

            def run(inner, spec, cancel, on_start):
                inner.calls += 1
                raise ProcessCleanupError(4242, ["kill falhou: OSError"])

        runner = Unkillable()
        run = self.run_all(runner=runner)
        self.assertEqual((run["state"], self.reason(run)), ("BLOCKED", "process_unkillable"))
        attempt = run["steps"][0]["attempts"][0]
        self.assertEqual((attempt["pid"], attempt["classification"]), (4242, "process_unkillable"))
        self.assertEqual(runner.calls, 1)  # never retried
        self.assertIn("process_unkillable", run["reason"]["detail"])

    def test_spawn_failure_blocks(self):
        raw = raw_config(per_role={"coordenador": {**agent("coordenador"), "executable": str(self.root / "inexistente.exe")}})
        run = self.run_all(raw, which=lambda name: name)
        self.assertEqual((run["state"], self.reason(run)), ("BLOCKED", "spawn_failed"))

    @staticmethod
    def wait_dead(pid, seconds=5):
        end = time.time() + seconds
        while time.time() < end:
            if not handoff.pid_alive(pid):
                return True
            time.sleep(0.1)
        return False


class ContractTests(Base):
    def test_invalid_outputs_block_and_are_never_recorded(self):
        for scenario, needle in (("garbage", "contract_missing"), ("nan", "contract_missing"), ("two", "contract_ambiguous"), ("wrong_role", "role"), ("approve", "human_approval"), ("commit", "policy")):
            with self.subTest(scenario=scenario):
                self.tearDown_state()
                raw = raw_config(per_role={"coordenador": agent("coordenador", scenario)})
                run = self.run_all(raw)
                self.assertEqual((run["state"], self.reason(run)), ("BLOCKED", "contract_invalid"))
                self.assertIn(needle, run["reason"]["detail"])
                self.assertEqual(self.journal_results("coordenador"), [])

    def tearDown_state(self):
        import shutil

        shutil.rmtree(self.root / ".chat-decisions", ignore_errors=True)

    def test_exit_zero_alone_is_not_acceptance(self):
        run = self.run_all(raw_config(per_role={"coordenador": agent("coordenador", "garbage")}))
        self.assertEqual(run["steps"][0]["attempts"][0]["exit_code"], 0)
        self.assertEqual(run["state"], "BLOCKED")

    def evidence_result(self, ev, role="reviewer", status="reviewed", **extra):
        evidence = [{"criterion": "A5", "semantic_verdict": ev}, {"criterion": "A6", "semantic_verdict": "pass"}]
        return {"protocol": "AGENT_RESULT", "role": role, "task_id": "T", "status": status, "verdict": "pass", "next_agent": "QA", "scope_changed": False, "blocking_issue": False,
                "changed_files": [], "evidence": evidence, "limitations": [], "commit_performed": False, "push_performed": False, "human_approval": "pending", **extra}

    def test_a_passing_verdict_cannot_contradict_its_own_evidence(self):
        for verdict in ("fail", "inconclusive"):
            result, errors = contract.validate_contract("reviewer", "T", [self.evidence_result(verdict)])
            self.assertIsNone(result)
            self.assertIn("contradiz", errors[0])
        self.assertEqual(contract.validate_contract("reviewer", "T", [self.evidence_result("pass")])[1], [])
        self.assertIn("semantic_verdict", contract.validate_contract("reviewer", "T", [self.evidence_result("talvez")])[1][0])

    def test_code_may_report_inconclusive_but_not_failed_evidence(self):
        base = self.evidence_result("inconclusive", role="code", status="implemented", next_agent="Reviewer", verdict=None)
        self.assertEqual(contract.validate_contract("code", "T", [base])[1], [])
        failing = self.evidence_result("fail", role="code", status="implemented", next_agent="Reviewer", verdict=None)
        self.assertIn("contradiz", contract.validate_contract("code", "T", [failing])[1][0])

    def test_required_criteria_need_passing_evidence(self):
        ok = self.evidence_result("pass")
        self.assertEqual(contract.validate_contract("reviewer", "T", [ok], ("A5", "A6"))[1], [])
        errors = contract.validate_contract("reviewer", "T", [ok], ("A5", "A7"))[1]
        self.assertIn("A7", errors[0])

    def test_judge_with_failing_evidence_is_blocked_end_to_end(self):
        class Lying(ProcessRunner):
            def run(inner, spec, cancel, on_start):
                outcome = super().run(spec, cancel, on_start)
                if "reviewer" in spec.argv:
                    data = contract.extract_results(outcome.stdout.decode("utf-8", "replace"))[0]
                    data["evidence"][0]["semantic_verdict"] = "fail"
                    outcome.stdout = json.dumps(data).encode()
                return outcome

        run = self.run_all(runner=Lying())
        self.assertEqual((run["state"], self.reason(run)), ("BLOCKED", "contract_invalid"))
        self.assertEqual(self.journal_results("reviewer"), [])

    def test_extraction_is_strict(self):
        self.assertEqual(contract.extract_results('texto {"protocol": "AGENT_RESULT", "a": NaN}'), [])
        self.assertEqual(len(contract.extract_results('x {"protocol":"AGENT_RESULT"} y {"other":1}')), 1)
        self.assertIn("contract_missing", contract.validate_contract("code", "T", [])[1][0])


class OwnershipTests(Base):
    def test_guard_ignores_patterns_for_read_only_roles_and_non_cache_qa(self):
        from supervisor.workspace import ownership_violations

        self.assertTrue(ownership_violations("reviewer", ["src/x.py"], ("**",), False))
        self.assertTrue(ownership_violations("gate", ["src/x.py"], ("src/*",), False))
        self.assertTrue(ownership_violations("qa", ["src/x.py"], ("src/*",), False))
        self.assertEqual(ownership_violations("qa", ["a/__pycache__/x.pyc"], ("**/__pycache__/*",), False), [])
        self.assertEqual(ownership_violations("code", ["out/a.txt"], ("out/*",), False), [])

    def test_read_only_role_that_writes_is_blocked(self):
        run = self.run_all(raw_config(per_role={"reviewer": agent("reviewer", extra=["--write", "out/hack.txt", "--declare", "-"])}))
        self.assertEqual((run["state"], self.reason(run)), ("BLOCKED", "ownership_violation"))
        self.assertIn("reviewer alterou fora do ownership", run["reason"]["detail"])
        self.assertEqual(self.journal_results("reviewer"), [])

    def test_code_outside_ownership_is_blocked(self):
        run = self.run_all(raw_config(code_write="docs_x/b.txt"))
        self.assertEqual((run["state"], self.reason(run)), ("BLOCKED", "ownership_violation"))
        self.assertEqual(self.journal_results("code"), [])

    def test_code_declaration_must_match_git(self):
        raw = raw_config()
        raw["agents"]["code"]["args"] += ["--declare", "out/other.txt"]
        run = self.run_all(raw)
        self.assertEqual(self.reason(run), "ownership_violation")
        self.assertIn("não declaradas", run["reason"]["detail"])

    def test_preexisting_dirty_files_are_not_blamed_on_the_agent(self):
        (self.root / "base.txt").write_text("sujo antes\n", encoding="utf-8")
        run = self.run_all()
        self.assertEqual(run["state"], "AWAITING_HUMAN", run.get("reason"))

    def test_a_commit_by_an_agent_is_blocked(self):
        class Committing(ProcessRunner):
            def run(inner, spec, cancel, on_start):
                outcome = super().run(spec, cancel, on_start)
                if "--role" in spec.argv and spec.argv[spec.argv.index("--role") + 1] == "reviewer":
                    (self.root / "x.txt").write_text("x", encoding="utf-8")
                    git(self.root, "add", "x.txt")
                    git(self.root, "commit", "-q", "-m", "indevido")
                return outcome

        run = self.run_all(runner=Committing())
        self.assertEqual(self.reason(run), "ownership_violation")
        self.assertIn("HEAD mudou", run["reason"]["detail"])


class IterationTests(Base):
    def test_reviewer_failure_returns_to_code_once_then_passes(self):
        raw = raw_config(per_role={"reviewer": agent("reviewer", "judge_fail_once", extra=["--state-file", str(self.aux / "r.count")])})
        run = self.run_all(raw)
        self.assertEqual(run["state"], "AWAITING_HUMAN", run.get("reason"))
        self.assertEqual([(s["role"], s["iteration"]) for s in run["steps"]], [("coordenador", 0), ("orquestrador", 0), ("code", 0), ("reviewer", 0), ("code", 1), ("reviewer", 1), ("qa", 1), ("gate", 1)])
        self.assertEqual(len(self.journal_results("code")), 2)

    def test_always_failing_judge_hits_the_explicit_limit(self):
        raw = raw_config(per_role={"qa": agent("qa", "always_fail")}, limits={"max_iterations": 2})
        run = self.run_all(raw)
        self.assertEqual(run["state"], "ITERATION_LIMIT_EXCEEDED")
        self.assertEqual(max(s["iteration"] for s in run["steps"]), 2)
        self.assertEqual(len([s for s in run["steps"] if s["role"] == "qa"]), 3)

    def test_zero_iterations_means_no_return_to_code(self):
        raw = raw_config(per_role={"reviewer": agent("reviewer", "always_fail")}, limits={"max_iterations": 0})
        self.assertEqual(self.run_all(raw)["state"], "ITERATION_LIMIT_EXCEEDED")

    def test_inconclusive_verdict_blocks_instead_of_looping(self):
        run = self.run_all(raw_config(per_role={"gate": agent("gate", "inconclusive")}))
        self.assertEqual((run["state"], self.reason(run)), ("BLOCKED", "agent_blocked"))


class ResumeTests(Base):
    def paused(self):
        sup = self.sup(authorizer=lambda r: r.role == "coordenador")
        return sup.start("T-1", "x")

    def paused_first(self):
        """Run resting before the very first process (nothing authorized)."""
        return self.sup(authorizer=lambda r: False).start("T-1", "x")

    def test_head_or_tree_drift_blocks_resume(self):
        run = self.paused()
        (self.root / "intruso.txt").write_text("novo", encoding="utf-8")
        blocked = self.sup().resume("T-1", run["run_id"])
        self.assertEqual((blocked["state"], self.reason(blocked)), ("BLOCKED", "drift"))
        self.assertEqual(len(self.journal_results("orquestrador")), 0)

    def test_head_divergence_blocks_resume(self):
        run = self.paused()
        (self.root / "nova.txt").write_text("c", encoding="utf-8")
        git(self.root, "add", "nova.txt")
        git(self.root, "commit", "-q", "-m", "outro")
        self.assertEqual(self.reason(self.sup().resume("T-1", run["run_id"])), "drift")

    def test_crash_after_journal_write_is_adopted_not_duplicated(self):
        class Crash(BaseException):
            pass

        counter = self.aux / "c.count"
        raw = raw_config(per_role={"coordenador": agent("coordenador", extra=["--state-file", str(counter)])})
        first = self.sup(raw)
        real_record = first.journal.record

        def record_then_die(*a, **k):
            real_record(*a, **k)
            raise Crash()

        first.journal.record = record_then_die
        with self.assertRaises(Crash):
            first.start("T-1", "x")
        run_id = monitor.status(self.root)["runs"][0]["run_id"]
        self.assertEqual(monitor.status(self.root, "T-1", run_id)["state"], "VALIDATING")
        done = self.sup(raw).resume("T-1", run_id)
        self.assertEqual(done["state"], "AWAITING_HUMAN", done.get("reason"))
        self.assertEqual(len(self.journal_results("coordenador")), 1)
        self.assertEqual(counter.read_text(), "1")  # the process was not launched twice
        self.assertIn("record_adopted", [e["type"] for e in RunStore(self.root, "T-1", run_id).read_events()])

    def test_live_pid_from_interrupted_attempt_blocks_relaunch(self):
        run = self.paused_first()
        store = RunStore(self.root, "T-1", run["run_id"])
        state = store.load_state()
        state.update({"state": "RUNNING", "current": 0})
        state["steps"][0]["attempts"] = [{"n": 1, "pid": os.getpid(), "completed": False, "dir": "x"}]
        store.save_state(state)
        blocked = self.sup().resume("T-1", run["run_id"])
        self.assertEqual(self.reason(blocked), "process_possibly_alive")

    def test_dead_pid_attempt_counts_as_interrupted_and_relaunches_once(self):
        run = self.paused_first()
        store = RunStore(self.root, "T-1", run["run_id"])
        state = store.load_state()
        state.update({"state": "RUNNING", "current": 0})
        state["steps"][0]["attempts"] = [{"n": 1, "pid": 2**22 + 12345, "completed": False, "dir": "x"}]
        store.save_state(state)
        done = self.sup().resume("T-1", run["run_id"])
        self.assertEqual(done["state"], "AWAITING_HUMAN", done.get("reason"))
        self.assertEqual(done["steps"][0]["attempts"][0]["classification"], "interrupted")

    def interrupted_after_completion(self, classification, exit_code, max_attempts):
        raw = raw_config(limits={"max_attempts": max_attempts})
        first = self.sup(raw, authorizer=lambda r: False).start("T-1", "x")
        store = RunStore(self.root, "T-1", first["run_id"])
        state = store.load_state()
        state.update({"state": "RUNNING"})
        state["steps"][0]["attempts"] = [{"n": 1, "pid": 2**22 + 99, "completed": True, "classification": classification, "exit_code": exit_code, "dir": "x"}]
        store.save_state(state)

        class Boom:
            def run(self, *a, **k):
                raise AssertionError("não pode relançar após tentativa já concluída")

        return store, self.sup(raw, runner=Boom()).resume("T-1", first["run_id"])

    def test_completed_failed_attempt_at_the_limit_is_not_relaunched(self):
        _, done = self.interrupted_after_completion("process_failed", 3, 1)
        self.assertEqual((done["state"], self.reason(done)), ("FAILED", "process_failed"))

    def test_completed_ok_attempt_is_reconciled_to_validation_without_relaunch(self):
        store, done = self.interrupted_after_completion("ok", 0, 1)
        self.assertIn("resumed_reconciled", [e["type"] for e in store.read_events()])
        self.assertNotEqual(self.reason(done), "attempt_limit")

    def test_completed_retryable_failure_below_the_limit_may_relaunch(self):
        raw = raw_config(limits={"max_attempts": 2})
        first = self.sup(raw, authorizer=lambda r: False).start("T-1", "x")
        store = RunStore(self.root, "T-1", first["run_id"])
        state = store.load_state()
        state.update({"state": "RUNNING"})
        state["steps"][0]["attempts"] = [{"n": 1, "pid": 2**22 + 99, "completed": True, "classification": "process_failed", "exit_code": 3, "dir": "x"}]
        store.save_state(state)
        done = self.sup(raw).resume("T-1", first["run_id"])
        self.assertEqual(done["state"], "AWAITING_HUMAN", done.get("reason"))
        self.assertEqual(len(done["steps"][0]["attempts"]), 2)

    def test_config_change_or_tampered_events_refuse_resume(self):
        run = self.paused()
        other = raw_config(limits={"max_attempts": 3})
        with self.assertRaises(StoreError):
            self.sup(other).resume("T-1", run["run_id"])
        events = RunStore(self.root, "T-1", run["run_id"]).events_path
        events.write_text(events.read_text(encoding="utf-8").replace("run_created", "run_forged", 1), encoding="utf-8")
        with self.assertRaises(StoreError):
            self.sup().resume("T-1", run["run_id"])

    def test_concurrent_supervisor_on_same_task_is_refused(self):
        store = RunStore(self.root, "T-1", "other")
        lock = store.acquire()
        try:
            with self.assertRaises(StoreError):
                self.run_all()
        finally:
            store.release(lock)

    def test_orphan_task_lock_is_recovered(self):
        store = RunStore(self.root, "T-1", "other")
        lock = store.dir.parent / "active.lock"
        lock.parent.mkdir(parents=True)
        lock.write_text("pid=%d run=x\n" % (2**22 + 777), encoding="utf-8")
        self.assertEqual(self.run_all()["state"], "AWAITING_HUMAN")

    def test_abort_flag_stops_a_paused_run(self):
        run = self.paused()
        self.assertEqual(self.sup().abort("T-1", run["run_id"])["state"], "ABORTED")
        with self.assertRaises(StoreError):
            self.sup().resume("T-1", run["run_id"])


class PersistenceTests(Base):
    def test_artifact_tampered_after_record_is_not_declared_recorded(self):
        sup = self.sup()
        real = sup.journal.record

        def corrupt(*a, **k):
            files = real(*a, **k)
            path = self.root / files["resume"]
            path.write_text(path.read_text(encoding="utf-8") + "adulterado", encoding="utf-8")
            return files

        sup.journal.record = corrupt
        run = sup.start("T-1", "x")
        self.assertEqual((run["state"], self.reason(run)), ("BLOCKED", "persistence_uncertain"))

    def test_record_failure_blocks(self):
        sup = self.sup()

        def boom(*a, **k):
            raise RuntimeError("lock ocupado")

        sup.journal.record = boom
        self.assertEqual(self.reason(sup.start("T-1", "x")), "persistence_failed")


class RedactionTests(Base):
    def test_secrets_in_cli_output_are_masked_everywhere(self):
        run = self.run_all(raw_config(per_role={"coordenador": agent("coordenador", "secret")}))
        self.assertEqual(run["state"], "AWAITING_HUMAN", run.get("reason"))
        blob = "".join(p.read_text(encoding="utf-8", errors="replace") for p in (self.root / ".chat-decisions").rglob("*") if p.is_file())
        self.assertNotIn("SUPERSECRET123", blob)
        self.assertNotIn("abcdefghijklmnopqrstuvwxyz", blob)
        self.assertIn("[REDACTED]", blob)

    def test_redact_function(self):
        self.assertNotIn("sk-abcdefghijklmnopqrstu", redact("key sk-abcdefghijklmnopqrstu fim"))
        self.assertNotIn("hunter2", redact("password: hunter2"))

    def test_output_is_bounded(self):
        spec = ProcessSpec([sys.executable, "-c", "print('x'*50000)"], str(self.root), dict(os.environ), None, 20, 2048)
        outcome = ProcessRunner().run(spec, lambda: False, lambda pid: None)
        self.assertEqual(outcome.exit_code, 0)
        self.assertTrue(outcome.stdout_truncated)
        self.assertLessEqual(len(outcome.stdout), 2048)


class MonitorTests(Base):
    def test_status_is_read_only_and_explains_blocks(self):
        run = self.run_all(raw_config(per_role={"coordenador": agent("coordenador", "garbage")}))
        before = sorted(p.name for p in (self.root / ".chat-decisions").rglob("*"))
        summary = monitor.status(self.root, "T-1", run["run_id"])
        self.assertEqual(sorted(p.name for p in (self.root / ".chat-decisions").rglob("*")), before)
        self.assertEqual(summary["state"], "BLOCKED")
        self.assertTrue(summary["events_chain_ok"])
        self.assertIn("AGENT_RESULT", summary["hint"])
        self.assertEqual(monitor.status(self.root)["runs"][0]["reason"], "contract_invalid")


class CliTests(Base):
    def write_toml(self, raw, path):
        def value(v):
            return json.dumps(v) if not isinstance(v, (list, dict)) else (("[" + ", ".join(value(i) for i in v) + "]") if isinstance(v, list) else None)

        lines = ["[run]"] + [f"{k} = {value(v)}" for k, v in raw["run"].items()]
        for role, item in raw["agents"].items():
            lines += ["", f"[agents.{role}]"] + [f"{k} = {value(v)}" for k, v in item.items()]
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return path

    def cli(self, *args):
        return subprocess.run([sys.executable, str(CLI), "--root", str(self.root), *args], capture_output=True, text=True)

    def test_dry_run_and_execute_via_cli(self):
        conf = self.write_toml(raw_config(), self.root.parent / f"{self.root.name}.toml")
        self.addCleanup(conf.unlink)
        dry = self.cli("run", "--config", str(conf), "--test-mode", "--task-id", "T-9", "--dry-run")
        self.assertEqual(dry.returncode, 0, dry.stderr)
        self.assertFalse(json.loads(dry.stdout)["process_started"])
        self.assertFalse((self.root / ".chat-decisions").exists())
        paused = self.cli("run", "--config", str(conf), "--test-mode", "--task-id", "T-9", "--execute")
        self.assertEqual(paused.returncode, 0, paused.stderr)
        self.assertEqual(json.loads(paused.stdout)["state"], "AWAITING_AUTHORIZATION")
        full = self.cli("run", "--config", str(conf), "--test-mode", "--task-id", "T-10", "--execute", "--authorize", ",".join(ROUTE))
        self.assertEqual(full.returncode, 0, full.stderr)
        self.assertEqual(json.loads(full.stdout)["state"], "AWAITING_HUMAN")
        listing = self.cli("status", "--task-id", "T-10")
        self.assertEqual(json.loads(listing.stdout)["runs"][0]["state"], "AWAITING_HUMAN")

    def test_cli_rejects_bad_usage_and_unsafe_config(self):
        raw = raw_config()
        conf = self.write_toml(raw, self.root.parent / f"{self.root.name}-b.toml")
        self.addCleanup(conf.unlink)
        no_mode = self.cli("run", "--config", str(conf), "--test-mode", "--task-id", "T")
        self.assertEqual(no_mode.returncode, 2)
        without_test_mode = self.cli("plan", "--config", str(conf), "--task-id", "T")
        self.assertEqual(without_test_mode.returncode, 2)
        self.assertIn("provider", without_test_mode.stderr)
        raw["agents"]["code"]["args"].append("--dangerously-skip-permissions")
        bad = self.write_toml(raw, self.root.parent / f"{self.root.name}-c.toml")
        self.addCleanup(bad.unlink)
        self.assertEqual(self.cli("plan", "--config", str(bad), "--test-mode", "--task-id", "T").returncode, 2)
        self.assertEqual(self.cli("resume", "--config", str(conf), "--test-mode", "--task-id", "T", "--run-id", "x").returncode, 2)

    def test_blocked_run_exits_nonzero(self):
        raw = raw_config(per_role={"coordenador": agent("coordenador", "garbage")})
        conf = self.write_toml(raw, self.root.parent / f"{self.root.name}-d.toml")
        self.addCleanup(conf.unlink)
        done = self.cli("run", "--config", str(conf), "--test-mode", "--task-id", "T", "--execute", "--authorize", "coordenador")
        self.assertEqual(done.returncode, 1)
        self.assertEqual(json.loads(done.stdout)["state"], "BLOCKED")


if __name__ == "__main__":
    unittest.main()
