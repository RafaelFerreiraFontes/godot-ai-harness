# Validação 02A — agentes nativos no Zed
Data da inspeção: 2026-11-13. Resultado: configuração estática pronta para revisão;
descoberta e comportamento têm limites explícitos abaixo. Nenhuma inferência foi enviada.

## Git e preservação
- Clone principal: D:/My Personal Projects/Web Projects/godot-ai-harness.
- Origem da branch feature/02a-native-agents: feature/01-vscode-agents-instructions,
  SHA 9a43a1782b8bba7fed67b7c669b2a759639714ca.
- Histórico inspecionado: 9a43a178 limpeza posterior a 0863b6aa (etapa 01), seguido
  de ae208aeb (main). Branch nova usa o estado atual da etapa 01, não reverte a limpeza.
- origin: https://github.com/RafaelFerreiraFontes/godot-ai-harness.git; nenhum remote
  adicional foi criado. git status, branch -avv, worktree list e log -5 inspecionados.
- Estado inicial do principal: apenas .zed/ não rastreado. Preservado, sem staging.
- raspy-plume: worktree intencional em
  D:/My Personal Projects/Web Projects/worktrees/godot-ai-harness/raspy-plume/godot-ai-harness,
  detached HEAD em 9a43a178; .zed/ não rastreado no início e no fim. Nenhuma escrita,
  switch, merge, cherry-pick, prune, reset ou clean nesse worktree.
- HEAD principal permanece 9a43a178 na nova branch. Sem commit/push/merge.
- .claude/settings.json, .codex/hooks.json, AGENTS.md e CLAUDE.md preservados.
  Nenhuma alteração no runtime GDA, skills, fixtures STG/HD2D ou configurações globais.

## Arquivos
Criados:
- .claude/agents/coordenador.md e .claude/agents/code.md.
- .codex/agents/orquestrador.toml e .codex/agents/reviewer.toml.
- .codex/config.toml (somente configuração do pai read-only/on-request).
- .agents/agents/qa/agent.md e .agents/agents/gate/agent.md.
- docs/harness/agent-result.md, zed-native-agents.md e validation-02a.md.

