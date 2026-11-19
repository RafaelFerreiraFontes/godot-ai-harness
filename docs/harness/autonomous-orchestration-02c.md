# Etapa 02C — supervisor de orquestração autônoma

O supervisor (`scripts/agent_supervisor.py` + pacote `scripts/supervisor/`) executa a rota
Coordenador → Orquestrador → Code → Reviewer → QA → Gate → HUMAN a partir de CLIs
configuráveis, grava o journal 02B automaticamente e para em **AWAITING_HUMAN**. Só stdlib,
Python ≥ 3.11 (`py -3`; o `python` do PATH pode ser 3.10). É independente do Zed e do GDA.

> **Política pendente (T0/T0b).** `AGENTS.md`, `code.md`, `coordenador.md` e
> `provider-routing.md` ainda dizem que nenhuma CLI é iniciada automaticamente. Esta entrega
> **não os emendou**: a decisão cabe ao humano. Por isso o padrão é seguro: `plan`/`--dry-run`
> não iniciam nada, e `--execute` só roda os papéis nomeados em `--authorize` (ou confirmados
> um a um com `--confirm-each`). Nenhum provedor real foi invocado nos testes.

## Uso

```powershell
py -3 scripts/agent_supervisor.py plan --config meu.toml --task-id T-1            # sem processo, sem escrita
py -3 scripts/agent_supervisor.py run  --config meu.toml --task-id T-1 --request pedido.md --dry-run
py -3 scripts/agent_supervisor.py run  --config meu.toml --task-id T-1 --request pedido.md --execute --authorize coordenador,orquestrador
py -3 scripts/agent_supervisor.py status --task-id T-1 [--run-id R]               # somente leitura
py -3 scripts/agent_supervisor.py resume --config meu.toml --task-id T-1 --run-id R --confirm --authorize code
py -3 scripts/agent_supervisor.py abort  --config meu.toml --task-id T-1 --run-id R
```

`--test-mode` aceita `provider = "fake"` (fixtures em `tests/fakes/`). Exit codes: 0 repouso
válido (AWAITING_HUMAN ou aguardando autorização), 1 BLOCKED/FAILED/ABORTED/
ITERATION_LIMIT_EXCEEDED, 2 uso ou configuração inválidos. Exit 0 nunca é aprovação.

## Configuração

Veja [`supervisor.example.toml`](supervisor.example.toml). Por papel: `provider`, `executable`
(descoberto no PATH, sem iniciar), `args` com placeholders `{model} {role} {task_id} {cwd}
{prompt} {prompt_file}`, `model`, `prompt_via` (`stdin` ou `arg`), `timeout_seconds`,
`max_output_bytes`, `env_allow`, `ownership`. Globais em `[run]`: `max_iterations`,
`max_attempts`, `retry_on`. Rejeitado na carga: provider/família de modelo fora da matriz de
`model-policy.md`, alternativo sem `alternate_justification`, flags de bypass
(`--dangerously-*`, `bypassPermissions`, `--mode auto`, `danger-full-access`…), shells,
shims `.cmd/.bat`, variáveis sensíveis em `env_allow`, Codex sem `-s read-only`, Code sem
`ownership`. **Os argv do exemplo vêm de `--help` e não foram exercitados com provedores
reais**; identidade do modelo em runtime nunca é verificada (`runtime_model_verified=false`).

## Estados

`PENDING → AWAITING_AUTHORIZATION → RUNNING → VALIDATING → RECORDED → (próximo passo | AWAITING_HUMAN)`;
terminais: `AWAITING_HUMAN` (único sucesso), `BLOCKED`, `FAILED`, `ABORTED`,
`ITERATION_LIMIT_EXCEEDED`. Falha (`fail`/`changes_required`) de Reviewer/QA/Gate volta a Code
com `iteração+1`; acima de `max_iterations` termina em ITERATION_LIMIT_EXCEEDED. Veredito
`inconclusive` bloqueia. HUMAN é pedido de aprovação: o supervisor recusa qualquer resultado
com `human_approval` ≠ `pending` e nunca preenche esse campo.

## Garantias e mecanismos

