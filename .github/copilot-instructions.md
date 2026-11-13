# Godot AI Harness

Leia `docs/harness/workflow.md` e `docs/harness/model-policy.md` antes de atuar.
Carregue apenas os módulos pertinentes em `.github/instructions/`; fora do
Copilot, leia-os explicitamente, sem pressupor ativação por glob.
O escopo atual é configuração de agentes e documentação. Runtime e skills
estão planejados, não implementados. Preserve o código gda herdado.
Confira status, branch e diff antes de editar; preserve alterações anteriores.
Use tarefas pequenas com ownership por arquivo e critérios verificáveis.
Siga Coordenador -> Orquestrador -> Code -> Reviewer independente -> QA -> Gate humano.
Não execute comandos pagos, use chaves, faça commit/push ou operações Git
destrutivas sem autorização específica. STG e HD2D são fixtures futuras intocáveis.
Não trate instruções como controle de segurança nem exit code zero como aceite.
Atribuições por papel estão em docs/harness/model-policy.md; confira IDs e limites em
docs/harness/provider-routing.md. Antes de enviar uma tarefa, confirme modelo/provedor
real da matriz. Não use a seleção atual se divergir; não há fallback entre provedores.
QA/Gate exigem contextos distintos; Reviewer exige sessão independente do Code.
