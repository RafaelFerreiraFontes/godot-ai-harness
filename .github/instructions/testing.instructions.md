---
description: Testes e evidências
applyTo: 'tests/**,**/tests/**,**/test_*.py,**/*Tests.cs'
---
Leia docs/test-standards.md antes de criar ou alterar testes herdados. Use fixtures isoladas; STG e HD2D são intocáveis nesta etapa.
Separe unitário, análise estática, boot headless, integração .NET e visual/editor. Registre contagens/skips, timeout, stdout/stderr, exit codes e JSON semântico.
No STG, scene list produziu JSON com erro GUT ausente em stderr (res://addons/gut/gut_loader_the_scene.gd): isso não aprova runtime. script validate --all com valid=true é evidência estática de outro escopo.
A futura godot-testing deverá verificar erros semânticos mesmo com exit code zero.
