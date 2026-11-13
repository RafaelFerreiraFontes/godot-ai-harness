# Operação dos agentes — etapa 01
Abra a raiz do clone no VS Code. No Chat selecione o harness Copilot, execute **Chat: Open Customizations** e confira Agents e Instructions sem erros. Selecione Coordenador no menu de agentes. Use nova sessão para revisão independente, anexando diff, plano e evidências. Nenhuma invocação paga foi necessária para preparar estes arquivos.

| Papel | Saída e transição |
| --- | --- |
| Coordenador | Objetivo, escopo, riscos e critérios -> Orquestrador |
| Orquestrador | Tarefas, dependências, ownership por arquivo, evidências -> Code |
| Code | Diff limitado e verificações -> Reviewer |
| Reviewer | Achados independentes com arquivo/linha -> QA ou Code |
| QA | Matriz critério/evidência e veredito -> Gate ou Code |
| Gate | Parecer técnico e pendências -> aprovação humana explícita |

A mudança de papel é manual no seletor do Copilot. Entregue o pacote de contexto ao próximo papel; o Orquestrador pode delegar pelo mecanismo realmente disponível, sem assumir controle de CLI. Não há handoffs automáticos configurados: a referência atual limita `handoffs` ao harness Local. Nesse formato, label/agent/prompt são obrigatórios e send deve ser false; não acrescente esse campo ao target github-copilot. Não criamos cópias Local porque isso duplicaria seis configurações.
Os aliases de tools usados são read/search, edit/execute no Code, execute em QA e agent/todo no Orquestrador. Confirme ferramentas efetivas na sessão. Listas/instruções não são barreiras de segurança: permissões e revisão humana continuam necessárias. Execute pode alterar caches mesmo em QA.

Leia [.github/copilot-instructions.md](../../.github/copilot-instructions.md) e os módulos pertinentes. Copilot aplica globs relativos à raiz, com barras / e padrões separados por vírgula. Codex/Claude não carregam esses módulos automaticamente: seus roteadores mandam lê-los explicitamente. Links não garantem inclusão automática. Regras por linguagem podem se sobrepor às regras de testes/lint de forma complementar. Git e arquitetura valem também para a tarefa como um todo: carregue seus módulos explicitamente quando necessário, mesmo sem arquivo correspondente.

## Pacote de trabalho e evidências
Cada tarefa deve trazer ID, objetivo, entradas, responsável, arquivos exclusivos, dependências, critérios mensuráveis, revisor e evidências esperadas. Registre comandos exatos, cwd, versões, horário, stdout/stderr, exit codes, contagens de testes/skips e caminhos dos logs. Não inclua segredos.
Exemplo de formato de relatório, não evidência executada:
```json
{"task":"T01","criterion":"agentes descobertos","command":null,"cwd":null,"exit_code":null,"stdout_log":null,"stderr_log":null,"semantic_verdict":"inconclusive","tests":{"passed":0,"failed":0,"skipped":0},"technical_gate":"pending","human_approval":"pending","limitations":["verificação na interface pendente"]}
```
Vereditos: pass, fail ou inconclusive. Critério sem evidência fica inconclusivo; falha relevante bloqueia o gate. Exit 0, JSON parseável e valid=true isolados não comprovam comportamento. Diferencie análise estática, startup, testes funcionais e visual. O caso STG está documentado nas instructions de testes.
Aceite desta etapa: seis agentes, YAML válido, tools compatíveis, módulos/globs coerentes, links válidos, política de modelos preservada, diff sem whitespace e limitações reportadas. Aprovação técnica não substitui decisão humana. Commit/push/merge exigem autorização específica.

## Arquitetura e limites
O legado é godot-agent 0.25.0: src/gda, libs/gda-balancing, skills/gda, tests, docs/adr e exemplos. CONTEXT-MAP.md roteia seus domínios; instruções locais de subdomínios continuam pertinentes ao legado. A política deste fork orienta o novo harness; não copie seleção herdada de modelos para ele.
O futuro Core detectará engine/capabilities e resolverá dinamicamente os comandos oficiais godot_console e godot-mono_console. O usuário relatou encerramento headless correto e validou Godot 4.7.2, Python 3.13, uv e .NET SDK 10.0.403; isso é contexto fornecido, não revalidação nesta etapa.
Futuras skills: godot-coding com godot-gdscript/godot-dotnet, godot-testing, godot-linting e godot-assets. Esta última só gerencia/importa/catalogra/analisa recursos, cenas e nodes e auxilia níveis; não gera assets. Catálogo visual com visão de agentes e controle remoto do editor serão adaptadores opcionais com permissões e evidências próprias. A CLI não oferece isso nativamente por pressuposto. MCP só mediante justificativa.
Não implementamos launcher, runtime ou skills completas, não removemos gda e não alteramos STG/HD2D.

## Fontes e compatibilidade
Consulta em 2026-11-13:
- [Custom agents](https://code.visualstudio.com/docs/agent-customization/custom-agents)
- [Custom instructions](https://code.visualstudio.com/docs/agent-customization/custom-instructions)
- [Referência de agentes](https://code.visualstudio.com/docs/agents/reference/custom-agent-file-reference)
- [Referência de instructions](https://code.visualstudio.com/docs/agents/reference/custom-instructions-reference)

O harness determina formato e ferramentas; escolher modelo Claude no Copilot não seleciona o harness Claude. Os arquivos usam target github-copilot, aliases documentados e nenhum ID de modelo não validado. Outros harnesses exigem formatos próprios. A documentação atual anuncia descontinuação do Local em fevereiro de 2027.
Verificação manual restante: confirmar descoberta sem erros, abrir nova sessão sem envio pago, conferir seleção/tools/instructions; um teste comportamental real e revisão entre provedores dependem de autorização para uso dos modelos. Não declarar essa validação realizada com base apenas no YAML.

## Etapa 01.5 — seleção por papel
Siga a [matriz de modelos](model-policy.md) e o [contrato de roteamento](provider-routing.md).
A sequência permanece Coordenador -> Orquestrador -> Code -> Reviewer -> QA -> Gate -> aprovação humana.
As transições continuam manuais; a seleção do agente no Copilot não chama uma CLI.
Antes de enviar, confira provedor/modelo real contra a matriz. Sem correspondência validada,
interrompa a execução do papel e informe a limitação; não use silenciosamente a seleção atual.
Alternativas e otimizações exigem decisão explícita e justificativa. Não há fallback entre provedores.
Reviewer usa sessão independente do Code; QA e Gate usam contextos distintos e preferencialmente
modelos diferentes. No pacote registre identidade, esforço, evidências e limitações de cota.
A confirmação de ID no catálogo/API não comprova seleção no Copilot nem execução da CLI.


## Atualização de configuração — target vscode
Os seis arquivos agora usam o esquema Local por solicitação do usuário. Selecione
o harness Local para usar seus handoffs; target não altera o harness da sessão.
Os parágrafos anteriores sobre ausência de model/handoffs descrevem a configuração
anterior e ficam substituídos por esta seção e pela atualização em provider-routing.md.
Cada agente tem um único model qualificado, model-policy: required, esforço medium,
argument-hint e visibilidade explícita. Os handoffs têm send: false e exigem revisão
antes de enviar. O Reviewer ainda requer nova sessão; Gate requer contexto distinto
do QA. Orquestrador permite somente Code em agents; demais usam lista vazia.
skills não é compatível com vscode e fica apenas como comentário YAML. Não foram
criadas skills ou integrações. Veja a documentação oficial antes de migrar do Local.
