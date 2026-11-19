"""Fast, isolated tests for the 02B local journal."""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "agent_handoff.py"


def valid_result(**override):
    value = {"protocol": "AGENT_RESULT", "role": "coordenador", "task_id": "T02B-001", "status": "planned", "verdict": None, "next_agent": "Orquestrador", "scope_changed": False, "blocking_issue": False, "changed_files": [], "evidence": [], "limitations": [], "commit_performed": False, "push_performed": False, "human_approval": "pending"}
    value.update(override)
    return value


class AgentHandoffTests(unittest.TestCase):
    def run_cli(self, *args, cwd=ROOT, input=None):
        return subprocess.run([sys.executable, str(SCRIPT), *args], cwd=cwd, input=input, text=True, capture_output=True, check=False)

    def test_validate_accepts_the_canonical_contract(self):
        with tempfile.TemporaryDirectory() as temp:
            result = Path(temp) / "result.json"
            result.write_text(json.dumps(valid_result()), encoding="utf-8")
            completed = self.run_cli("validate", str(result))
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(json.loads(completed.stdout), {"valid": True, "errors": []})

    def test_validate_rejects_non_boolean_and_unapproved_commit(self):
        with tempfile.TemporaryDirectory() as temp:
            result = Path(temp) / "result.json"
            result.write_text(json.dumps(valid_result(scope_changed=1, commit_performed=True)), encoding="utf-8")
            completed = self.run_cli("validate", str(result))
        self.assertEqual(completed.returncode, 1)
        codes = {item["code"] for item in json.loads(completed.stdout)["errors"]}
        self.assertEqual(codes, {"type", "const", "policy"})

    def test_record_redacts_secret_and_indexes_latest_result(self):
        with tempfile.TemporaryDirectory() as temp:
            worktree = Path(temp)
            result = worktree / "result.json"
            prompt = worktree / "prompt.md"
            resume = worktree / "resume.md"
            result.write_text(json.dumps(valid_result()), encoding="utf-8")
            prompt.write_text("token=do-not-store", encoding="utf-8")
            resume.write_text("plano curto", encoding="utf-8")
            completed = self.run_cli("--root", str(worktree), "record", "--role", "coordenador", "--task-id", "T02B-001", "--session-id", "s-1", "--result", str(result), "--prompt-log", str(prompt), "--resume", str(resume))
            self.assertEqual(completed.returncode, 0, completed.stderr)
            index = json.loads((worktree / ".chat-decisions" / "index.json").read_text(encoding="utf-8"))
            log = next((worktree / ".chat-decisions" / "coordenador").glob("prompt-log_*.md")).read_text(encoding="utf-8")
        self.assertEqual(index["tasks"]["T02B-001"]["next_agent"], "Orquestrador")
        self.assertIn("[REDACTED]", log)
        self.assertNotIn("do-not-store", log)

    def test_handoff_never_launches_a_provider_and_requires_contract_destination(self):
        with tempfile.TemporaryDirectory() as temp:
            worktree = Path(temp)
            result = worktree / "result.json"
            prompt = worktree / "prompt.md"
            resume = worktree / "resume.md"
            result.write_text(json.dumps(valid_result()), encoding="utf-8")
            prompt.write_text("entrada", encoding="utf-8")
            resume.write_text("resumo", encoding="utf-8")
            self.assertEqual(self.run_cli("--root", str(worktree), "record", "--role", "coordenador", "--task-id", "T02B-001", "--session-id", "s-1", "--result", str(result), "--prompt-log", str(prompt), "--resume", str(resume)).returncode, 0)
            completed = self.run_cli("--root", str(worktree), "handoff", "--task-id", "T02B-001", "--to", "Orquestrador")
        self.assertEqual(completed.returncode, 0, completed.stderr)
        package = json.loads(completed.stdout)
        self.assertEqual(package["authorization"], "human_confirmation_required")
        self.assertTrue(package["baseline_required"])


