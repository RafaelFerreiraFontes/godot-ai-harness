"""Provider adapters (argv/stdout shaping) and strict AGENT_RESULT extraction/validation."""

from __future__ import annotations

import json
import re
from typing import Any

import agent_handoff as handoff

from .config import AgentConfig
from .states import JUDGES, OK_STATUS

MAX_ARG_PROMPT = 24_000  # conservative Windows command-line budget for prompt_via=arg


class AdapterError(RuntimeError):
    pass


class ProviderAdapter:
    """Generic adapter: placeholder substitution, no provider-specific flags assumed.

    Flags live in the config (verified per CLI version by a human), never in this code.
    """

    name = "generic"

    def build_argv(self, agent: AgentConfig, executable: str, *, task_id: str, cwd: str, prompt: str, prompt_file: str) -> list[str]:
        values = {"model": agent.model, "role": agent.role, "task_id": task_id, "cwd": cwd, "prompt": prompt, "prompt_file": prompt_file}
        if agent.prompt_via == "arg" and len(prompt) > MAX_ARG_PROMPT:
            raise AdapterError("prompt excede o limite seguro de linha de comando; use prompt_via=stdin")
        argv = [executable]
        for arg in agent.args:
            argv.append(re.sub(r"\{([a-z_]+)\}", lambda m: values[m.group(1)], arg))
        return argv

    def extract_text(self, stdout: str) -> str:
        return stdout


class ClaudeAdapter(ProviderAdapter):
    name = "claude"

    def extract_text(self, stdout: str) -> str:
        """`--output-format json` wraps the final message in a `result` field; plain text passes through."""
        try:
            data = handoff.parse_json_strict(stdout)
        except ValueError:
            return stdout
        if isinstance(data, dict) and isinstance(data.get("result"), str):
            return data["result"]
        return stdout


def adapter_for(provider: str) -> ProviderAdapter:
    return ClaudeAdapter() if provider == "claude" else ProviderAdapter()


def _reject(name: str) -> Any:
    raise ValueError(f"constante não finita: {name}")


def extract_results(text: str) -> list[dict[str, Any]]:
    """Every top-level JSON object in the text that declares protocol AGENT_RESULT."""
    decoder = json.JSONDecoder(parse_constant=_reject)
    found, index = [], 0
    while True:
        index = text.find("{", index)
        if index < 0:
            return found
        try:
            value, end = decoder.raw_decode(text, index)
        except ValueError:
            index += 1
            continue
        if isinstance(value, dict) and value.get("protocol") == "AGENT_RESULT":
            found.append(value)
        index = end


def validate_contract(role: str, task_id: str, results: list[dict[str, Any]], required_criteria: tuple[str, ...] = ()) -> tuple[dict[str, Any] | None, list[str]]:
    """Exactly one result, canonical schema/semantics, right role/task, no self-approval."""
    if not results:
        return None, ["contract_missing: nenhum AGENT_RESULT encontrado na saída"]
    if len(results) > 1:
        return None, [f"contract_ambiguous: {len(results)} objetos AGENT_RESULT na saída; exige exatamente um"]
    result = results[0]
    errors = [f"schema:{e['field']}:{e['code']}" for e in handoff.validate(result)]
    if errors:
        return None, errors
    if result["role"] != role:
        errors.append(f"role: esperado {role!r}, recebido {result['role']!r}")
    if result["task_id"] != task_id:
        errors.append(f"task_id: esperado {task_id!r}, recebido {result['task_id']!r}")
    if result["human_approval"] != "pending":
        errors.append("human_approval: somente decisão humana pode alterar 'pending'; resultado de agente não autoriza")
    if result["status"] not in (*OK_STATUS[role], "blocked", "changes_required"):
        errors.append(f"status: {result['status']!r} inválido para {role}")
    needs_evidence = result["status"] == "implemented" or (role in JUDGES and result.get("verdict") == "pass")
    if needs_evidence:
        evidence = result["evidence"]
        if not evidence or not all(isinstance(e, dict) and isinstance(e.get("criterion"), str) and e["criterion"].strip() for e in evidence):
            errors.append("evidence: avanço exige evidências objeto com 'criterion' (exit 0 isolado não prova)")
        else:
            verdicts = [e.get("semantic_verdict") for e in evidence]
            if any(v is not None and v not in ("pass", "fail", "inconclusive") for v in verdicts):
                errors.append("evidence: semantic_verdict deve ser pass, fail ou inconclusive")
            # A judge cannot pass while its own evidence fails or is inconclusive; Code may report
            # inconclusive items honestly but never a failing one.
            blocked_values = ("fail", "inconclusive") if role in JUDGES else ("fail",)
            bad = [e["criterion"] for e in evidence if e.get("semantic_verdict") in blocked_values]
            if bad:
                errors.append(f"evidence: avanço contradiz evidências {blocked_values}: {bad}")
            passed = {e["criterion"].strip() for e in evidence if e.get("semantic_verdict") == "pass"}
            missing = [c for c in required_criteria if not any(p == c or p.startswith(c + " ") or p.startswith(c + ":") for p in passed)]
            if missing:
                errors.append(f"evidence: critérios exigidos sem evidência pass: {missing}")
    if role != "code" and result["changed_files"] and result["status"] != "blocked":
        errors.append("changed_files: somente Code pode declarar arquivos alterados")
    return (None, errors) if errors else (result, [])
