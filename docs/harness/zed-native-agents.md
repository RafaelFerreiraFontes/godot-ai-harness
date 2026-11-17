# Agentes nativos no Zed — etapa 02A

## Escopo e instalação observada
Abra a raiz do projeto ou o worktree de teste em File > Open Folder no Zed.
Em Agent Panel/Threads Sidebar, crie uma thread externa escolhendo Claude Agent,
Codex ou Google Antigravity. Use os agentes ACP já instalados; não é necessário
instalar provedor nem mudar autenticação. Consulte agent: open settings para inspecionar
a seleção, sem modificar configurações globais.

No Windows inspecionado, os três servidores estão registrados em settings.json do Zed.
Claude ACP 0.107.0 contém claude.exe 2.1.323, diferente de Claude Code 2.1.319 do PATH.
Codex ACP 2.6.0 tem dependência @openai/codex 0.166.0, diferente do CLI 0.167.0.
Antigravity ACP usa agy_acp_server.exe/localharness_external.exe 1.5.0, em vez de
presumirmos que chama agy.exe do PATH. Instalação não comprova descoberta ou permissões.
A configuração de projeto .zed/settings.json preexistente contém disable_ai: true.
Ela foi preservada; poderá impedir o painel de IA nesse workspace. Cabe ao usuário
decidir habilitá-lo localmente para o teste. Nenhuma configuração Zed foi alterada.

## Papéis e seleção de modelos

| Papel | Arquivo nativo | Principal | Alternativo por decisão explícita |
| --- | --- | --- | --- |
| Coordenador | .claude/agents/coordenador.md | claude-opus-5-5 | Sonnet 5.5 |
| Code | .claude/agents/code.md | claude-sonnet-5-5 | Opus 5.5 |
| Orquestrador | .codex/agents/orquestrador.toml | gpt-6.1-terra | GPT-6.1 Sol |
| Reviewer | .codex/agents/reviewer.toml | gpt-6.1-sol | GPT-6 Astra |
| QA | .agents/agents/qa/agent.md | Gemini 3.8 Flash, seleção manual | Gemini 4 Hydrogen |
| Gate | .agents/agents/gate/agent.md | Gemini 4 Hydrogen, seleção manual | Gemini 4 Carbon, pendente |

IDs Claude constam do catálogo oficial; CLI aceita full IDs. Codex usa IDs nativos,
sem sufixo de conta/vendor do Codex Bridge. O campo Local model do VS Code não é
ID de CLI. No Antigravity, inherit/flash/pro não fixam uma versão exata:
mantivemos inherit, sem fingir equivalência. agy models lista
gemini-3.8-flash-medium e gemini-4-hydrogen-medium; Carbon não foi listado.
No Zed, escolha o modelo pelo seletor exposto pelo adapter e confira identidade real
antes de enviar qualquer tarefa. Sem correspondência verificável, pare.
Somente Claude em Claude, GPT autorizado em Codex e Gemini em Antigravity.
Não há fallback automático entre provedores; alternativas exigem justificativa.
Não troque provider/auth por indisponibilidade nem presuma que o adapter segue o PATH.

## Ativação nativa versus corpo de instruções
Claude: .claude/agents é um catálogo de subagentes; não cria seis entradas ACP.
No CLI, --agent coordenador ou --agent code pode selecionar o papel como principal;
--model com o ID completo confirma intenção de modelo. Esses comandos iniciam sessão
e NÃO foram executados como teste de inferência. Em Zed, use o mecanismo nativo
que o adapter realmente expuser; peça a invocação explícita do subagente apenas
após confirmar sua descoberta e modelo. /agents, quando disponível, pode listar
definições; claude agents --json nesta versão lista sessões de fundo, não prova arquivos.

Codex: os TOMLs são agentes de projeto; a sessão pai continua dona de permissões,
provider e MCP. Não existe aqui um switch --agent que invente uma thread ACP.
Quando houver invocação de agente customizado na sessão, solicite o nome exato e
confirme modelo/resultado. Para papel principal sem suporte nativo, carregue explicitamente
developer_instructions como orientação e selecione o modelo manualmente; isso não
aplica automaticamente configurações TOML de subagente.

Antigravity: agy agents lista os nomes no runtime direto; --agent qa/gate e o painel
/agents são mecanismos nativos do CLI. O ACP instalado pode não expor esse painel,
ou usar outra descoberta. mainAgent: true e subagent: false permitem seleção principal
sem autorizar invocação automática. Confirme modelo manualmente, mesmo com nome do papel.

