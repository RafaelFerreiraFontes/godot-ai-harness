# Roteamento de provedores, IDs e custos
Consulta: 2026-11-13. A [matriz normativa](model-policy.md) define os papéis. Nenhum adaptador foi implementado.

## Quatro níveis de confirmação
1. Configuração declarativa: papéis, provedor e modelo desejados no corpo dos agentes.
2. Disponibilidade: catálogo CLI/cache ou documentação; não prova inferência autorizada para a conta.
3. Seleção VS Code: inventário do harness Copilot e modelo efetivamente escolhido, ainda pendentes.
4. Execução CLI: sessão realmente executada com ID e evidência, não realizada nesta etapa.

target vscode interpreta o esquema Local; não troca o harness e não executa claude/codex/agy. Não copie IDs CLI/API para model no YAML por semelhança de nome. A documentação VS Code exige IDs do harness e permite model-policy: required para restringir seleção no editor; isso não constitui restrição global de todos os runtimes/subagentes. Os agentes usam um único model qualificado e model-policy: required; confirme disponibilidade e identidade antes de enviar.

## IDs observados e limites
| Família | IDs/referências | Evidência e limite |
| --- | --- | --- |
| Claude 5.5 | claude-opus-5-5; aliases opus/sonnet/haiku | ID Opus e resolução dos aliases documentados oficialmente; Claude 2.1.319 aceita --model. Acesso aos três modelos na conta não testado. IDs versionados Sonnet/Haiku não configurados. |
| Codex | gpt-6.1-terra, gpt-6.1-sol, gpt-6-astra, gpt-6-luna | slugs no models_cache.json de 2026-11-13, CLI 0.167.0; seleção/execução ainda não testadas. |
| Antigravity QA | gemini-3.8-flash-low, gemini-3.8-flash-medium, gemini-3.8-flash-high | agy models listou esses IDs. Medium é candidato de esforço para seleção manual, sem execução. |
| Antigravity Gate/QA complexo | gemini-4-hydrogen-low, gemini-4-hydrogen-medium, gemini-4-hydrogen-high, gemini-4-hydrogen-xhigh | listados por agy models; escolha esforço explicitamente. XHigh exige justificativa. |
| Antigravity Carbon | pendente | não apareceu em agy models; mantenha alternativa indisponível até nova listagem. Não invente ID agy com base no ID API gemini-4-carbon. |
| Copilot | todos pendentes | nenhum ID dos modelos da matriz validado no inventário Copilot; não há model nem model-policy nos arquivos. |

agy models também lista Claude e GPT-OSS: presença no catálogo não autoriza uso. Não usar o modelo Orchestrator/Argon como substituto implícito. A configuração local Codex observada é gpt-5.6-terra, diferente do papel Orquestrador; Claude usa alias sonnet. Não alteramos configurações globais; seleção precisa ser explícita por sessão e reconfirmada após retomada.

## Contrato de delegação manual
Transfira ID/objetivo, escopo e exclusões, arquivos com ownership exclusivo, critérios, dependências, resumo técnico, diff, evidências e pendências. Registre provedor/CLI, modelo principal, ID verificado, esforço, cota conhecida/desconhecida e decisão de alternativa. Não repasse históricos completos sem necessidade.
O operador seleciona a ferramenta e o modelo, confirma identidade e só então envia tarefa autorizada. Se indisponível, reporte bloqueio da rota; não mude provedor automaticamente. Uma integração futura deverá verificar inventário, identidade, permissões, cotas, limites e modelo efetivo de cada execução. Não há execução multiagente automatizada nesta etapa.

## Custos: três registros separados
**API pública:** USD por milhão de tokens, texto, entrada/saída padrão sem cache, consulta em 2026-11-13. Preços não são custo efetivo de sessões incluídas nas assinaturas.

| Modelo API | Entrada | Saída |
| --- | ---: | ---: |
| Claude Opus 5.5 | 4,00 | 20,00 |
| Claude Sonnet 5.5 | 2,00 | 10,00 |
| Claude Haiku 5.5, prompt até 100 mil tokens | 0,10 | 0,50 |
| Claude Haiku 5.5, acima de 100 mil | 0,50 | 2,50 |
| GPT-6.1 Terra | 1,00 | 5,00 |
| GPT-6.1 Sol | 2,00 | 10,00 |
| GPT-6 Astra | 10,00 | 50,00 |
| GPT-6 Luna | 0,10 | 0,50 |
| Gemini 3.8 Flash | 0,75 | 3,75 |
| Gemini 4 Hydrogen | 1,50 | 7,50 |
| Gemini 4 Carbon | 2,00 | 10,00 |