Modificados:
- Os seis .github/agents/*.agent.md: somente a seção AGENT_RESULT foi substituída
  por referência ao contrato único; models, tools, agents e handoffs preservados.
- docs/harness/workflow.md e provider-routing.md: referências e limites da 02A.
Arquivos novos ainda não rastreados não aparecem em git diff --stat normal.

## Fontes consultadas
- https://zed.dev/docs/ai/external-agents
- https://code.claude.com/docs/en/sub-agents
- https://platform.claude.com/docs/en/models/overview
- https://learn.chatgpt.com/docs/agent-configuration/subagents
- https://antigravity.google/docs/subagents (incluindo tab=cli)
- https://antigravity.google/docs/customization-discovery/
- https://antigravity.google/docs/cli/commands/agents

## Modelos e permissões
| Papel | Configuração nativa | Alternativo manual | Permissões e limite |
| --- | --- | --- | --- |
| Coordenador | claude-opus-5-5 | Sonnet 5.5 | Read/Glob/Grep, plan, sem edição/shell/delegação |
| Code | claude-sonnet-5-5 | Opus 5.5 | Read/Glob/Grep/Write/Edit/Bash, default, sem Agent |
| Orquestrador | gpt-6.1-terra | GPT-6.1 Sol | requer pai read-only; sem apps/plugins/memories/elevação |
| Reviewer | gpt-6.1-sol | GPT-6 Astra | requer pai read-only; sem apps/plugins/memories/elevação |
| QA | inherit; selecionar Gemini 3.8 Flash exato | Hydrogen | view_file/grep_search/run_command; mainAgent, sem subagent, autoexecução off |
| Gate | inherit; selecionar Gemini 4 Hydrogen exato | Carbon pendente | view_file/grep_search; sem shell/edição/subagent, autoexecução off |

Claude full IDs constam da documentação e dos metadados nativos de descoberta.
Codex debug models --bundled retornou, com exit 0, gpt-6.1-terra, gpt-6.1-sol,
gpt-6-astra e gpt-6-luna. Não usamos os nomes qualificados do VS Code como IDs CLI.
agy models retornou, com exit 0, Flash e Hydrogen low/medium/high, Hydrogen xhigh,
além de modelos não autorizados; só Gemini é permitido. Carbon não apareceu.
IDs candidatos principais: gemini-3.8-flash-medium e gemini-4-hydrogen-medium.
O esquema Antigravity documenta inherit/flash/pro, não versões exatas: inherit foi
mantido e seleção manual é obrigatória. Pro não comprova Hydrogen. Sem fallback
entre provedores; alternativas e otimizações exigem decisão explícita/justificativa.
Nenhuma garantia de disponibilidade de conta ou cobrança é deduzida do catálogo.

Codex custom agents herdam provider, MCP e permissões do pai; sandbox_mode no agente
não seria eficaz. Foi criada configuração de projeto restritiva, mas seu carregamento
não foi comprovado: config/read sem overrides retornou sandbox_mode=null,
approval_policy=null e modelo global gpt-5.6-terra. Com overrides explícitos de sessão,
config/read retornou read-only/on-request. Seleção de modelo do pai também deve ser
confirmada quando não houver ativação nativa. Não alteramos trust/config global.
Bash/run_command podem causar efeitos mesmo com instruções conservadoras; supervisão,
autorização por tarefa e isolamento continuam necessários. Não houve teste de escrita negativa.

## Descoberta e diagnósticos sem inferência
| Verificação | Evidência | Resultado |
| --- | --- | --- |
| Claude Code --version | 2.1.319 | confirmado |
| Controle stream-json initialize, sem user prompt | exit 0, agents contém code=claude-sonnet-5-5 e coordenador=claude-opus-5-5 | descoberta CLI confirmada |
| Claude stderr na inicialização | outra fonte de auth prevalece sobre login claude.ai; conectores desativados | cobrança/método efetivo precisam de confirmação; credencial não exibida nem alterada |
| Codex CLI --version | 0.167.0 | confirmado |
| codex --strict-config app-server --print-startup-config | exit 0, appServerVersion 0.167.0 | diagnóstico de startup, não descoberta dos TOMLs |
| codex debug prompt-input sem prompt | exit 0, não contém nomes customizados | inconclusivo para descoberta |
| Codex app-server initialize + config/read | sem erros; com overrides retornou read-only/on-request | restrição explícita confirmada em metadados, não comportamento |
| agy agents e agy agent | exit 0, saída vazia | descoberta não comprovada |
| agy --agent qa --mode plan sem mensagem | tela de confiança do workspace e seleção Argon; encerrado por Ctrl+C, exit 0 | não aceitamos confiança nem executamos tarefa; QA/modelo exato pendentes |

A primeira execução do auxiliar de metadados Claude terminou com erro de codificação
de saída; o auxiliar foi corrigido e repetido, retornando discovery com exit 0.
Isso foi falha de coleta, não do agente. Nenhum prompt de usuário foi enviado.
A geração do esquema diagnóstico Codex concluiu; não encontrou endpoint de listagem
de agentes no esquema consultado. Não criamos endpoint, wrapper ou ACP próprio.

## Zed ACP: instalação versus execução
settings.json global registra claude-acp, codex-acp e antigravity-acp.
Artefatos locais observados:
- Claude ACP 0.107.0, contendo claude.exe 2.1.323.
- Codex ACP 2.6.0, dependência @openai/codex 0.166.0 e README local descrevendo
  inicialização via app-server e possibilidade de overrides de modelo/permissões.
- Antigravity ACP 1.5.0, agy_acp_server.exe e localharness_external.exe.

Isso comprova instalação, não ativação de cada papel pela integração. Não presumimos
que o ACP use os mesmos binários/modelos do PATH. Não foi enviada tarefa no Zed.
O .zed/settings.json de projeto tem disable_ai: true; cabe ao usuário habilitar
quando decidir testar. Arquivo e configurações globais foram mantidos.
O guia inclui seis prompts iniciais e fallback manual de leitura das instruções,
sempre declarando que corpo de prompt não aplica permissões do frontmatter.

## Validação estática
Validador local temporário com Python 3.13, PyYAML já disponível e tomllib padrão:
- seis agentes nativos, campos/tipos conferidos com as referências oficiais;
- dez frontmatters YAML (quatro nativos e seis VS Code), três TOMLs (dois agentes e pai);
- modelos exatos para Claude/Codex e inherit explícito para Antigravity;
- listas mínimas de ferramentas documentadas; disponibilidade efetiva Antigravity ainda pendente;
- 14 campos do AGENT_RESULT original consolidados em uma única fonte;
- todos os doze agentes referenciam esse contrato, sem cópia divergente do JSON;
- links locais existentes, ausência de whitespace final e git diff --check com exit 0.

A checagem detectou dois links relativos Antigravity incorretos, corrigidos antes
do resultado final pass. Não foram instaladas dependências. Os auxiliares de
inspeção/validação ficaram fora do repositório alvo e não são runtime/adaptadores.

## Pendências e aceite humano
Pronto para revisão estática independente; descoberta Codex/Antigravity, exposição dos
papéis no Zed, permissões efetivas ACP, seleção de modelos e testes comportamentais
permanecem pendentes. Não há aprovação humana nem evidência de fluxo multi-provider
executado. Etapa 02B deverá projetar integração própria apenas após essas verificações.

Para raspy-plume, siga a seção de worktrees no guia zed-native-agents.md: inspecionar
árvore/divergências, preservar .zed e trabalho local, e somente após aprovação criar
commit 02A e branch de teste nova para cherry-pick explícito. Nada foi aplicado lá.

```json
{"stage":"02A","static_verdict":"pass","native_agents":6,"yaml_frontmatters":10,"toml_files":3,"protocol_fields":14,"claude_cli_discovery":"confirmed","codex_cli_discovery":"inconclusive","antigravity_cli_discovery":"blocked_by_workspace_trust","zed_acp_installations":"observed","zed_role_activation":"not_tested","permissions_behavior":"not_tested","inference":"not_run","worktree_raspy_plume":"preserved","commit_performed":false,"push_performed":false,"human_approval":"pending"}
```