Em qualquer integração que só permita anexar um arquivo, o corpo orienta o modelo,
mas o frontmatter não restringe ferramentas por mágica. Use permissões externas
restritivas e confirme-as. Se isso não puder ser garantido, deixe a execução pendente
e use apenas análise sobre contexto fornecido.

## Permissões efetivas e seus limites
- Claude Coordenador: Read/Glob/Grep, sem Write/Edit/Bash/PowerShell/Agent, permissionMode plan.
- Claude Code: Read/Glob/Grep/Write/Edit/Bash, permissionMode default e sem Agent.
  Bash permite efeitos amplos: exige autorização por tarefa e supervisão do runtime.
- Codex Orquestrador/Reviewer: .codex/config.toml pede sandbox read-only no pai,
  approval_policy on-request; sem apps/plugins/memories/pedido de elevação nos agentes.
  sandbox_mode colocado apenas em um TOML de agente não imporia sandbox próprio.
  Config de projeto depende de confiança/carregamento e overrides do adapter.
  No CLI, confirme explicitamente -s read-only ao iniciar a sessão de análise.
- Antigravity QA: view_file/grep_search/run_command, sem edição, comando sem autoexecução.
  Testes podem escrever caches: só comandos autorizados e isolados, com efeitos registrados.
- Antigravity Gate: view_file/grep_search, sem shell/edição, commandExecutionPolicy off.
  off é política de autoexecução, não prova universal de bloqueio de shell.

No diagnóstico config/read sem overrides, sandbox_mode e approval_policy vieram null:
o carregamento efetivo da configuração de projeto não foi comprovado. Com parâmetros
explícitos -c sandbox_mode=\"read-only\" e -c approval_policy=\"on-request\", a mesma
API retornou read-only/on-request. Use a seleção restritiva no adapter ou o CLI com
parâmetros explícitos; não declare sandbox ativo apenas porque o arquivo existe.
O controle initialize do Claude listou code/coordenador com modelos completos, mas
avisou que outra fonte de autenticação tem precedência sobre claude.ai. Nenhuma
credencial foi exibida nem alterada. Verifique cobrança/autenticação no runtime antes
de enviar tarefa; não presumimos uso da assinatura.
Permissões via ACP ainda exigem verificação manual; não foram demonstradas por prompts.
Nenhum papel pode usar o próximo agente como pretexto para iniciar outro provedor.

## Prompts iniciais por thread
Envie uma tarefa real somente após decidir que seu uso de assinatura/cota está autorizado.
Os exemplos abaixo não são comandos executados nem mecanismo garantido de ativação.

### Coordenador — nova thread Claude
> Selecione e confirme Claude Opus 5.5. Ative o subagente coordenador se a integração o
> descobrir; senão leia .claude/agents/coordenador.md como instruções de papel e informe
> a limitação. Confirme leitura/pesquisa sem shell/edição. Planeje a tarefa T-ID a seguir.
> Siga docs/harness/agent-result.md. Não inicie outro provedor.

### Orquestrador — nova thread Codex
> Confirme GPT-6.1 Terra e sessão read-only. Use o agente orquestrador descoberto em
> .codex/agents/orquestrador.toml; sem ativação nativa, leia developer_instructions e
> declare a limitação de permissões. Decomponha este plano em tarefas com ownership.
> Siga docs/harness/agent-result.md e devolva pacotes manuais para Code.

### Code — nova thread Claude
> Confirme Claude Sonnet 5.5. Ative code de .claude/agents/code.md se disponível;
> senão aplique o corpo e declare que as permissões precisam de configuração externa.
> Implemente somente T-ID nestes arquivos exclusivos. Execute apenas verificações
> autorizadas, registre efeitos e entregue diff/evidências no contrato AGENT_RESULT.

### Reviewer — nova thread Codex independente
> Confirme GPT-6.1 Sol e read-only. Ative reviewer de .codex/agents/reviewer.toml,
> ou leia suas instruções declarando que isso não impõe sandbox. Revise este pacote
> sem reutilizar a sessão do Code. Não edite. Cite severidade, arquivo/linha e evidências.
> Retorne docs/harness/agent-result.md, sem autoaprovação.

