"""Supervisor configuration: per-role provider, CLI, model, limits and safety policy.

Everything that varies (executable, argv, model, timeouts) comes from TOML or a dict.
The only hardcoded data is the *policy* from docs/harness/model-policy.md, used to
reject a role routed to the wrong provider or model family; there is no fallback.
"""

from __future__ import annotations

import hashlib
import json
import re
import shutil
from dataclasses import dataclass, field
from pathlib import Path, PurePath
from typing import Any, Callable

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - the supervisor needs Python >= 3.11
    tomllib = None  # type: ignore[assignment]

ROLES = ("coordenador", "orquestrador", "code", "reviewer", "qa", "gate")
ROLE_PROVIDER = {"coordenador": "claude", "code": "claude", "orquestrador": "codex", "reviewer": "codex", "qa": "antigravity", "gate": "antigravity"}
PROVIDER_FAMILY = {"claude": "claude-", "codex": "gpt-", "antigravity": "gemini-"}
# (principal, manual alternates). An alternate needs an explicit justification in the config.
ROLE_MODELS = {
    "coordenador": ("claude-opus-5-5", ("claude-sonnet-5-5",)),
    "code": ("claude-sonnet-5-5", ("claude-opus-5-5",)),
    "orquestrador": ("gpt-6.1-terra", ("gpt-6.1-sol",)),
    "reviewer": ("gpt-6.1-sol", ("gpt-6-astra",)),
    "qa": ("gemini-3.8-flash", ("gemini-4-hydrogen",)),
    "gate": ("gemini-4-hydrogen", ("gemini-4-carbon",)),
}
PLACEHOLDERS = {"model", "role", "task_id", "cwd", "prompt", "prompt_file"}
PLACEHOLDER_RE = re.compile(r"\{([A-Za-z_]+)\}")
BYPASS_RE = re.compile(r"(?i)(dangerous|bypass|skip[-_]?permissions|danger-full-access|yolo|auto[-_]?approve|full-auto|approval_policy\W*never|sandbox_mode\W*danger)")
BYPASS_VALUES = {"bypasspermissions", "auto", "dontask"}
PROVIDER_EXE = {"claude": {"claude"}, "codex": {"codex"}, "antigravity": {"agy"}}
MODEL_FLAGS = {"claude": {"--model"}, "codex": {"-m", "--model"}, "antigravity": {"--model"}}
# Only Code writes project files; QA may only declare cache globs; every other role is read-only.
CACHE_TOKENS = ("__pycache__", ".pytest_cache", ".ruff_cache", ".mypy_cache", ".cache")
SHELLS = {"cmd", "powershell", "pwsh", "bash", "sh", "zsh", "wsl", "cscript", "wscript"}
SECRET_ENV = re.compile(r"(?i)(key|token|secret|password|credential|auth)")
DEFAULT_ENV = ("PATH", "PATHEXT", "SYSTEMROOT", "SYSTEMDRIVE", "WINDIR", "COMSPEC", "USERPROFILE", "HOME", "APPDATA", "LOCALAPPDATA", "PROGRAMDATA", "TEMP", "TMP", "USERNAME", "HOMEDRIVE", "HOMEPATH", "LANG")


class ConfigError(ValueError):
    def __init__(self, errors: list[str]) -> None:
        super().__init__("; ".join(errors))
        self.errors = errors


@dataclass(frozen=True)
class AgentConfig:
    role: str
    provider: str
    executable: str
    model: str
    args: tuple[str, ...]
    prompt_via: str = "stdin"
    timeout_seconds: float = 1800.0
    max_output_bytes: int = 2_000_000
    env_allow: tuple[str, ...] = DEFAULT_ENV
    alternate_justification: str = ""
    ownership: tuple[str, ...] = ()
    required_criteria: tuple[str, ...] = ()


@dataclass(frozen=True)
class Limits:
    max_iterations: int = 2
    max_attempts: int = 2
    retry_on: tuple[str, ...] = ("timeout", "process_failed")


@dataclass(frozen=True)
class SupervisorConfig:
    agents: dict[str, AgentConfig]
    limits: Limits = field(default_factory=Limits)
    test_mode: bool = False
    digest: str = ""


def _is_alternate(role: str, model: str) -> bool:
    principal, alternates = ROLE_MODELS[role]
    return not _matches(model, principal) and any(_matches(model, alt) for alt in alternates)


def _matches(model: str, base: str) -> bool:
    return model == base or model.startswith(base + "-")  # agy IDs carry an effort suffix


