---
description: Lint e formatação
applyTo: '**/*.py,**/*.ps1,**/*.gd,**/*.cs,.github/**,pyproject.toml'
---
Consulte pyproject.toml e CI para Ruff check/format e Pyright do legado. Use ferramentas locais; não instale linters nem reformate em massa.
Para PowerShell/GDScript/C# confirme configuração e disponibilidade de PSScriptAnalyzer, linter GDScript ou ferramentas .NET; ausência é lacuna explícita.
Execute git diff --check. Para agentes/instructions valide YAML, tipos, links e globs. Lint não prova comportamento. A futura godot-linting consolidará os passos.
