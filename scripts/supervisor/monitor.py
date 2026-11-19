"""Read-only monitoring and error diagnosis of supervisor runs (never writes, never spawns)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .store import RunStore, StoreError, list_runs

HINTS = {
    "executable_missing": "Instale/ajuste o PATH ou o campo executable do papel; não há fallback de provider.",
    "contract_invalid": "A saída não trouxe exatamente um AGENT_RESULT válido; veja stdout.log do passo e o campo reason.",
    "ownership_violation": "Um papel alterou arquivos fora do seu ownership ou o HEAD mudou; inspecione git status/diff antes de qualquer retomada.",
    "drift": "A árvore ou o HEAD mudou desde o último snapshot; reconcilie manualmente e abra nova execução.",
    "persistence_uncertain": "O journal não pôde ser relido de forma consistente; verifique .chat-decisions/ manualmente.",
    "process_possibly_alive": "Um PID da tentativa anterior ainda existe; confirme o processo antes de prosseguir.",
    "isolation_unavailable": "O isolamento de árvore de processos não pôde ser garantido; a execução foi recusada.",
    "process_unkillable": "O filho pode continuar vivo (kill/wait falhou); use o PID registrado na tentativa, encerre manualmente e abra nova execução.",
    "timeout": "Timeout esgotou as tentativas; revise timeout_seconds ou o tamanho da tarefa.",
    "process_failed": "O processo saiu com código diferente de zero; veja stderr.log do passo.",
    "iteration_limit": "Reviewer/QA/Gate falharam além do limite; decisão humana necessária.",
    "awaiting_human": "Rota concluída. human_approval continua pending; a aprovação é exclusivamente humana.",
}


def summarize(run: dict[str, Any], store: RunStore | None = None) -> dict[str, Any]:
    steps = []
    for step in run["steps"]:
        steps.append({"index": step["index"], "role": step["role"], "iteration": step["iteration"], "result": step.get("result_path"),
                      "attempts": [{"n": a["n"], "pid": a.get("pid"), "exit_code": a.get("exit_code"), "classification": a.get("classification"), "dir": a.get("dir")} for a in step["attempts"]]})
    reason = run.get("reason") or {}
    out = {"task_id": run["task_id"], "run_id": run["run_id"], "state": run["state"], "mode": run.get("mode"), "current_step": run["current"], "reason": reason, "hint": HINTS.get(reason.get("code", "")), "steps": steps, "updated_at": run.get("updated_at")}
    if store is not None:
        out["events_chain_ok"] = store.verify_events()
        out["events"] = len(store.read_events())
    return out


def status(root: Path, task_id: str | None = None, run_id: str | None = None) -> dict[str, Any]:
    if task_id and run_id:
        store = RunStore(root, task_id, run_id)
        return summarize(store.load_state(), store)
    runs = []
    for task, run in list_runs(root, task_id):
        try:
            state = RunStore(root, task, run).load_state()
            runs.append({"task_id": task, "run_id": run, "state": state["state"], "reason": (state.get("reason") or {}).get("code")})
        except StoreError as exc:
            runs.append({"task_id": task, "run_id": run, "state": "UNREADABLE", "reason": str(exc)})
    return {"runs": runs}