def _agent_errors(role: str, raw: dict[str, Any], test_mode: bool) -> list[str]:
    errs: list[str] = []
    tag = f"agents.{role}"
    provider, model = raw.get("provider"), raw.get("model")
    fake = test_mode and provider == "fake"
    if not fake and provider != ROLE_PROVIDER[role]:
        errs.append(f"{tag}: provider deve ser {ROLE_PROVIDER[role]!r} (política de modelos), recebeu {provider!r}")
    if provider == "fake" and not test_mode:
        errs.append(f"{tag}: provider 'fake' só é aceito em modo de teste")
    if not isinstance(model, str) or not model.strip():
        errs.append(f"{tag}: model ausente")
    elif not fake:
        family = PROVIDER_FAMILY.get(str(provider), "")
        if family and not model.startswith(family):
            errs.append(f"{tag}: modelo {model!r} não pertence à família do provider {provider} ({family}*)")
        principal, alternates = ROLE_MODELS[role]
        if not any(_matches(model, base) for base in (principal, *alternates)):
            errs.append(f"{tag}: modelo {model!r} fora da matriz do papel (principal {principal})")
        elif _is_alternate(role, model) and not str(raw.get("alternate_justification", "")).strip():
            errs.append(f"{tag}: modelo alternativo exige alternate_justification explícita")
    executable = raw.get("executable")
    if not isinstance(executable, str) or not executable.strip():
        errs.append(f"{tag}: executable ausente")
    else:
        stem = PurePath(executable).stem.lower()
        if stem in SHELLS or re.search(r"[&|;<>`$\"\n]", executable):
            errs.append(f"{tag}: executable não pode ser shell nem conter metacaracteres")
        if executable.lower().endswith((".cmd", ".bat")):
            errs.append(f"{tag}: shims .cmd/.bat não são aceitos (exigiriam shell)")
    args = raw.get("args", [])
    if not isinstance(args, list) or not all(isinstance(a, str) for a in args):
        return errs + [f"{tag}: args deve ser lista de strings"]
    if raw.get("prompt_via", "stdin") not in ("stdin", "arg"):
        errs.append(f"{tag}: prompt_via deve ser stdin ou arg")
    joined = " ".join(args)
    if raw.get("prompt_via", "stdin") == "arg" and "{prompt}" not in joined:
        errs.append(f"{tag}: prompt_via=arg exige o placeholder {{prompt}} em args")
    if raw.get("prompt_via", "stdin") == "stdin" and "{prompt}" in joined:
        errs.append(f"{tag}: {{prompt}} só vale com prompt_via=arg")
    for index, arg in enumerate(args):
        if BYPASS_RE.search(arg):
            errs.append(f"{tag}: argumento de bypass/perigoso recusado: {arg!r}")
        for name in PLACEHOLDER_RE.findall(arg):
            if name not in PLACEHOLDERS:
                errs.append(f"{tag}: placeholder desconhecido {{{name}}}")
        if arg in ("--permission-mode", "--mode") and index + 1 < len(args) and args[index + 1].lower() in BYPASS_VALUES:
            errs.append(f"{tag}: modo de permissão que dispensa aprovação recusado: {args[index + 1]!r}")
        if arg.lower().startswith(("--permission-mode=", "--mode=")) and arg.split("=", 1)[1].lower() in BYPASS_VALUES:
            errs.append(f"{tag}: modo de permissão que dispensa aprovação recusado: {arg!r}")
    if provider == "codex" and not _codex_read_only(args):
        errs.append(f"{tag}: Codex só roda com sandbox read-only explícito (-s read-only)")
    if not fake and provider in PROVIDER_EXE and isinstance(executable, str) and executable.strip():
        stem = PurePath(executable).stem.lower()
        if stem not in PROVIDER_EXE[provider]:
            errs.append(f"{tag}: executable {executable!r} não pertence ao provider {provider} (esperado {sorted(PROVIDER_EXE[provider])})")
        errs.extend(_model_binding_errors(tag, provider, str(model), args))
    timeout = raw.get("timeout_seconds", 1800)
    if isinstance(timeout, bool) or not isinstance(timeout, (int, float)) or not 0 < timeout <= 86400:
        errs.append(f"{tag}: timeout_seconds deve estar em (0, 86400]")
    limit = raw.get("max_output_bytes", 2_000_000)
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1024 <= limit <= 50_000_000:
        errs.append(f"{tag}: max_output_bytes deve estar em [1024, 50000000]")
    env = raw.get("env_allow", list(DEFAULT_ENV))
    if not isinstance(env, list) or not all(isinstance(e, str) and e for e in env):
        errs.append(f"{tag}: env_allow deve ser lista de nomes")
    else:
        for name in env:
            if SECRET_ENV.search(name):
                errs.append(f"{tag}: variável sensível {name!r} não pode ser repassada")
    own = raw.get("ownership", [])
    if not isinstance(own, list) or not all(isinstance(o, str) and o and not o.startswith(("/", "..")) and ".." not in o.split("/") for o in own):
        errs.append(f"{tag}: ownership deve ser lista de globs relativos sem '..'")
    elif role == "code" and not own:
        errs.append(f"{tag}: Code exige ownership explícito (globs dos arquivos exclusivos)")
    elif role == "code" and any(not o.strip("*/") for o in own):
        errs.append(f"{tag}: ownership de Code não pode ser um curinga irrestrito")
    elif role == "qa" and not all(any(token in o for token in CACHE_TOKENS) for o in own):
        errs.append(f"{tag}: QA só pode declarar globs de cache ({', '.join(CACHE_TOKENS)})")
    elif role not in ("code", "qa") and own:
        errs.append(f"{tag}: papel somente leitura não pode ter ownership de escrita")
    criteria = raw.get("required_criteria", [])
    if not isinstance(criteria, list) or not all(isinstance(c, str) and c.strip() for c in criteria):
        errs.append(f"{tag}: required_criteria deve ser lista de strings")
    return errs


