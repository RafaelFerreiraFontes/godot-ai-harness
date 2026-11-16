# zed-flow-smoke — validador experimental de AGENT_RESULT

Experimento T02A-FLOW-001. Python 3.13, somente biblioteca padrão, sem `gda`.
Contrato de origem: `docs/harness/agent-result.md` (não alterado).

## Uso

```
python -I -B experiments/zed-flow-smoke/validate_agent_result.py <arquivo.json | ->
python -I -B -m unittest discover -s experiments/zed-flow-smoke -v
```

Saída: `{"valid": bool, "errors": [{"field","code","message"}]}`.
Exit `0` válido; `1` violação do contrato; `2` JSON malformado (`malformed_json`),
erro de leitura (`read_error`) ou uso incorreto (`usage`), sem traceback.
Códigos de contrato: `missing_field`, `invalid_type`, `invalid_value`, `unknown_field`.

## Fixtures

`valid.json` (molde do contrato), `missing_task_id.json`, `invalid_verdict.json`
(`"approved"`), `truncated.json` (JSON truncado). Raiz em lista, booleano como
string, protocolo incorreto e campo extra são cobertos nos testes.

## Decisões locais (não mudam o contrato)

- Campos fora dos 14 obrigatórios são rejeitados com `unknown_field`.
- `human_approval` e `task_id` aceitam qualquer string não vazia.
- `evidence` é só lista de objetos; chaves internas não são validadas.
- `changed_files` e `limitations` são listas de strings.
- Booleanos estritos: `"false"`, `0` e `1` são rejeitados.
- `NaN`/`Infinity`, inteiros acima do limite do Python e aninhamento excessivo geram `malformed_json` (exit 2).
- Entrada UTF-8 (BOM tolerado). Chaves duplicadas no JSON não são detectadas.

## Limitações

Valida forma, não verdade: não comprova que evidências existem, nem coerência
entre papel, status e próximo agente. `valid=true` e exit 0 não substituem revisão.