- **Processo**: argv sem shell, `stdin` por pipe, saída limitada e redigida, árvore de
  processos isolada (Job Object no Windows, sessão/`killpg` em POSIX); timeout e cancelamento
  (SIGINT ou `abort`) encerram a árvore. Se o isolamento não for possível, a execução é recusada.
- **Resultado**: exatamente um objeto `AGENT_RESULT` na saída, validado pelo schema 02B,
  papel/tarefa corretos, evidências com `criterion` para avanço. Exit 0 não basta.
- **Ownership**: snapshot Git (HEAD + hash dos arquivos sujos) antes/depois de cada passo.
  Só Code escreve, dentro dos globs de `ownership`; HEAD alterado ou escrita fora → BLOCKED.
  Arquivos já sujos antes do passo não são atribuídos ao agente.
- **Journal**: cada passo grava resultado, prompt-log e resumo via `Journal.record` e relê
  arquivos, hashes e índice antes de `RECORDED`; divergência → BLOCKED (`persistence_uncertain`).
- **RunStore**: `.chat-decisions/runs/<task>/<run_id>/` com `state.json` atômico,
  `events.jsonl` encadeado por hash, logs por tentativa e lock por tarefa.
- **Retomada**: exige `--confirm`, mesma configuração, cadeia de eventos íntegra, HEAD e árvore
  iguais ao último snapshot e nenhum PID anterior vivo. Um registro gravado antes de uma queda
  é adotado, não duplicado. Terminais não retomam.
- **Retry**: só `timeout`/`process_failed`, até `max_attempts`; nunca em contrato inválido,
  violação de ownership ou cancelamento.

## Correções M1–M7 em `agent_handoff.py` (aditivas)

M1/M2 `handoff` devolve `criteria`, `resume`, `prompt_log_path` e `baseline` Git; M3 resumes
da mesma sessão não se sobrescrevem; M4 NaN/Infinity rejeitados; M5 UTF-8 com BOM e UTF-16 com
BOM lidos, codificação inválida → exit 2; M6 lock órfão (PID morto) é recuperado; M7 sem
`dt.UTC` (Python 3.10). M6b: stdout/stderr passam por mascaramento extra (Bearer, `sk-`, `ghp_`).

## Limitações

Smoke com provedores reais não executado (exige autorização separada). Argv de `agy` e a
leitura de stdin pelas CLIs não foram verificados. Job Object é atribuído logo após o
`CreateProcess`, e uma corrida teórica com netos criados nesse intervalo não é coberta. Sem
rotação/retensão do journal. PID reutilizado não é distinguível: o supervisor bloqueia em vez
de supor.

## Correções após revisão independente

- **Vínculo provider/executável/modelo:** o executável precisa ser `claude`, `codex` ou `agy`
  conforme o provider, e os args devem selecionar o modelo exatamente uma vez (`--model`/`-m`
  com `{model}` ou o mesmo literal validado); overrides `-c model=...` e duplicatas são recusados.
- **Ownership por papel:** só Code tem globs de escrita (curinga irrestrito recusado); QA só
  declara globs de cache; os demais papéis não aceitam ownership. O guard em runtime aplica a
  mesma regra, independente da configuração.
- **Evidências vs veredito:** um juiz com `verdict=pass` não pode ter evidência `fail` ou
  `inconclusive`; Code não pode avançar com evidência `fail`. `required_criteria` (opcional,
  por papel) exige evidência `pass` para cada critério listado.
- **Retomada:** após queda com tentativa já concluída, o supervisor reconcilia (ok → validação,
  falha sem tentativas → FAILED) e nunca excede `max_attempts`; há também guarda dura em `_attempt`.
- **Runner:** tudo após `Popen` (inclusive `on_start`) fica em `try/finally`, que encerra a
  árvore e fecha handles mesmo se a persistência do PID falhar.
- **Runner (R6):** se a atribuição ao Job falhar, o filho não atribuído é morto diretamente
  (`proc.kill()`), a espera é limitada (10 s) e o Job e os pipes são fechados em `finally`.
- **Runner (R7):** o `finally` do runner executa kill, espera, join, fechamento de pipes e do Job
  de forma independente; qualquer falha vira `ProcessCleanupError` (com o PID, encadeando a
  exceção original). O engine registra o PID, bloqueia como `process_unkillable` e nunca faz retry
  nem declara a árvore encerrada sem confirmação.