def _model_binding_errors(tag: str, provider: str, model: str, args: list[str]) -> list[str]:
    """The model the CLI really receives must be the validated one: one flag, `{model}` or the same literal."""
    flags = MODEL_FLAGS[provider]
    values: list[str] = []
    errs: list[str] = []
    for index, arg in enumerate(args):
        if arg in flags:
            if index + 1 >= len(args):
                errs.append(f"{tag}: {arg} sem valor")
            else:
                values.append(args[index + 1])
        elif any(arg.startswith(flag + "=") for flag in flags if flag.startswith("--")):
            values.append(arg.split("=", 1)[1])
        elif re.search(r"(?i)\bmodel\s*=", arg):
            errs.append(f"{tag}: seleção de modelo por override ({arg!r}) é recusada; use {sorted(flags)[0]} {{model}}")
    if len(values) != 1:
        errs.append(f"{tag}: args deve selecionar o modelo exatamente uma vez ({'/'.join(sorted(flags))} {{model}}); encontradas {len(values)}")
    elif values[0] not in ("{model}", model):
        errs.append(f"{tag}: modelo nos args ({values[0]!r}) difere do modelo validado ({model!r})")
    return errs


def _codex_read_only(args: list[str]) -> bool:
    for index, arg in enumerate(args):
        if arg in ("-s", "--sandbox") and index + 1 < len(args) and args[index + 1] == "read-only":
            return True
        if arg in ("--sandbox=read-only", "-s=read-only"):
            return True
    return False


def parse_config(raw: dict[str, Any], *, test_mode: bool = False) -> SupervisorConfig:
    errs: list[str] = []
    run = raw.get("run", {})
    if not isinstance(run, dict):
        raise ConfigError(["[run] deve ser tabela"])
    limits = Limits(
        max_iterations=run.get("max_iterations", 2),
        max_attempts=run.get("max_attempts", 2),
        retry_on=tuple(run.get("retry_on", ("timeout", "process_failed"))),
    )
    for name in ("max_iterations", "max_attempts"):
        value = getattr(limits, name)
        if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= 10 or (name == "max_attempts" and value < 1):
            errs.append(f"run.{name} fora do intervalo permitido (max_iterations 0..10, max_attempts 1..10)")
    if not set(limits.retry_on) <= {"timeout", "process_failed"}:
        errs.append("run.retry_on aceita apenas timeout e process_failed")
    agents_raw = raw.get("agents", {})
    if not isinstance(agents_raw, dict) or not agents_raw:
        raise ConfigError(errs + ["[agents.*] ausente"])
    agents: dict[str, AgentConfig] = {}
    for role, item in agents_raw.items():
        if role not in ROLES:
            errs.append(f"agents.{role}: papel desconhecido")
            continue
        if not isinstance(item, dict):
            errs.append(f"agents.{role}: deve ser tabela")
            continue
        found = _agent_errors(role, item, test_mode)
        errs.extend(found)
        if not found:
            agents[role] = AgentConfig(
                role=role, provider=item["provider"], executable=item["executable"], model=item["model"], args=tuple(item.get("args", [])),
                prompt_via=item.get("prompt_via", "stdin"), timeout_seconds=float(item.get("timeout_seconds", 1800)),
                max_output_bytes=int(item.get("max_output_bytes", 2_000_000)), env_allow=tuple(item.get("env_allow", DEFAULT_ENV)),
                alternate_justification=str(item.get("alternate_justification", "")), ownership=tuple(item.get("ownership", [])),
                required_criteria=tuple(item.get("required_criteria", [])),
            )
    if errs:
        raise ConfigError(errs)
    digest = hashlib.sha256(json.dumps(raw, sort_keys=True, ensure_ascii=False, default=str).encode("utf-8")).hexdigest()
    return SupervisorConfig(agents=agents, limits=limits, test_mode=test_mode, digest=digest)


def load_config(path: Path, *, test_mode: bool = False) -> SupervisorConfig:
    if tomllib is None:
        raise ConfigError(["Python >= 3.11 é necessário para ler TOML"])
    try:
        raw = tomllib.loads(path.read_bytes().decode("utf-8-sig"))
    except (OSError, UnicodeDecodeError, tomllib.TOMLDecodeError) as exc:
        raise ConfigError([f"configuração ilegível ({path.name}): {exc}"]) from exc
    return parse_config(raw, test_mode=test_mode)


def resolve_executable(agent: AgentConfig, which: Callable[[str], str | None] = shutil.which) -> str | None:
    """PATH discovery only; never starts the program."""
    found = which(agent.executable)
    if found and found.lower().endswith((".cmd", ".bat")):
        return None
    return found
