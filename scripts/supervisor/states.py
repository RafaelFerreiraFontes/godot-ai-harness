"""Deterministic state table and routing decisions for the 02C supervisor.

Nothing here performs I/O.  HUMAN is a resting state that requests approval; the
supervisor can never produce or imply an approval.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class State(str, Enum):
    PENDING = "PENDING"
    AWAITING_AUTHORIZATION = "AWAITING_AUTHORIZATION"
    RUNNING = "RUNNING"
    VALIDATING = "VALIDATING"
    RECORDED = "RECORDED"
    AWAITING_HUMAN = "AWAITING_HUMAN"
    BLOCKED = "BLOCKED"
    FAILED = "FAILED"
    ABORTED = "ABORTED"
    ITERATION_LIMIT_EXCEEDED = "ITERATION_LIMIT_EXCEEDED"


TERMINAL = frozenset({State.AWAITING_HUMAN, State.BLOCKED, State.FAILED, State.ABORTED, State.ITERATION_LIMIT_EXCEEDED})
FAILURE_TERMINAL = frozenset({State.BLOCKED, State.FAILED, State.ABORTED, State.ITERATION_LIMIT_EXCEEDED})
STOPS = frozenset({State.BLOCKED, State.FAILED, State.ABORTED, State.ITERATION_LIMIT_EXCEEDED})

TRANSITIONS: dict[State, frozenset[State]] = {
    State.PENDING: frozenset({State.AWAITING_AUTHORIZATION}) | STOPS,
    State.AWAITING_AUTHORIZATION: frozenset({State.RUNNING}) | STOPS,
    # RUNNING -> RUNNING is a classified, bounded retry of the same step.
    State.RUNNING: frozenset({State.RUNNING, State.VALIDATING}) | STOPS,
    State.VALIDATING: frozenset({State.RECORDED}) | STOPS,
    # RECORDED -> PENDING opens the next step (possibly Code again, one iteration later).
    State.RECORDED: frozenset({State.PENDING, State.AWAITING_HUMAN}) | STOPS,
    State.AWAITING_HUMAN: frozenset(),
    State.BLOCKED: frozenset(),
    State.FAILED: frozenset(),
    State.ABORTED: frozenset(),
    State.ITERATION_LIMIT_EXCEEDED: frozenset(),
}


class InvalidTransition(RuntimeError):
    pass


def check_transition(current: State, target: State) -> None:
    if target not in TRANSITIONS[current]:
        raise InvalidTransition(f"transição proibida: {current.value} -> {target.value}")


ROUTE = ("coordenador", "orquestrador", "code", "reviewer", "qa", "gate")
LABEL = {"coordenador": "Coordenador", "orquestrador": "Orquestrador", "code": "Code", "reviewer": "Reviewer", "qa": "QA", "gate": "Gate"}
JUDGES = ("reviewer", "qa", "gate")
OK_STATUS = {
    "coordenador": ("planned",),
    "orquestrador": ("ready", "planned"),
    "code": ("implemented",),
    "reviewer": ("reviewed",),
    "qa": ("tested",),
    "gate": ("evaluated",),
}
# Only Code writes project files; QA may only touch caches that the config declares.
WRITER_ROLES = ("code",)


@dataclass(frozen=True)
class Decision:
    kind: str  # next | human | blocked | limit
    role: str | None = None
    iteration: int = 0
    reason: str = ""


def expected_next(role: str) -> str:
    """Label the contract must announce when the role passes."""
    index = ROUTE.index(role)
    return LABEL[ROUTE[index + 1]] if index + 1 < len(ROUTE) else "HUMAN"


def decide(role: str, result: dict, iteration: int, max_iterations: int) -> Decision:
    """Pure routing: maps a validated AGENT_RESULT to the next supervisor step."""
    status, verdict, announced = result.get("status"), result.get("verdict"), result.get("next_agent")
    if status == "blocked" or result.get("blocking_issue"):
        return Decision("blocked", reason="agente reportou bloqueio")
    if role in JUDGES and (verdict == "fail" or status == "changes_required"):
        if announced != "Code":
            return Decision("blocked", reason=f"falha deve retornar a Code, contrato aponta {announced}")
        if iteration + 1 > max_iterations:
            return Decision("limit", reason=f"limite de {max_iterations} iterações atingido")
        return Decision("next", "code", iteration + 1, "retorno a Code por falha")
    if role in JUDGES and verdict != "pass":
        return Decision("blocked", reason=f"veredito {verdict!r} de {role} não é pass nem fail")
    if role not in JUDGES and verdict in ("fail", "inconclusive"):
        return Decision("blocked", reason=f"veredito {verdict!r} em {role}")
    if status not in OK_STATUS[role]:
        return Decision("blocked", reason=f"status {status!r} inválido para {role}")
    want = expected_next(role)
    if announced != want:
        return Decision("blocked", reason=f"next_agent {announced!r} difere da rota {want!r}")
    if want == "HUMAN":
        return Decision("human", reason="aprovação humana pendente")
    return Decision("next", ROUTE[ROUTE.index(role) + 1], iteration, "avanço de rota")
