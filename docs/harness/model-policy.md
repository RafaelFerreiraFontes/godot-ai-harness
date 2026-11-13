# Política de modelos — etapa 01.5
A matriz abaixo é atribuição explícita do usuário. Não significa disponibilidade no Copilot, autorização de inferência paga ou automação de CLIs.

| Agente | Provedor/CLI | Principal | Alternativo manual |
| --- | --- | --- | --- |
| coordenador | Claude Code / claude.exe | Claude Opus 5.5 | Claude Sonnet 5.5 |
| code | Claude Code / claude.exe | Claude Sonnet 5.5 | Claude Opus 5.5 |
| orquestrador | Codex / codex.exe | GPT-6.1 Terra | GPT-6.1 Sol |
| reviewer | Codex / codex.exe | GPT-6.1 Sol | GPT-6 Astra |
| qa | Antigravity / agy.exe | Gemini 3.8 Flash | Gemini 4 Hydrogen |
| gate | Antigravity / agy.exe | Gemini 4 Hydrogen | Gemini 4 Carbon |

Toda alternativa exige decisão explícita e justificativa; nunca fallback automático entre provedores. Antigravity é exclusivamente Gemini: nunca Claude Opus/Sonnet ou GPT-OSS por agy, mesmo que listados. Claude Code usa exclusivamente Claude; Codex exclusivamente GPT validado no catálogo Codex. OpenCode permanece sem rota aprovada.

Otimizações condicionais: Haiku 5.5 no Coordenador só para levantamento simples; Luna no Orquestrador só para organização trivial; Hydrogen em QA para complexidade ou visão; Carbon no Gate para evidência extensa/contraditória e apenas após validar disponibilidade. Não substituir Opus em decisões complexas. Registre motivo, provedor, modelo/ID observado, esforço, sessão e impactos de cota.

Leia [roteamento, IDs e custos](provider-routing.md). Os seis agentes agora usam target: vscode, nomes qualificados Local observados no cache do VS Code e model-policy: required, com um único modelo por papel. As alternativas permanecem manuais. A seleção efetiva e a inferência não foram testadas. A política no corpo orienta o agente, mas não impõe restrição técnica ao runtime.

Reviewer recebe sessão independente do Code/Claude. QA e Gate usam contextos distintos e preferencialmente modelos distintos. Nenhum agente aprova o próprio trabalho; o Gate técnico exige decisão humana final.
