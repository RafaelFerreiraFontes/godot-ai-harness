---
description: Arquitetura do harness
applyTo: 'src/**,skills/**,scripts/**,pyproject.toml'
---
Consulte CONTEXT.md, CONTEXT-MAP.md e docs/adr/ como referência do gda herdado. src/gda, libs/gda-balancing e skills/gda não são contrato do novo runtime. Preserve o legado.
O futuro Core detectará engine/capabilities sem fixar versão e sem depender de Python/daemon/MCP do gda. Use Godot CLI oficial e resolução dinâmica de godot_console e godot-mono_console (aliases, funções ou executáveis).
Detalhes ficam nas futuras skills godot-coding (godot-gdscript e godot-dotnet), godot-testing e godot-linting. Não implemente essas camadas agora. MCP é opcional e exige justificativa.
