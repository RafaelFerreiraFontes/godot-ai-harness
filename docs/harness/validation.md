# Evidências da etapa 01 — 2026-11-13
- Clone: D:/My Personal Projects/Web Projects/godot-ai-harness.
- Status inicial limpo, única branch local main; origin aponta para RafaelFerreiraFontes/godot-ai-harness. Nenhum remote upstream configurado; referência upstream fornecida pelo usuário: aigengame/godot-agent.
- Branch criada: feature/01-vscode-agents-instructions, base ae208aebd47b23cfe94debde67329dde799c9b25. main permaneceu nesse SHA.
- Inspecionados AGENTS.md, CLAUDE.md, CONTEXT.md, CONTEXT-MAP.md, pyproject.toml, inventário de testes e .github. RULES.md ausente. O legado e os roteadores de subdomínios foram preservados.
- Mudanças: seis .github/agents/{coordenador,orquestrador,code,reviewer,qa,gate}.agent.md; .github/copilot-instructions.md; oito .github/instructions/{architecture,python-powershell,gdscript,dotnet,testing,linting,assets,git-docs}.instructions.md; AGENTS.md; CLAUDE.md; docs/harness/{workflow,model-policy,validation}.md.
- Patches preparados com apply_patch e aplicados com git apply --check --recount e git apply --recount: exit 0.
- Validação local Python 3.13/PyYAML 6.0.3: seis agentes e oito instructions parseados, tipos/frontmatter, target, aliases de tools e ausência de model/handoffs verificados; links dos agentes/instructions existentes; oito amostras de glob correspondentes: exit 0.
- Globs testados por conversão local dos padrões usados para regex; isso não equivale ao resolvedor real do VS Code.
- git diff --check: exit 0. Checagem adicional dos arquivos novos por espaços finais: zero problemas.
- code --status: exit 0; VS Code 1.146.0, janela godot-ai-harness aberta, inventário reporta oito instructions e um copilot-instructions. Isso confirma inventário de workspace, não descoberta dos seis agentes nem inclusão nas requisições.
- Nenhuma execução de engine, teste funcional do legado, revisão por outro modelo/provedor ou inspeção visual do seletor realizada. Não foram usados modelos pagos ou chaves. STG/HD2D intocados. Sem commit/push.
- Próximo aceite: conferir Agents/Instructions em Chat: Open Customizations e seleção/tools no Copilot; revisão independente e aprovação humana. Runtime/skills ficam para etapa futura.
```json
{"stage":"01","static_validation":"pass","yaml_agents":6,"yaml_instructions":8,"glob_samples":8,"diff_check_exit":0,"whitespace_issues":0,"vscode_inventory":"observed","vscode_agent_discovery":"not_validated","behavioral_tests":"not_run","independent_review":"pending","human_approval":"pending"}
```

## Etapa 01.5 — 2026-11-13
Estado inicial: branch feature/01-vscode-agents-instructions, com mudanças não commitadas da etapa 01 (AGENTS.md/CLAUDE.md modificados; .github/agents, copilot-instructions, instructions e docs/harness novos). Todas preservadas. Nenhuma branch criada; main segue ae208aebd47b23cfe94debde67329dde799c9b25.

