"""Fast, isolated tests for the 02B local journal."""

import json
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


if __name__ == "__main__":
    unittest.main()
