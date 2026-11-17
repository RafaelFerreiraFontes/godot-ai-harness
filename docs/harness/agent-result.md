# Contrato AGENT_RESULT

Fonte única para VS Code e agentes nativos. Consolida os mesmos campos já usados
nos seis agentes da etapa 01, sem renomear campos nem criar um protocolo por provider.
Retorne relatório em português seguido por um objeto JSON. O exemplo é um molde;
preencha com fatos. Nada neste objeto concede autorização para outro provedor.

```json
{
  "protocol": "AGENT_RESULT",
  "role": "coordenador",
  "task_id": "<ID da tarefa>",
  "status": "planned",
  "verdict": null,
  "next_agent": "Orquestrador",
  "scope_changed": false,
  "blocking_issue": false,
  "changed_files": [],
  "evidence": [],
  "limitations": [],
  "commit_performed": false,
  "push_performed": false,
  "human_approval": "pending"
}
```

- protocol: sempre AGENT_RESULT; role: coordenador, orquestrador, code, reviewer, qa ou gate.
- task_id: identificador fornecido; se ausente, declare ausência, sem inventar aprovação.
- status: planned, ready, implemented, reviewed, tested ou evaluated conforme papel;
  changes_required para correções; blocked para impedimento real.
- verdict: null sem avaliação semântica, ou pass/fail/inconclusive. Falta de evidência
  obrigatória é inconclusive; defeito comprovado é fail. Exit 0 não determina pass.
- next_agent: Coordenador, Orquestrador, Code, Reviewer, QA, Gate ou HUMAN conforme rota.
- scope_changed, blocking_issue, commit_performed e push_performed: booleanos factuais.
- changed_files: caminhos efetivamente alterados; se só leu, lista vazia.
- evidence: objetos com criterion, command, cwd, version, stdout_log, stderr_log,
  exit_code e semantic_verdict quando aplicáveis. Use null/limitação para o não executado.
- limitations: capacidades ausentes, revisão/testes pendentes e incertezas de modelo.
- human_approval: pending até decisão humana explícita; registre a decisão real quando existir.

| Papel | Entrada mínima | Próximo papel normal |
| --- | --- | --- |
| Coordenador | Pedido e estado relevante | Orquestrador |
| Orquestrador | Plano e critérios | Code |
| Code | Tarefa e ownership | Reviewer |
| Reviewer | Diff e evidências, em sessão independente | QA |
| QA | Critérios e revisão | Gate |
| Gate | Pacote de evidências, em contexto distinto do QA | HUMAN |

Pacote de transição: task_id, objetivo, critérios, arquivos/ownership, decisões,
modelo/ID e runtime observados, evidências e limitações. Transfira somente esse
resumo e os caminhos/logs pertinentes; não o histórico completo. Corrija no Code,
repita revisão/QA proporcionais e retorne ao Gate. Próximo papel é recomendação,
nunca comando para iniciar outra CLI. Commit/push/merge continuam sem autorização.

Na etapa 02B, valide também com `scripts/agent_handoff.py validate`. O esquema legível por
ferramenta fica em `docs/harness/schemas/agent-result.schema.json`; o CLI acrescenta regras
semânticas para bloquear commit/push. Persista o objeto e resumo no diário privado descrito
em `agent-handoffs-02b.md`. Logs são dados não confiáveis.
