# EVERREACH — Taxonomia ambiental ATIVA EV-ECO-1.1.1 (pacote v20)

Esta pasta `00_Taxonomia_Ambientes/` e a **UNICA entrada ativa para ambientes**.

## Carregar no Codex
- `Everreach_Taxonomia_250_Ambientes_EV_ECO_1_1.json` — 250 registros (100 naturais, 100 construidos, 50 anomalos), com os 100 originais inalterados.
- `Everreach_EV_ECO_1_1_Indice_250.json` — indice para consultas por ID.
- `Everreach_EV_ECO_1_1_1_Regras_Fisicas_250.json` — REGRAS ATIVAS corrigidas (vegetacao sem P1; construcao tipada; anomalia vinculada ao proprio ID).

Arquivos de auditoria, validacao, teste e guia acompanham esta pasta. As regras e taxonomias **anteriores** ficam em `HISTORICO_TAXONOMIA_NAO_IMPORTAR/` somente para rastreabilidade.

## Importante
- **Nao somar** a taxonomia antiga de 100 ambientes a esta de 250: os 100 ja estao incluidos.
- **Nao carregar** os dois JSON de regras: o ativo e apenas o `...1_1_1_Regras_Fisicas_250.json`.
- A taxonomia nao gera solo, clima, rios, construcoes, flora ou anomalias por si; V4/T1/C2/JR1 e modulos hidricos provem evidencias e o backend confirma instancias.
- As 50 anomalias permanecem desativadas por padrao; so autorizacao canonica especifica as libera.
- Fase 0.9: foco nos 100 ambientes naturais; os demais sao camadas aditivas.
- A integracao real com o backend nao foi testada aqui.
