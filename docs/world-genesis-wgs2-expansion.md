# World Genesis WGS2: expansao de lugares naturais

## Estado

WGS2 v1 e uma implementacao experimental parcial e opt-in. Ela amplia a selecao de formacoes naturais locais, reutilizando o contrato de persistencia, o grafo de `LocationConnection` e os sistemas existentes de descoberta e viagem. Nao esta pronta para ser considerada fechamento da fase: a cobertura continua limitada a uma celula e nao ha contrato de micro-habitat para alterar Vg2.

## Catalogo e selecao

- Perfil: `world_genesis_ap1_tp1_wgs2_v1`; namespace persistido novo: `wgs2_`.
- Mantem as cinco selecoes-base WGS1 e acrescenta 15 candidatos do catalogo v24, agrupados em paisagens abertas, relevo rochoso, cavidades naturais, paisagens aridas e refugios naturais.
- A escolha e deterministica e ponderada pelos pesos relativos do catalogo em duas etapas: chance por celula elegivel, familia e, em seguida, arquetipo. Nao fixa quantidades globais.
- Treze dos novos candidatos possuem adaptadores com evidencias reconhecidas. `EV-LOC-0049` aguarda confirmacao local de umidade; `EV-LOC-0225` requer confirmacao E1 de ambos os habitats de ecotono. Sem evidencias, sao rejeitados com razao persistida, nao materializados.
- `EV-LOC-0017` e `EV-LOC-0179` permanecem catalogados como pendentes, fora da selecao: falta evidencia de vegetacao. Conteudo de anomalia ausente nao e inventado.
- Persistencia reutiliza `GenesisFormationCandidate`, `GenesisNaturalFormation`, `Location` e `LocationConnection`; nenhum esquema novo ou migracao de save foi necessario. WGS1 permanece selecionado pelo contrato anterior e nao compartilha os novos IDs.

Os estados sao distintos: catalogado nao significa suportado; suportado nao significa elegivel no contexto; elegivel nao significa materializado; materializado nao significa descoberto ou exploravel.

## Cobertura e evidencias

`WGS2_COVERAGE_V1` esta deliberadamente limitado a uma celula e a uma envoltoria maxima de 700 m. Ha dimensoes/orientacao deterministicas e acesso local persistente, mas nao uma cobertura fisica que atravesse setores ou faces, nem propriedade/deduplicacao de footprints sobrepostos. Portanto, nao afirmar continuidade multissetorial de uma formacao.

E1/T1 continuam sendo as fontes de evidencia aceitas. Este passo nao cria um overlay local para Vg2: uma formacao natural nao muda cobertura vegetal ou micro-habitat. A cavidade tem entrada/saida no grafo existente e inspecao de interior, mas nao introduz ambiente subterraneo autoritativo, fontes hidricas ou conteudo biologico.

## Playtest real

O harness `backend/scripts/playtest_wgs2_v1.py` executou o perfil por HTTP em Uvicorn, com LLM desativado e SQLite temporario. O banco principal foi verificado como inalterado.

| Seed | Inicio AP1 | Territorio novo | Candidatos avaliados | Resultado |
|---|---:|---:|---:|---|
| 42 | 80,557 s | 5,181 km | 0 | Nenhuma oportunidade nesta amostra; sem vazamento de coordenadas ocultas. |
| 7 | 48,828 s | 5,209 km | 3 | `EV-LOC-0050` (compatibilidade/base) materializado, descoberto, inspecionado e visitado; duas rejeicoes por evidencias insuficientes. Retorno e persistencia apos reinicio confirmados. |
| 2026 | 57,157 s | 5,093 km | 2 | Novo `EV-LOC-0037` materializado, descoberto, inspecionado e visitado; `EV-LOC-0225` rejeitado pela ausencia de ambos habitats. |

Probe HTTP adicional no SQLite isolado da seed 7 confirmou entrada em `genesis_formation_interior`, inspecao e saida para `genesis_formation` pelo `LocationConnection` existente. Os sinais publicos foram direcionais e nao revelaram coordenadas. Medias observadas de requests: geracao 2,17–4,62 s e viagem 2,64–5,46 s. Inicio de campanha levou 48,8–80,6 s nesses ensaios. Isso e evidencia limitada, nao benchmark de escala ou memoria; a latencia de inicio merece investigacao antes de ampliar materializacao.

Os resultados completos por seed estao em [`artifacts/wgs2-expansion/playtest.json`](../artifacts/wgs2-expansion/playtest.json).

## Validacao executada

- `test_genesis_wgs2_families.py`: 4 testes passaram (determinismo/versionamento, independencia de ordem, familias/catalogo e gates conservadores).
- `test_genesis_local_formations.py`: 14 testes passaram na suite completa, incluindo regressao WGS1. Regressao curta repetida apos os ultimos ajustes: 4 passaram, 10 selecionados foram omitidos.
- `compileall`, `git diff --check` e `npm.cmd run build` passaram.
- Playtest HTTP com tres seeds e probe HTTP de cavidade passaram; a persistencia foi exercitada usando banco isolado.

## Arquivos e integracao

- `backend/app/game/world/genesis/wgs2_families.py`: registro de familias, adaptadores de evidencias e selecao versionada.
- `backend/app/game/world/genesis/local_formations.py`: despacho WGS1/WGS2, candidatos, materializacao deterministica, persistencia e sinais.
- `backend/app/tests/test_genesis_wgs2_families.py`: cobertura especifica WGS2.
- `backend/scripts/playtest_wgs2_v1.py`: ensaio HTTP reproduzivel com SQLite temporario.
- Perfil opt-in aceito nos contratos de campanha/bootstrap, fluxo de acoes, validacao de viagem e interface de criacao/jogo. O grafo de movimento existente foi mantido.
- `artifacts/wgs2-expansion/playtest.json`: resultados sanitizados.

## Limites e proximas etapas

1. Definir contrato de footprints persistentes multi-celula/setor, incluindo deduplicacao e continuidade em emendas, antes de declarar cobertura geografica extensa.
2. Definir como uma formacao fornece evidencia local a Vg2 sem falsificar E1/T1; depois testar seu efeito em habitats e aparencia.
3. Investigar a latencia de bootstrap e medir memoria/custo com cenarios representativos.
4. Aumentar playtests e validacao de familias sem forcar a aparicao de cada ID.

WGS2 permanece opt-in; nao habilitar em campanhas reais por padrao. Nenhum dataset foi alterado e nao foi executada migracao automatica de saves.
