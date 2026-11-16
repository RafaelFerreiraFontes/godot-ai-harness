"""Validador experimental de AGENT_RESULT (apenas biblioteca padrão).

Contrato: docs/harness/agent-result.md. Decisões locais do experimento (não
alteram o contrato): campos extras são rejeitados (unknown_field),
human_approval aceita qualquer string não vazia e evidence é validada apenas
como lista de objetos.

Saída da CLI: {"valid": bool, "errors": [{"field","code","message"}]}.
Exit 0 = válido; 1 = violação do contrato; 2 = JSON malformado ou uso incorreto.
"""
from __future__ import annotations

import json
import sys

# Enumerações: fonte única em docs/harness/agent-result.md
ROLES = ("coordenador", "orquestrador", "code", "reviewer", "qa", "gate")
STATUSES = (
    "planned", "ready", "implemented", "reviewed", "tested", "evaluated",
    "changes_required", "blocked",
)
VERDICTS = ("pass", "fail", "inconclusive")  # além de null
NEXT_AGENTS = ("Coordenador", "Orquestrador", "Code", "Reviewer", "QA", "Gate", "HUMAN")
PROTOCOL = "AGENT_RESULT"

BOOL_FIELDS = ("scope_changed", "blocking_issue", "commit_performed", "push_performed")
LIST_FIELDS = ("changed_files", "evidence", "limitations")
REQUIRED_FIELDS = (
    "protocol", "role", "task_id", "status", "verdict", "next_agent",
    "scope_changed", "blocking_issue", "changed_files", "evidence",
    "limitations", "commit_performed", "push_performed", "human_approval",
)


def _err(field, code, message):
    return {"field": field, "code": code, "message": message}


def _check_enum(obj, field, allowed, errors):
    value = obj[field]
    if not isinstance(value, str):
        errors.append(_err(field, "invalid_type", f"{field} deve ser string"))
    elif value not in allowed:
        errors.append(_err(field, "invalid_value",
                           f"{field}={value!r} fora de {list(allowed)}"))


def validate(obj):
    """Retorna lista de erros (vazia se válido)."""
    if not isinstance(obj, dict):
        return [_err("$", "invalid_type", "a raiz deve ser um objeto JSON")]
    errors = []
    for field in REQUIRED_FIELDS:
        if field not in obj:
            errors.append(_err(field, "missing_field", f"campo obrigatório ausente: {field}"))
    for field in obj:
        if field not in REQUIRED_FIELDS:
            errors.append(_err(field, "unknown_field", f"campo não previsto: {field}"))

    if "protocol" in obj:
        if not isinstance(obj["protocol"], str):
            errors.append(_err("protocol", "invalid_type", "protocol deve ser string"))
        elif obj["protocol"] != PROTOCOL:
            errors.append(_err("protocol", "invalid_value", f"protocol deve ser {PROTOCOL!r}"))
    if "role" in obj:
        _check_enum(obj, "role", ROLES, errors)
    for field in ("task_id", "human_approval"):
        if field in obj and (not isinstance(obj[field], str) or not obj[field].strip()):
            errors.append(_err(field, "invalid_type", f"{field} deve ser string não vazia"))
    if "status" in obj:
        _check_enum(obj, "status", STATUSES, errors)
    if "verdict" in obj and obj["verdict"] is not None:
        _check_enum(obj, "verdict", VERDICTS, errors)
    if "next_agent" in obj:
        _check_enum(obj, "next_agent", NEXT_AGENTS, errors)
    for field in BOOL_FIELDS:
        if field in obj and not isinstance(obj[field], bool):  # estrito: sem "true"/0/1
            errors.append(_err(field, "invalid_type", f"{field} deve ser booleano"))
    for field in LIST_FIELDS:
        if field not in obj:
            continue
        value = obj[field]
        if not isinstance(value, list):
            errors.append(_err(field, "invalid_type", f"{field} deve ser lista"))
            continue
        want, label = (dict, "objeto") if field == "evidence" else (str, "string")
        for i, item in enumerate(value):
            if not isinstance(item, want):
                errors.append(_err(f"{field}[{i}]", "invalid_type", f"item deve ser {label}"))
    return errors


def _report(errors, code):
    json.dump({"valid": not errors, "errors": errors}, sys.stdout)
    sys.stdout.write("\n")
    return code


def _reject_constant(name):
    # NaN/Infinity/-Infinity não fazem parte do JSON (RFC 8259)
    raise ValueError(f"constante não-JSON: {name}")


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if len(argv) != 1:
        return _report([_err("$", "usage", "uso: validate_agent_result.py <arquivo|->")], 2)
    try:
        if argv[0] == "-":
            raw = sys.stdin.buffer.read()
        else:
            with open(argv[0], "rb") as fh:
                raw = fh.read()
        obj = json.loads(raw.decode("utf-8-sig"), parse_constant=_reject_constant)
    except (OSError, UnicodeDecodeError) as exc:
        return _report([_err("$", "read_error", f"falha ao ler entrada: {exc}")], 2)
    except json.JSONDecodeError as exc:
        return _report([_err("$", "malformed_json", f"JSON malformado: {exc}")], 2)
    except (ValueError, RecursionError) as exc:  # inteiro gigante, NaN/Infinity, aninhamento
        return _report([_err("$", "malformed_json", f"JSON inválido: {exc}")], 2)
    errors = validate(obj)
    return _report(errors, 1 if errors else 0)


if __name__ == "__main__":
    sys.exit(main())