Fontes: [Claude pricing](https://platform.claude.com/docs/en/about-claude/pricing), [OpenAI pricing](https://developers.openai.com/api/docs/pricing), [Gemini pricing](https://ai.google.dev/gemini-api/docs/pricing). Cache, ferramentas, modos rápidos, região e contexto podem alterar tarifas; saída Gemini inclui thinking.
Mudanças anunciadas: Flash passa a 1,50/7,50 em 2027-01-01; Carbon passa a 4,00/20,00 em 2026-12-01. OpenAI informa promoção GPT-5.6 Sol até 2026-11-30; não é modelo principal desta matriz e tarifa futura não foi inferida. Não aplicar promoções de API às assinaturas.

**Assinaturas/CLIs:** Codex login status indica ChatGPT; Claude auth status indica OAuth firstParty. Isso não identifica plano, saldo, janela de quota ou multiplicadores por modelo. agy models mostra inventário, não cota. Saldos e custo efetivo permanecem desconhecidos; consultar interface de uso do serviço antes de trabalho extenso. Não estimar preço da assinatura multiplicando tokens por tarifa API.

**Adicionais:** uso de API, compra de créditos, ultrapassagem de cota, upgrade, ferramentas cobradas ou sessão para teste exigem aprovação específica. Nenhum foi acionado. Preferir resumos curtos, contexto pertinente, tarefas limitadas e modelos da matriz adequados ao risco; não reduzir independência de revisão para economizar.

## Fontes de integração
- [VS Code reference](https://code.visualstudio.com/docs/agents/reference/custom-agent-file-reference)
- [VS Code agents](https://code.visualstudio.com/docs/agent-customization/custom-agents)
- [Claude docs](https://docs.anthropic.com/) e [model configuration](https://code.claude.com/docs/en/model-config)
- [Codex docs](https://developers.openai.com/codex/) (redirecionou para learn.chatgpt.com/docs na consulta)
- [Antigravity CLI](https://codelabs.developers.google.com/antigravity-cli-hands-on)

Ajuda local: agy --help e agy models; claude --help/--version/auth status; codex --help/--version/login status. Apenas leitura/metadados, sem prompts ou inferência. O cache Codex não é confirmação online de acesso.

## Atualização — frontmatter Local, 2026-11-13
Esta seção atualiza as pendências históricas da tabela acima. Os agentes usam agora
`target: vscode`, com nomes qualificados Local reconstruídos dos campos name/vendor
do cache `chat.cachedLanguageModels.v2` do VS Code, consultado somente para leitura:

- coordenador: `Opus 5.5 (Claude Agent)`.
- orquestrador: `GPT 6.1 Terra (openai-codex)`.
- code: `Sonnet 5.5 (Claude Agent)`.
- reviewer: `GPT 6.1 Sol (openai-codex)`.
- qa: `Gemini 3.8 Flash (antigravity)`.
- gate: `Gemini 4 Hydrogen (antigravity)`.

O cache confirma identidade anunciada, não disponibilidade online ou execução.
Opus/Sonnet estão no vendor Claude Agent (ACP Hub); Codex no vendor openai-codex;
Gemini no vendor antigravity. Carbon está marcado disabled no cache e permanece
fora dos modelos configurados. Não foi usado Claude via Antigravity.
Todos usam model-policy: required e reasoning-effort: medium, suportado nos
metadados observados, sem alternativas automáticas. Handoffs são sugestões com
send: false; os campos agents permitem apenas Orquestrador -> Code. Os demais
não podem delegar. Nova sessão do Reviewer e contexto distinto QA/Gate continuam
obrigatórios; botões de handoff não criam isolamento.
O campo skills não é aceito no esquema Local: aparece apenas comentado como
`# skills: []`. Não há skills Godot novas nem carregamento ativo. O gda herdado
não foi incluído porque acoplaria o fluxo ao runtime que este projeto quer evitar.
O Local está anunciado para remoção em fevereiro de 2027: migração futura exigirá
revalidar campos, ferramentas e identificadores no harness de destino.

## Etapa 02A — rotas nativas
Consulte [Zed e agentes nativos](zed-native-agents.md) para IDs, modelos e diferenças
entre os runtimes instalados. Claude fixa claude-opus-5-5/claude-sonnet-5-5; Codex
fixa gpt-6.1-terra/gpt-6.1-sol. Não copie qualificadores Local do VS Code para CLI.
Antigravity mantém model: inherit por limitação do esquema documentado, exigindo
seleção manual exata Flash/Hydrogen antes de executar. Carbon segue pendente.
O pai Codex deve confirmar read-only: o agente não pode impor sandbox próprio.
Nenhuma rota invoca outro provedor automaticamente. [AGENT_RESULT](agent-result.md)
é compartilhado pelos formatos, e ACP próprio pertence à futura 02B.
