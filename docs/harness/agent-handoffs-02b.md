# Etapa 02B — handoffs assistidos e diário persistente

O MVP é local e não chama `claude`, `codex`, `agy`, API nem Zed. Ele preserva evidências entre sessões, valida o `AGENT_RESULT` canônico e produz pacotes compactos para o próximo papel. Uma pessoa confirma cada envio ao provedor seguinte.

## Integrações e limites

| Superfície | Situação no 02B | Uso concreto |
|---|---|---|
| Claude Code | hook nativo documentado, condicional | `Stop`/`SessionEnd` pode encaminhar JSON a `collect-hook`; só arquiva. |
| Codex | hook nativo documentado, condicional/trust review | `Stop`/`SessionEnd` pode chamar o coletor; não inicia subagentes. |
| Antigravity CLI | hooks existem, versão ACP local precisa de confirmação | adaptador de stdout/entrada (`record`); não se declara hook instalado. |
| Zed/ACP | sessões, prompts e capacidades negociados | não é orquestrador cross-provider; não abre múltiplas Threads. |

Todo payload de hook é dado não confiável: nunca é executado como instrução e nunca escolhe modelo, permissão, provider ou aprovação humana.

## Journal privado

```powershell
python scripts/agent_handoff.py init
```

`.chat-decisions/` é ignorado por Git e terá esta forma:

```text
.chat-decisions/
├── INDEX.md / index.json              # última decisão por task_id
├── .locks/T02B-001.lock               # só durante escrita
├── events/{claude,codex,antigravity}/
├── coordenador/
│   ├── AGENT_RESULT_2026-11-16T12-00-00.000000Z_T02B-001_session-1.json
│   ├── prompt-log_2026-11-16T12-00-00.000000Z_T02B-001_session-1.md
│   └── prompt-resume_T02B-001_session-1.md
└── {orquestrador,code,reviewer,qa,gate}/
```

As gravações usam arquivo temporário + replace, lock por `task_id`, nomes UTC seguros para Windows e índice reconstruído. Cada resposta vira arquivo novo (append-only por convenção). Não há rotação automática; defina retenção antes de remover dados. Se for preciso versionar, crie cópia saneada manual em `docs/harness/examples/`, nunca adicione o diretório privado inteiro.

## Fluxo manual assistido

1. Coordenador registra C1–C8, escopo e baseline Git antes de Code. O baseline contém `git status --short --untracked-files=all`, `git diff` e hashes.
2. O operador confirma modelo/permissões e invoca explicitamente o subagente Codex `orquestrador`.
3. Só Code recebe ownership de escrita. Reviewer é subagente Codex explícito e read-only. QA/Gate são contextos Antigravity distintos.
4. Cada papel usa `record`; o próximo consulta apenas `index.json` e o resultado apontado.
5. `handoff` apenas monta JSON para revisão humana; nunca inicia CLI.

```powershell
python scripts/agent_handoff.py record --role coordenador --task-id T02B-001 --session-id claude-123 --result .\result.json --prompt-log .\prompt.md --resume .\resume.md
python scripts/agent_handoff.py handoff --task-id T02B-001 --to Orquestrador
```

O pacote contém `human_confirmation_required`. Recursões Code → Reviewer/QA são decisão humana e devem registrar contador/limite no resumo. `configured_not_runtime_verified` vale apenas para baixo risco com seleção humana explícita e sem mismatch; use `runtime_verified` apenas com metadado do runtime e `mismatch_or_unverified_configuration` nas divergências.

## Segurança e adaptadores

`record` mascara valores simples de `token`, `api_key`, `secret`, `password` e `authorization`; não substitui revisão humana. Não passe credenciais entre provedores, omita caminhos sensíveis quando possível e só persista prompts completos com consentimento deliberado. O hash protege integridade do conteúdo persistido, não prova identidade.

```powershell
python scripts/agent_handoff.py validate .\result.json
Get-Content .\hook-payload.json | python scripts/agent_handoff.py collect-hook --provider claude --event Stop --role code
```

`validate` retorna 0 somente para contrato válido — nunca para aprovação —, 1 para violação e 2 para erro/JSON malformado. `collect-hook` apenas arquiva payload; não converte texto livre em `AGENT_RESULT` nem encaminha provider. Configurações de hooks não foram instaladas automaticamente: revise versão, schema/payload e trust da CLI antes de ativar. Para Antigravity/ACP, capture uma saída exportada e use `record`; não use scraping de UI.
