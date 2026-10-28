# Everreach — Locais e Formações Fantásticas v2 — Ley Lines

**Versão:** `everreach.locais_formacoes.v2` • 240 arquétipos originais preservados • 56 manifestações reutilizáveis.

O JSON `Everreach_Locais_Fantasticos_v2.json` é a fonte canônica. O CSV é visão simplificada para revisão, não material para importar como JSON. Nenhuma localização geográfica, mapa de Ley Lines, instância, recompensa ou habilidade é criada aqui.

## Preservação

- Todos os 240 registros originais de `catalogo` continuam com os mesmos campos e valores originais; só foi acrescentado `geografia_arcana`.
- Metadados de versão evoluíram; contratos v1 foram mantidos e receberam `geografia_arcana_v2`.
- Nomes, classes de fantasia, textos, IDs, habitats, raridades, pesos e requisitos anômalos **não foram alterados**.
- Hash SHA-256 do JSON v1 autoritativo: `85c01e77945915c7784970d7fa30888a3f217156557163285f9cbcc25c47d6ce` (rastreabilidade, sem arquivo histórico no pacote).

## `geografia_arcana` — por arquétipo

| Campo | Tipo / enum | Significado |
|---|---|---|
| `schema_extensao` | string fixa | `everreach.locais.arcano.v2` |
| `afinidade_arcana` | `nenhuma`, `baixa`, `moderada`, `alta`, `excepcional` | Compatibilidade qualitativa, não poder |
| `relacao_com_ley_lines` | `independente`, `favorecido_proximidade`, `favorecido_convergencia`, `associado_nexo`, `exige_condicao_arcana_especifica`, `evita_energia_intensa` | Preferência de variação, **não exigência física automática** |
| `sensibilidade_a_intensidade` | `nenhuma`, `baixa`, `moderada`, `alta`, `excepcional` | Resposta hipotética a fonte real; não define bônus ou mana |
| `dependencia_arcana_obrigatoria.existe` | bool | `true` nos 30 locais anômalos, `false` nos naturais/fantásticos |
| `dependencia_arcana_obrigatoria.tipo` | `nenhuma` / `fonte_anomala_canonica_especifica` | Origem estritamente necessária ao local de base |
| `dependencia_arcana_obrigatoria.fonte_anomala_exigida_id` | ID `EV-ANO-*` ou `null` | Para anômalos deve corresponder exatamente ao original |
| `dependencia_arcana_obrigatoria.match_exato_com_canon` | bool | Validação por ID, não autorização genérica |
| `dependencia_arcana_obrigatoria.ley_line_especifica_obrigatoria` | bool, atualmente `false` | Ley Lines não são requisito universal nem mesmo para anomalias |
| `manifestacoes_possiveis_ids` | array de IDs `EV-ARC-MAN-*` | Opções válidas para análise; não ativa nenhum efeito |
| `variacoes_procedurais_condicionais[]` | array | Condições reais para possíveis variantes **do mesmo arquétipo** |
| `regra_preservacao` | objeto | Flags contra criação automática de mundo, recompensas e efeitos |

## Variações

As variantes normais usam `linha_ativa_proxima`, `linha_fraca_persistida` (apenas para locais que evitam alta intensidade), `convergencia_persistida` ou `nexo_persistido`; locais anômalos sempre exigem `anomalia_canonica_especifica_confirmada` com o ID explícito em `id_fonte_anomala_exata`.

O mesmo local pode ser inteiramente não mágico (forma base) ou manifestar diferenças ambientais quando **fonte arcana persistida + suporte físico real + elegibilidade + autorização específica, se houver** forem confirmados. A ausência de rede arcana não bloqueia local natural ou fantástico; **ausência de evidência não conta como autorização**.

## Vocabulário `Everreach_Manifestacoes_Arcanas_v1.json`

56 entradas `EV-ARC-MAN-NNNN`, separando `visual`, `investigavel` e `potencial_mecanico_pendente`.

`requisito_fisico_ou_arcano` é tag para contrato com geografia, hidrologia, flora, materiais e fontes canônicas; o backend resolve evidência. Somente após evidência poderá materializar uma manifestação específica. Mesmo manifestações visuais não criam automaticamente elementos físicos (pedras, árvores, névoa, água ou cristais). Efeitos mecânicos ficam **indefinidos** até existir sistema autoritativo.

### Cenários de integração

- **Gruta com drusas reais, sem magia**: mantém o arquétipo original, sem efeitos arcanos.
- **Mesma gruta com Ley Line persistida**: pode receber ecos, luminescência ou ressonância se evidências reais satisfizerem a manifestação. Não adiciona cristais automaticamente.
- **Gruta próxima a nexo**: pode receber manifestação candidata adicional; a mera existência do nexo não cria uma dungeon.
- **Ilha flutuante**: continua exigindo a anomalia exata em `fisica_e_fantasia.fonte_anomala_exigida_id`; uma Ley Line genérica **não basta**.
- **Floresta com magia latente**: pode existir independente de Ley Lines, respeitando flora presente e suas regras.
- **Campo sem mana**: continua permitido pelo gerador físico. Não limitar locais a nível de jogador.

## Regras de importação (Codex)

1. World Genesis V4/T1/JR1/C2/W1 etc. confirma contexto físico e elegibilidade ambiental.
2. Futuro sistema de Geografia Arcana entrega fontes reais (`ley_line_id`, `nexo_id`, autorização canônica) por entidade persistida.
3. Localizações candidatas consultam `EV-LOC` sem forçar magia.
4. Variantes consultam IDs `EV-ARC-MAN-*`, suas evidências e o vínculo arcano realmente existente.
5. Backend instancia e salva ID persistente, estado, descoberta, possíveis variações. Retornar estados `candidato`, `pendente`, `confirmado` ou `incompativel` conforme dados conhecidos.
6. Nenhum efeito de mana, magia, XP, loot, geração física, raça, planta, minério, teleporte ou monstro pode surgir somente desta taxonomia.

## Limitações honestas

Validação feita em JSON, preservação de registros, distribuição de enums, vínculos internos e casos conceituais; **não testou o código do World Genesis nem uma rede de Ley Lines real**. As fontes anômalas existentes foram preservadas e devem ser confirmadas por instância/cânone específico na integração. As manifestações são ideias de experiência, não receitas fechadas nem limites às descobertas.
