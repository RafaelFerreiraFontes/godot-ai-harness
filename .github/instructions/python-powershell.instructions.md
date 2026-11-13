---
description: Python e PowerShell
applyTo: '**/*.py,**/*.ps1,**/*.psm1,pyproject.toml'
---
Respeite Python >=3.13, uv.lock e ferramentas declaradas no pyproject.toml. Use ambiente local existente; não instale dependências sem necessidade e autorização.
Em PowerShell use Get-Command para descobrir aliases/funções/executáveis; preserve argumentos como listas e caminhos com espaços. Evite strings de comando.
Capture LASTEXITCODE imediatamente para comandos nativos; trate erros PowerShell separadamente. Sucesso do shell não prova sucesso do processo filho.