### QA — nova thread Antigravity
> Confirme Gemini 3.8 Flash exato, não apenas tier flash. Selecione qa descoberto em
> .agents/agents/qa/agent.md; sem seleção nativa, leia o corpo e confirme as permissões
> externas antes de comandos. Verifique estes critérios; não altere produção.
> Registre logs, screenshots realmente analisadas, exit codes e vereditos semânticos.

### Gate — outra thread Antigravity
> Confirme Gemini 4 Hydrogen exato, não tier pro. Selecione gate de
> .agents/agents/gate/agent.md ou aplique o corpo declarando a limitação.
> Use contexto distinto do QA, sem shell ou edição. Confira revisão e evidências,
> emita pass/fail/inconclusive no contrato compartilhado e aguarde decisão humana.

## Transferência, revisão e concorrência
Siga [AGENT_RESULT](agent-result.md), fonte única. Transfira ID, objetivo, critérios,
arquivos/ownership, decisões, modelo real, evidências e limitações. Não replique o
histórico completo. Mantenha só um escritor por arquivo. Pare e renegocie ownership
se outra sessão modificar o mesmo alvo. Reviewer começa independente; QA e Gate
têm threads distintas, preferencialmente Flash e Hydrogen. pass técnico não é aceite humano.

## Teste seguro em raspy-plume
O worktree observado está detached HEAD em 9a43a178, com .zed/ não rastreado.
Não foi removido, atualizado ou convertido em branch. Não execute merge/cherry-pick
enquanto houver trabalho local sem estratégia de preservação. Antes de qualquer integração,
inspecione no clone e no worktree: git status --short, git log -5 --oneline e git diff.

Após revisão e autorização específica, o usuário pode criar um commit 02A na branch
de implementação. Até isso ocorrer, arquivos novos não aparecem em git diff normal:
não use somente git diff como pacote completo desta etapa.

Exemplo futuro, para execução pelo usuário apenas após preservar mudanças locais
e obter árvore limpa. Substitua o SHA pelo commit 02A realmente aprovado:

```powershell
git -C 'D:/My Personal Projects/Web Projects/worktrees/godot-ai-harness/raspy-plume/godot-ai-harness' status --short
git -C 'D:/My Personal Projects/Web Projects/worktrees/godot-ai-harness/raspy-plume/godot-ai-harness' switch -c test/02a-native-agents
git -C 'D:/My Personal Projects/Web Projects/worktrees/godot-ai-harness/raspy-plume/godot-ai-harness' cherry-pick <SHA-02A-aprovado>
```

Use nome novo se a branch de teste existir; não force branch existente. Cherry-pick
leva só o commit aprovado e acomoda divergência, mas pode conflitar: resolva com
revisão humana ou aborte o cherry-pick; não use reset para esconder conflitos.
Se houver vários commits 02A, examine e selecione explicitamente a sequência.
Com alterações locais, primeiro preserve-as em uma branch própria/commit ou backup
revisado pelo usuário; não faça stash automático. Nenhum desses comandos foi executado.
Abra então essa pasta no Zed e verifique a configuração local disable_ai antes de testar.

## Próxima etapa e fontes
02B poderá projetar adaptador próprio ACP e orquestração entre provedores com identidade,
permissões, cotas, ownership e evidências verificáveis; nada disso está implementado aqui.
Resultados reais e pendências: [validation-02a.md](validation-02a.md).

Consulta em 2026-11-13:
- [Zed external agents](https://zed.dev/docs/ai/external-agents)
- [Claude subagents](https://code.claude.com/docs/en/sub-agents)
- [Claude model IDs](https://platform.claude.com/docs/en/models/overview)
- [Codex subagents](https://learn.chatgpt.com/docs/agent-configuration/subagents)
- [Antigravity subagents](https://antigravity.google/docs/subagents)
- [Antigravity discovery](https://antigravity.google/docs/customization-discovery/)
- [Antigravity agents](https://antigravity.google/docs/cli/commands/agents)

## Etapa 02B — persistência e handoff assistido

O Zed/ACP continua sem automação cross-provider declarada. Antes de trocar Thread, use o
coletor local de `agent-handoffs-02b.md` para persistir resultado, resumo e baseline. Abra
manualmente a próxima Thread, selecione provider/modelo autorizado, confirme permissões e
entregue somente o pacote compacto. Não altere settings globais nem assuma que hook abre
Threads no Zed. Hooks dependem de versão, configuração e trust do runtime; o coletor pode
arquivar eventos, mas nunca roteia/invoca uma sessão.