class Regression02CTests(unittest.TestCase):
    """M1-M7 from the 02C plan; all fixes are additive and 02B records stay readable."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)

    def cli(self, *args, input=None):
        return subprocess.run([sys.executable, str(SCRIPT), "--root", str(self.root), *args], input=input, text=True, capture_output=True, check=False)

    def record(self, session="s-1", result=None, prompt="log", resume="resumo curto"):
        files = {"result.json": json.dumps(result or valid_result(evidence=[{"criterion": "C1"}, {"criterion": "C2"}])), "prompt.md": prompt, "resume.md": resume}
        for name, text in files.items():
            (self.root / name).write_text(text, encoding="utf-8")
        return self.cli("record", "--role", "coordenador", "--task-id", "T02B-001", "--session-id", session, "--result", str(self.root / "result.json"), "--prompt-log", str(self.root / "prompt.md"), "--resume", str(self.root / "resume.md"))

    def test_m1_m2_handoff_carries_criteria_resume_log_and_baseline(self):
        self.assertEqual(self.record().returncode, 0)
        package = json.loads(self.cli("handoff", "--task-id", "T02B-001", "--to", "Orquestrador").stdout)
        self.assertEqual(package["criteria"], ["C1", "C2"])
        self.assertIn("resumo curto", package["resume"])
        self.assertTrue(package["prompt_log_path"].endswith(".md"))
        self.assertIn("available", package["baseline"])
        self.assertEqual(package["authorization"], "human_confirmation_required")

    def test_m3_second_record_in_same_session_keeps_the_first_resume(self):
        self.assertEqual(self.record(resume="primeiro").returncode, 0)
        self.assertEqual(self.record(resume="segundo").returncode, 0)
        resumes = sorted((self.root / ".chat-decisions" / "coordenador").glob("prompt-resume_*.md"))
        self.assertEqual(len(resumes), 2)
        self.assertEqual({"primeiro" in r.read_text(encoding="utf-8") for r in resumes}, {True, False})

    def test_m4_nan_is_rejected(self):
        path = self.root / "nan.json"
        path.write_text(json.dumps(valid_result()).replace("false", "NaN", 1), encoding="utf-8")
        done = self.cli("validate", str(path))
        self.assertEqual(done.returncode, 2)
        self.assertFalse(json.loads(done.stdout)["valid"])

    def test_m5_encodings(self):
        body = json.dumps(valid_result())
        path = self.root / "r.json"
        path.write_bytes(b"\xef\xbb\xbf" + body.encode("utf-8"))
        self.assertEqual(self.cli("validate", str(path)).returncode, 0)
        path.write_bytes(body.encode("utf-16"))
        self.assertEqual(self.cli("validate", str(path)).returncode, 0)
        path.write_bytes("{\"x\": \"\u00e7\"}".encode("latin-1"))
        done = self.cli("validate", str(path))
        self.assertEqual(done.returncode, 2)
        self.assertNotIn("Traceback", done.stderr)

    def test_m6_orphan_lock_is_recovered_but_live_lock_still_blocks(self):
        lock = self.root / ".chat-decisions" / ".locks" / "T02B-001.lock"
        lock.parent.mkdir(parents=True)
        lock.write_text("pid=%d started=x\n" % (2**22 + 4321), encoding="utf-8")
        self.assertEqual(self.record().returncode, 0)
        self.assertFalse(lock.exists())
        lock.write_text("pid=%d started=x\n" % os.getpid(), encoding="utf-8")
        blocked = self.record(session="s-2")
        self.assertEqual(blocked.returncode, 2)
        self.assertIn("bloqueada", blocked.stderr)

    def test_m7_no_python_311_only_apis_and_runs_on_older_python(self):
        self.assertNotIn("dt.UTC", SCRIPT.read_text(encoding="utf-8"))
        older = shutil.which("python")
        if not older:
            self.skipTest("sem interpretador 'python' no PATH")
        version = subprocess.run([older, "-c", "import sys; print(sys.version_info[:2] < (3, 11))"], capture_output=True, text=True).stdout.strip()
        if version != "True":
            self.skipTest("o 'python' do PATH não é anterior a 3.11")
        result = self.root / "r.json"
        result.write_text(json.dumps(valid_result()), encoding="utf-8")
        done = subprocess.run([older, str(SCRIPT), "--root", str(self.root), "record", "--role", "coordenador", "--task-id", "T02B-001", "--session-id", "old", "--result", str(result), "--prompt-log", str(result), "--resume", str(result)], capture_output=True, text=True)
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertFalse((self.root / ".chat-decisions" / ".locks" / "T02B-001.lock").exists())


if __name__ == "__main__":
    unittest.main()
