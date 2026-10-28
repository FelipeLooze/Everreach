# Everreach — Dataset 14 v4 · Geologia, raridade e fragmentos

## O que mudou

Agora cada um dos **120 materiais originais** possui um perfil de ocorrência e de fragmentos soltos, além dos seus 14 atributos de 0 a 100 e dos seus 3 perfis de extração da v3 (**360 preservados**). Todos os IDs, nomes, atributos e perfis de extração anteriores estão inalterados.

**O material não é um gerador de loot.** O backend deve instanciar uma fonte física persistente em uma formação compatível. O mundo pode ser expandido por novas regiões, mas voltar à mesma gruta nunca refaz a geração. Jogador e NPCs enfrentam o mesmo estoque físico.

### Entender os números

* `indice_raridade_0_100`: quão incomum é um material, **não** porcentagem de drop (Adamantita 97 **não** significa 3% por escavação).
* `intensidade_geracao_referencia_por_milhao_de_formacoes_elegiveis`: referência *de worldgen*, apenas quando um candidato geológico novo, real e único é instanciado. Exige geologia, região, evidência e regras adicionais. Nunca rodar em passagem de tempo, visita, inspeção, saque ou coleta. A intensidade é sugestão de balanceamento, não promessa nem probabilidade obrigatória para engine.
* `indice_dificuldade_de_localizacao_0_100`: encontrar pistas/acesso, não habilidade para quebrar rocha.
* `indice_de_potencial_exposicao_0_100`: possibilidade relativa de uma fonte existente ficar exposta, **não é chance de fragmento por visita**.
* `volume_deposito_referencia_intervalo_unidades_abstratas`: tamanho aproximado de uma fonte recém-criada. Não credita materiais em inventário. Fonte real pode ser maior ou menor por evidências canônicas.
* Dificuldade para extrair e requisitos de proficiência/ferramentas permanecem nos três perfis `extracao_e_obtencao` já existentes.

| Material | Raridade /100 | Intensidade referencial / milhão de formações elegíveis | Modelo de origem | Encontrar /100 | Regra de fragmentos |
|---|---:|---:|---|---:|---|
| Ferro | 15 | 312750 | veio_montanhoso | 24 | permitido_com_fonte_e_desprendimento |
| Cobre | 22 | 265500 | veio_montanhoso | 26 | permitido_com_fonte_e_desprendimento |
| Prata | 52 | 38829 | veio_montanhoso | 44 | condicional_com_fonte_e_desprendimento |
| Ouro | 65 | 2204 | aluvião | 46 | raro_exige_fonte_exposta_e_evento_comprovado |
| Mithril | 88 | 54 | veio_montanhoso | 66 | excepcional_exige_evento_especifico_e_autorizacao |
| Oricalco | 93 | 41 | veio_arcano | 71 | excepcional_exige_evento_especifico_e_autorizacao |
| Adamantita | 97 | 1 | veio_profundo | 84 | bloqueado_por_padrao_somente_evento_canonico_excepcional |
| Aetherium | 99 | 1 | veio_anomalo | 76 | bloqueado_por_padrao_somente_evento_canonico_excepcional |
| Ferro Estelar | 88 | 54 | meteoritico | 62 | excepcional_exige_evento_especifico_e_autorizacao |

## Fragmentos soltos não são loot aleatório

1. Uma fonte **preexistente** (jazida, corpo meteórico, depósito aluvial, organismo mineralizante etc.) precisa estar registrada.
2. Um acontecimento físico específico (erosão real, impacto, desabamento, escavação passada ou perda de carga) desprende ou transporta uma quantidade limitada de material. O backend subtrai essa quantidade da origem e persiste `source_id`, `event_id`, `item_instance_id`, posição e volume.
3. O item fica no mapa até alguém retirá-lo ou outro evento físico alterar seu estado. **Não reaparece por reload, revisita ou por narração.**
4. Materiais raros requerem fonte exposta e evento verificável; muito raros exigem evento excepcional validado; **lendários não formam fragmentos naturais por padrão**, salvo evento excepcional canônico.
5. Para minério meteórico não é necessário um veio subterrâneo, mas é obrigatório um **corpo/impacto físico** persistido com massa finita. Para biominerais, vale a fonte biológica real.

## Regras mínimas para implementação pelo Codex

- Importar apenas o JSON ativo em `11_Geologia_Materiais_D14`. Não importar pastas `HISTORICO_*_NAO_IMPORTAR`.
- A matriz de 100 ambientes é uma **referência de compatibilidade**, não cria minério. Uma floresta sobre uma jazida não é automaticamente uma jazida.
- Criar oportunidades geológicas **apenas uma vez** por fonte/região/seed estável; ler estado já persistido quando o jogador retorna.
- Validar condições de geologia antes de ponderar ocorrências. Sem prova da formação, nenhum candidato vira fonte.
- Criar instâncias `deposito`, `desprendimento`, `fragmento` e `transferencia` com IDs idempotentes, procedência e volume finito. O mesmo `event_id` não pode gerar duas vezes.
- Para minério lendário ou formação anômala, exigir uma condição excepcional registrada pelo worldgen autoritativo ou outro acontecimento canônico. **Nem a narrativa nem uma inspeção podem autorizar criação.**
- Separar: geração da jazida → descoberta → acesso → extração → refino/fabricação. Comprar um material existente não exige mineração.
- O mundo pode conter materiais inéditos não catalogados, derivados de sistemas de criação/validação, mas também devem ter proveniência e propriedades persistentes.
- As intensidades e faixas de volume são um **ponto inicial para o balanceamento**, não parâmetros calibrados por playtest.

## Arquivos

- `{MAIN}`: 120 materiais completos + nova camada de raridade e origem.
- `{INDEX}`: índice leve por material.
- `{VALID}`: verificações estruturais e de referência.
- Pacote completo v13 inclui histórico v1/v2/v3 e torna a **v4 a única ativa**.

**Estado**: conteúdo validado estruturalmente, ainda não implementado ou testado no backend.