Arquivos atualizados nesta etapa: os seis .github/agents/*.agent.md; .github/copilot-instructions.md; docs/harness/model-policy.md, workflow.md e validation.md. Novo: docs/harness/provider-routing.md. AGENTS.md/CLAUDE.md avaliados e mantidos sem novas alterações; oito módulos de instructions preservados.

### Verificações e resultados
- Documentações oficiais consultadas: referências VS Code, Claude/Claude Code, Codex e codelab Antigravity, além das três páginas de preços; fontes e data constam em provider-routing.md.
- agy --help e agy models: executados sem prompt; Flash low/medium/high e Hydrogen low/medium/high/xhigh listados. Carbon ausente. Modelos Claude e GPT-OSS também aparecem, mas são proibidos nessa CLI pela política.
- claude --help/--version/auth status: Claude Code 2.1.319, opção --model e aliases documentados, OAuth firstParty. Modelo local sonnet; saldo/limites e acesso efetivo a Opus/Sonnet/Haiku 5.5 não testados.
- codex --help/--version/login status: 0.167.0, opção --model, autenticação ChatGPT. Cache de modelos datado de 2026-11-13 contém gpt-6.1-terra, gpt-6.1-sol, gpt-6-astra e gpt-6-luna. Configuração local gpt-5.6-terra observada, sem alteração; não garante seleção da matriz.
- Nenhum ID configurado no YAML: todos os IDs Copilot permanecem pendentes. Não confundimos ID API, catálogo CLI e modelo selecionado no editor.
- Validador local Python/PyYAML: exit 0, seis agentes com campos/tipos/target/tools compatíveis, oito módulos preservados, matriz conferida contra a política, ausência de model/handoffs e de fallback entre provedores. 28 links internos válidos e zero espaços finais nos arquivos inspecionados.
- git diff --check: exit 0. Checagem direta cobre whitespace dos arquivos novos ainda não adicionados ao Git.
- Tentativa de inspeção visual: autorização de janela expirou; nenhum controle de UI efetuado.
- A pedido do usuário, conexão ao SSE http://127.0.0.1:3333/sse estabelecida: HTTP 200 e initialize MCP 2024-11-05 aceito por vscode-mcp-bridge 0.2.5. tools/list executado.
- Via MCP, get_workspace_info confirmou D:/My Personal Projects/Web Projects/godot-ai-harness. get_open_tabs retornou os seis agentes como language chatagent, isDirty=false. get_diagnostics retornou lista vazia. Isso comprova reconhecimento dos arquivos e ausência de diagnósticos publicados, não descoberta no seletor, inclusão no contexto ou seleção efetiva de modelos.
- O MCP listado não fornece ferramenta de inventário Copilot/modelos. Não foram executados comandos arbitrários do editor, alterações de settings, prompts ou inferência para completar a verificação.

### Pendências e próximos passos
Confirmar modelos no seletor Copilot e IDs inseridos por completions do harness; só então considerar model com model-policy: required. Enquanto isso a atribuição permanece no corpo e o operador deve interromper se o provedor/modelo efetivo não coincidir. Carbon depende de aparecer no agy models. Opus possui ID oficial documentado; aliases Claude são suportados, mas acesso da conta e execução permanecem pendentes. Cotas atuais são desconhecidas.
Revisão independente, contextos distintos de QA/Gate e aprovação humana continuam necessários. Não houve sessão multiagente, chamada paga, alteração de configs globais, runtime/skills/adaptadores, STG/HD2D, commit ou push.

```json
{"stage":"01.5","static_verdict":"pass","agents":6,"instruction_modules":8,"internal_links":28,"model_ids_in_yaml":0,"matrix_consistency":"pass","cross_provider_fallback":"prohibited","diff_check_exit":0,"vscode_mcp":"connected","vscode_language":"chatagent","vscode_published_diagnostics":[],"copilot_model_ids":"pending","carbon_agy_id":"not_listed","cli_inference":"not_run","quota_remaining":"unknown","independent_review":"pending","human_approval":"pending"}
```

## Atualização de frontmatter Local — 2026-11-13
Por solicitação do usuário, os seis agentes passaram a target: vscode. Esta atualização substitui as conclusões anteriores de ausência de model/handoffs; as evidências antigas permanecem como histórico.
- Preenchidos model, model-policy: required, reasoning-effort: medium, argument-hint, user-invocable, disable-model-invocation, agents e handoffs. Um modelo por papel, sem fallback automático.
- Modelos Local: Opus 5.5 (Claude Agent), Sonnet 5.5 (Claude Agent), GPT 6.1 Terra (openai-codex), GPT 6.1 Sol (openai-codex), Gemini 3.8 Flash (antigravity), Gemini 4 Hydrogen (antigravity).
- Nomes/vendor e suporte ao esforço medium confirmados no cache chat.cachedLanguageModels.v2 do VS Code, lido em modo somente leitura. Nenhuma credencial foi consultada. Cache não comprova disponibilidade online nem execução.
- Orquestrador pode invocar somente Code; demais agents: []. Code permite invocação como subagente; demais papéis impedem invocação por modelo. Todos permanecem selecionáveis pelo usuário.
- Nove handoffs com destinos existentes e send: false: cinco progressões, Reviewer/QA para Code e Gate para QA/Coordenador. Independência de revisão e contextos distintos continuam exigidos.
- Conforme a referência oficial, Local não aceita skills: o campo fica apenas em comentário YAML como # skills: []. Nenhuma skill nova criada; gda herdado não foi ativado como dependência do novo fluxo.
- Validador Python/PyYAML: exit 0; seis frontmatters, seis modelos conferidos, esforço suportado, nove handoffs, trinta links internos nos agentes e protocolos JSON válidos; sem whitespace final.
- git diff --check: exit 0.
- MCP http://127.0.0.1:3333/sse, vscode-mcp-bridge 0.2.5: seis agentes reconhecidos como chatagent, isDirty=false; get_diagnostics retornou [] após as mudanças.
- Nenhuma sessão de inferência executada, configuração global alterada, commit ou push. Branch preservada: feature/01-vscode-agents-instructions.
- Pendências: disponibilidade/seleção online e comportamento real dos providers; handoffs não demonstram isolamento de sessão. Local tem remoção anunciada para fevereiro de 2027.
Fonte: [referência oficial de agentes](https://code.visualstudio.com/docs/agents/reference/custom-agent-file-reference).

```json
{"configuration":"vscode-local","static_verdict":"pass","agents":6,"models_matched_to_editor_cache":6,"handoffs":9,"handoff_send":false,"active_skills_field":false,"skills_reason":"unsupported_by_vscode_target","editor_diagnostics":[],"inference":"not_run","human_approval":"pending"}
```
