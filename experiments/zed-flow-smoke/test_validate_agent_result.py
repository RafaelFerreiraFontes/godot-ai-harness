import copy
import json
import os
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import validate_agent_result as v  # noqa: E402

SCRIPT = os.path.join(HERE, "validate_agent_result.py")
FIX = os.path.join(HERE, "fixtures")


def load(name):
    with open(os.path.join(FIX, name), encoding="utf-8") as fh:
        return json.load(fh)


def codes(errors):
    return {(e["field"], e["code"]) for e in errors}


def run_cli(arg, stdin=None):
    p = subprocess.run([sys.executable, "-I", "-B", SCRIPT, arg], input=stdin,
                       capture_output=True, cwd=HERE)
    return p.returncode, json.loads(p.stdout.decode("utf-8")), p.stderr.decode("utf-8")


class ValidateTests(unittest.TestCase):
    def test_valid_template(self):
        self.assertEqual(v.validate(load("valid.json")), [])

    def test_missing_task_id(self):
        errs = v.validate(load("missing_task_id.json"))
        self.assertEqual(codes(errs), {("task_id", "missing_field")})

    def test_invalid_verdict(self):
        errs = v.validate(load("invalid_verdict.json"))
        self.assertEqual(codes(errs), {("verdict", "invalid_value")})

    def test_valid_verdicts_and_statuses(self):
        for verdict in (None, "pass", "fail", "inconclusive"):
            o = load("valid.json"); o["verdict"] = verdict
            self.assertEqual(v.validate(o), [])
        for status in ("planned", "ready", "implemented", "reviewed", "tested",
                       "evaluated", "changes_required", "blocked"):
            o = load("valid.json"); o["status"] = status
            self.assertEqual(v.validate(o), [])

    def test_root_not_object(self):
        for root in ([], "x", 1, None):
            self.assertEqual(codes(v.validate(root)), {("$", "invalid_type")})

    def test_boolean_as_string_or_int(self):
        for bad in ("false", 0, 1, None):
            o = load("valid.json"); o["scope_changed"] = bad
            self.assertEqual(codes(v.validate(o)), {("scope_changed", "invalid_type")})

    def test_wrong_protocol(self):
        o = load("valid.json"); o["protocol"] = "OTHER"
        self.assertEqual(codes(v.validate(o)), {("protocol", "invalid_value")})

    def test_invalid_role_and_next_agent(self):
        o = load("valid.json"); o["role"] = "Code"; o["next_agent"] = "qa"
        self.assertEqual(codes(v.validate(o)),
                         {("role", "invalid_value"), ("next_agent", "invalid_value")})

    def test_unknown_field(self):
        o = load("valid.json"); o["extra"] = 1
        self.assertEqual(codes(v.validate(o)), {("extra", "unknown_field")})

    def test_list_types(self):
        o = load("valid.json")
        o["changed_files"] = "a.py"; o["evidence"] = ["x"]; o["limitations"] = [1]
        self.assertEqual(codes(v.validate(o)), {
            ("changed_files", "invalid_type"), ("evidence[0]", "invalid_type"),
            ("limitations[0]", "invalid_type")})

    def test_human_approval_empty_rejected_any_string_accepted(self):
        o = load("valid.json"); o["human_approval"] = ""
        self.assertEqual(codes(v.validate(o)), {("human_approval", "invalid_type")})
        o["human_approval"] = "aprovado por X"
        self.assertEqual(v.validate(o), [])

    def test_all_fields_missing(self):
        self.assertEqual(len(v.validate({})), 14)

    def test_does_not_mutate_input(self):
        o = load("valid.json"); snap = copy.deepcopy(o); v.validate(o)
        self.assertEqual(o, snap)


class CliTests(unittest.TestCase):
    def test_fixtures_exit_codes(self):
        cases = {"valid.json": 0, "missing_task_id.json": 1,
                 "invalid_verdict.json": 1, "truncated.json": 2}
        for name, code in cases.items():
            rc, out, err = run_cli(os.path.join(FIX, name))
            self.assertEqual(rc, code, name)
            self.assertEqual(out["valid"], code == 0)
            self.assertNotIn("Traceback", err)
        _, out, _ = run_cli(os.path.join(FIX, "truncated.json"))
        self.assertEqual(out["errors"][0]["code"], "malformed_json")

    def test_stdin_equals_file(self):
        for name in ("valid.json", "missing_task_id.json", "invalid_verdict.json"):
            path = os.path.join(FIX, name)
            with open(path, "rb") as fh:
                data = fh.read()
            self.assertEqual(run_cli(path), run_cli("-", stdin=data))

    def test_stdin_malformed(self):
        rc, out, err = run_cli("-", stdin=b"{")
        self.assertEqual((rc, out["errors"][0]["code"], err), (2, "malformed_json", ""))

    def test_list_root_and_extra_field_via_cli(self):
        with tempfile.TemporaryDirectory() as t:
            p = os.path.join(t, "r.json")
            with open(p, "w", encoding="utf-8") as fh:
                fh.write("[]")
            rc, out, _ = run_cli(p)
            self.assertEqual((rc, out["valid"]), (1, False))
            o = load("valid.json"); o["extra"] = True
            with open(p, "w", encoding="utf-8") as fh:
                json.dump(o, fh)
            rc, out, _ = run_cli(p)
            self.assertEqual((rc, out["errors"][0]["code"]), (1, "unknown_field"))

    def test_non_json_constants_and_limits_are_structured(self):
        base = json.dumps(load("valid.json"))
        cases = {
            "nan": base[:-1] + ', "x": NaN}',
            "inf": base[:-1] + ', "x": -Infinity}',
            "bigint": base[:-1] + ', "x": ' + "9" * 5000 + "}",
            "deep": "[" * 100000,
        }
        for name, text in cases.items():
            rc, out, err = run_cli("-", stdin=text.encode())
            self.assertEqual((rc, out["errors"][0]["code"], err), (2, "malformed_json", ""), name)

    def test_usage_and_missing_file(self):
        p = subprocess.run([sys.executable, "-I", "-B", SCRIPT], capture_output=True)
        self.assertEqual(p.returncode, 2)
        rc, out, _ = run_cli(os.path.join(FIX, "nao_existe.json"))
        self.assertEqual((rc, out["errors"][0]["code"]), (2, "read_error"))


if __name__ == "__main__":
    unittest.main()
