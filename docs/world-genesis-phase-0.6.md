# World Genesis — fase 0.6: balanço hídrico W1

## Auditoria e decisões anteriores à implementação

Revisados V4, H1 (`drainage`, `plan`), HR1 (`regional`, `regional_service`), C1/C2 (`query`, `service`), persistência e reset. H1 oferece área/célula e árvore de drenagem condicionada; HR1 oferece portas e trajetórias amostradas, mas não batimetria ou capacidade dos armazenamentos que suas cotas exigem. C2 fornece precipitação, PET e neve potencial em quatro períodos; PET não é perda efetiva.

| Alternativa | Decisão |
| --- | --- |
| Transformar área contribuinte H1 em vazão | Rejeitada: área não é alimentação hídrica. |
| Rotear toda chuva pela árvore condicionada e chamar de rio | Rejeitada: ignora ET, estoque, depressões e incompatibilidades regionais. |
| Materializar HR1 de todo o planeta | Rejeitada: custo desnecessário e contrário à geração progressiva. |
| Buckets sazonais conservativos e transferências condicionadas a evidências fixadas | Escolhida para W1. |

O plano é independente e versionado, com volumes inteiros em litros (1 mm × 1 m² = 1 L). Reservatórios: neve em equivalente líquido, solo, retenção superficial, coluna de depressão aproximada, água em trânsito e água com localização/rota pendente. Nenhuma dessas contas é uma fonte infinita. Armazenamentos são transportados entre os quatro períodos e entre ciclos climatológicos limitados, sem ticks de água.

As evidências HR1 são um manifesto explícito e limitado, fixado na preparação W1. Novas visitas não podem acrescentar silenciosamente rotas ao plano existente. Uma ligação física modelada exige validação bilateral e ausência de armazenamento regional de capacidade desconhecida. Água bloqueada fica contabilizada como pendência, sem virar automaticamente lago ou desaparecer. Uma coluna aproximada H1 pode indicar armazenamento e excesso potencial, sem fornecer geometria/permanência de lago.

C2 é a fonte padrão explícita do W1; C1 pode ser lido somente mediante configuração opt-in específica, sem conversão do clima antigo. Não foram modificados campos V4/H1/HR1/C1/C2, precipitação ou PET para umedecer o mundo.

## Entrega e domínio físico

W1 implementa uma contabilidade hídrica global conservativa e consultas de trechos regionais respaldados por evidência. **Disponibilidade de escoamento não é declaração de rio físico.** O produto global inclui quantidades locais, estoques, déficits e pendências em todas as células H1; a transferência efetiva modelada só ocorre no subconjunto regional cuja prova foi fixada. Não é um sistema de streaming completo, nem resolve todos os corredores H1 desta fase.

A malha é a H1 existente, no máximo 6.144 células. Áreas vêm do H1 e preservam sua quadratura esférica. A precipitação, PET, neve potencial e temperatura são lidas do contrato C1/C2 no centro de cada célula, usando a altura V4 que o próprio H1 já armazenou nesse raio exato. Não há nova avaliação de relevo, mudança da chuva ou outro gerador geográfico. O domínio é não marinho segundo H1; inclui terreno abaixo do datum desconectado do oceano, sem afirmar a existência de água interior.

O oceano conectado é **condição de saída**, com estágio marítimo prescrito pelo H1. Chuva/evaporação do oceano estão fora desta conta continental e não alimentam rios por si mesmas. A água só entra por precipitação continental e por estoques de ciclos anteriores explicitamente contabilizados. Uma cota acima do fundo marinho já coberta pelo estágio oceânico não exige que W1 encha o oceano; isso não autoriza fluxo reverso ou nascente marinha.

## Hipóteses e parâmetros W1

`WaterConfig` é imutável, estrito e versionado. Os defaults são hipóteses configuráveis de um modelo de RPG, não propriedades deduzidas da gravidade de um planeta gigante.

| Parâmetro | Default | Interpretação |
| --- | ---: | --- |
| `water_version` | 1 | Algoritmo W1; alterações autoritativas futuras exigem versão explícita. |
| `source_climate_version` | 2 | C2 para novos planos; valor 1 exige opt-in para usar C1 existente. |
| `warmup_years` | 2 | Dois ciclos climáticos preparatórios; publica-se o terceiro. Limite: sete preparatórios. |
| `soil_capacity_mm` | 150 | Capacidade uniforme de água acessível no solo, sem dataset pedológico. |
| `surface_capacity_mm` | 10 | Retenção superficial local, não área inundada. |
| `infiltration_mm_per_day` | 8 | Limite de infiltração escalado pela duração do período e pela capacidade livre do solo. |
| `soil_release_ppm_per_day` | 3.000 | Recessão simplificada do estoque de solo para água móvel. Não cria uma nascente. |
| `frozen_soil_factor_ppm` | 100.000 | Reduz infiltração/liberação do solo quando a temperatura média não é positiva. |
| `snow_melt_milli_mm_per_degree_day` | 3.000 | 3 mm por grau-dia positivo, limitado pela neve disponível. |
| `reservoir_wetted_area_ppm` | 100.000 | Área evaporante de referência da coluna, ajustada pelo preenchimento; hipótese incerta, não geometria de lago. |
| `channel_velocity_mm_s` | 1.000 | 1 m/s para escala de residência/transferência, não velocidade hidrodinâmica resolvida. |
| `flow_presence_liters_per_second` | 10 | Limiar de descrição de regime; quantidades menores continuam conservadas e transferidas. |

Os estoques começam secos **antes** dos ciclos preparatórios. O ano é o do clima fixado e cada período dura `[year_days, 4]` dias. O horizonte finito é uma hipótese inicial explícita: não são anos reais passados na campanha e não se avançou `WorldTime`. Não se afirma equilíbrio periódico. Neve persistente ou água pendente podem continuar acumulando; esse crescimento aparece nos estoques finais e no delta anual.

## Cálculo por período

1. A precipitação é separada em neve equivalente e chuva líquida pelo contrato climático existente. Soma-se neve ao estoque e aplica-se degelo por graus-dia positivos, limitado ao que existe. Não há sublimação, densidade de neve, geometria de geleira ou previsão de tempestades.
2. Chuva líquida, degelo e retenção superficial anterior formam a oferta local. Infiltração é limitada por essa oferta, taxa configurada e espaço livre no solo.
3. Evapotranspiração efetiva consome líquido exposto e depois água acessível do solo, sempre limitada por disponibilidade e PET. PET não é subtraída cegamente de um estoque seco.
4. Uma fração de recessão `kΔt/(1+kΔt)` libera água já armazenada no solo. O excesso além da retenção superficial torna-se **escoamento local disponível**. Não há fonte subterrânea infinita ou colocação de novas nascentes.
5. Escoamento local e afluentes recebidos alimentam a coluna de depressão, quando houver. A capacidade de referência é `área_H1 × (cabeça_H1 − altura_V4) × 1.000 L/m³`. Sua evaporação usa apenas a demanda remanescente e a área molhada aproximada, limitada à água existente. Não se duplica PET já consumida pelo solo/superfície.
6. O excesso da coluna é água potencialmente disponível para transferência. Se a rota estiver provada, entra no estoque em trânsito e libera uma fração `D/(D+comprimento)`, com `D = velocidade × duração`. A distância é uma corda curta esférica inteira entre centros H1; não modifica unidades de viagem do jogo. É uma aproximação de residência média por período, não tempo exato de propagação.
7. Se a rota não estiver provada, o volume fica na conta `unresolved`. A ordem de processamento segue a árvore H1 de montante para jusante; cada afluente contribui uma única vez. A passagem ao oceano é registrada como exportação do domínio, nunca como desaparecimento.

Não se aplica ET arbitrária da área de toda uma célula ao rio que a atravessa. Evaporação do canal e infiltração lateral de margem não foram resolvidas por falta de largura/área molhada; a evaporação adicional implementada refere-se à coluna de depressão e continua limitada à demanda remanescente. A discretização em quatro períodos também não resolve enxurradas diárias em regiões cuja chuva média é inferior à demanda.

## Conservação, arredondamento e confluências

Para cada nó/período:

`estoque inicial + precipitação + afluentes = ET efetiva + saída + exportação oceânica + estoque final`

Para o domínio, transferências internas cancelam:

`estoque inicial + precipitação = ET efetiva + exportação oceânica + estoque final`

Todos os volumes são inteiros em litros. Divisões deixam a fração não liberada no estoque; não se zera água pequena para fechar a conta. O resíduo numérico permitido no ledger quantizado é **zero**, verificado por nó, período, bacia potencial H1 e ano publicado. A área amostrada, o clima em mm e as hipóteses de reservatório são aproximações físicas: resíduo aritmético zero não significa precisão geofísica exata.

`local_runoff`, `incoming` e `outflow` são transferências internas, não novas entradas globais. Não se pode somar escoamento local à precipitação como se fossem fontes diferentes. Nos trechos HR1 compartilhados antes de uma confluência, contribuições de entradas diferentes são combinadas uma vez por segmento. A vazão de saída usa o volume efetivamente liberado após estoques/perdas. Repetir um recorte de mapa não duplica esse volume.

Volumes JSON podem exceder 2^53, sobretudo nos raios extremos. Os cálculos/persistência Python conservam inteiros; consumidores futuros devem usar leitura sem perda de precisão, sem converter esses números silenciosamente para `Number` JavaScript. Vazões de consulta são razões exatas em m³/s; floats são usados apenas na apresentação técnica.

## Evidência HR1 e rios alimentados

O manifesto fixa até **32 regiões HR1 explicitamente escolhidas**, ordenadas por endereço e checksum. O limite é de orçamento, não de conteúdo do planeta. Sem manifesto, W1 calcula toda a disponibilidade macro, mas mantém transferências regionais pendentes. Não busca silenciosamente todas as regiões já visitadas para escolher quais rios passam a existir.

Uma ligação é elegível para transportar água quando:

- pertence a um corredor H1 existente;
- os dois lados HR1 estão no manifesto e preservam proveniência/configuração;
- `compare_regional_connection` confirma ambas as metades;
- os perfis não exigem cabeça acima do terreno cuja capacidade de armazenamento seja desconhecida, ressalvado o estágio do oceano conectado.

Incompatibilidade HR1, falta de uma metade, escoamento sobre terreno sem refinamento ou armazenamento regional desconhecido produzem estados separados. W1 não eleva montanhas, corta leitos, inventa atalhos nem descarrega água por uma rota alternativa. A conta `unresolved` conserva o volume associado à pendência, **mas não é um lago mapeado, inundação ou água imediatamente utilizável**. Sua futura alocação poderá exigir posição, capacidade e perdas adicionais explicitamente contabilizadas.

As classes usam os quatro períodos publicados: zero transferência (`potentially_dry`), um período acima do limiar (`temporary`), dois/três (`seasonal`) e quatro (`regularly_supplied_in_model_window`). Traços inferiores ao limiar são identificados separadamente sem apagar volumes. Alimentação regular **não equivale a perenidade comprovada**; `perennial` e `river_bed_geometry_final` continuam indeterminada/falso, respectivamente.

Um trecho pode ter água modelada sem que o reach H1 inteiro esteja validado. A consulta identifica separadamente continuidade geométrica do reach completo. Não se declara um grande rio físico contínuo com base num único segmento aprovado. A transferência também não possui limite hidráulico de seção/condutância calculado: `conveyance_capacity_validated=False` explicita a hipótese de transporte agregado sem esse limite. T1 deverá verificar capacidade física do leito e possíveis transbordamentos; a vazão W1 representa alimentação modelada sob essa hipótese.

### Limite deliberado da progressão W1

As consultas regionais não precisam gerar o planeta inteiro e preservam os resultados já preparados. Entretanto, **W1 não implementa atualização incremental de sua autoridade hidráulica ao descobrir novas provas**. Acrescentar regiões HR1 não modifica um manifesto existente. Uma futura revisão/overlay deverá reconciliar os estoques pendentes e as condições de fronteira sem resetar ou duplicar água; não basta remover um marcador de pendência durante a exploração.

Essa restrição impede que a ordem de visita decida a distribuição fundamental. A disponibilidade local global permanece consultável em toda a superfície; a demonstração de cursos efetivamente transferindo água fica limitada às provas fixadas. É uma fundação conservativa, não cobertura regional completa do planeta.

## Depressões, lagos e armazenamento

As colunas de uma depressão H1 particionam a malha sem sobrepor áreas. Seus volumes podem ser somados como referência contábil do candidato, mas **não formam batimetria conectada**: não há garantia de nível uniforme, contorno, capacidade conjunta ou vertedouro definitivo. Excesso além da referência é marcado como transbordamento potencial; não atravessa um HR1 incompatível ou um armazenamento ainda desconhecido.

Candidatos HR1 são preservados nas respostas regionais com alocação de água desconhecida. Não se atribui o volume inteiro de uma célula a cada pequeno candidato, o que duplicaria água. `lake_permanent`, geometria de lago e área inundada permanecem indeterminadas. A retenção superficial de 10 mm também não é um mapa de pântanos.

Bacias sem receptor não exportam água ao oceano; seus estoques/pendências continuam no ledger. O contexto de terminal bruto H1 é mantido, preservando possibilidades endorreicas em vez de ativar toda saída condicionada. Evaporação, preenchimento e secagem sazonais de um bucket com capacidade declarada funcionam e são testados; a decisão de existência física/permanência de um lago exige a geometria que H1/HR1 ainda não fornecem.

## Persistência e uso interno

Foram acrescentadas `genesis_water_plans` e `genesis_water_sectors`, pela migração aditiva **`m21m4h5i6j7k`**, posterior a `l20l3g4h5i6j`. O plano depende do clima e da configuração HR1; nenhuma linha V4/H1/HR1/C1/C2 é convertida. A exclusão de campanha remove filhos W1 antes dos pais. A migração foi exercitada com chaves estrangeiras, upgrade/runtime/downgrade e preservação byte a byte dos payloads anteriores em banco temporário. **O banco real não foi migrado.**

Pré-requisitos explícitos: mundo V4, H1, HR1 inicializado e clima C2. Exemplo:

```python
from app.game.world.genesis.water.service import (
    initialize_water_balance, get_water_plan, materialize_water_sector,
)

# Configuração e provas escolhidas na preparação; não derivadas de visitas.
initialize_water_balance(db, campaign_id, regional_nodes=[source_node, target_node])
plan = get_water_plan(db, campaign_id)
snapshot = materialize_water_sector(db, campaign_id, sector_key)
# O chamador controla commit/rollback.
```

`regional_nodes` pode ficar vazio para disponibilidade macro com rotas pendentes. Inicializar não cria setores W1 nem materializa outras regiões. Um clima C1 antigo só é aceito com `WaterConfig(source_climate_version=1)` explícito, sem trocar esse clima por C2. Reconfiguração de plano existente ou extensão implícita do manifesto é recusada.

A assinatura W1 fixa H1, clima, HR1, configuração e manifesto. O payload global tem carga adiada e cache imutável de dois planos. Recarga valida conservação e recompila as provas a partir de baselines HR1 salvos, sem executar novamente balanço, relevo ou roteamento regional. Consultas verificam cabeçalhos e eventos HR1 ainda pendentes na Session, inclusive com autoflush desativado. Uma alteração de evidência exige overlay/revisão explícita, nunca regeneração silenciosa.

Snapshots têm `baseline` e `changes` separados. Ao retornar, os dados salvos e eventos são preservados. W1 não implementa os efeitos físicos de futuros eventos de barragem, incisão ou clima alterado; conserva os registros e recusa provas HR1 modificadas como se ainda fossem baselines válidos. JSON deve ser substituído por novo dicionário para persistir alterações pelo ORM, como nas camadas anteriores.

As consultas de setor recortam apenas geometria HR1 já fixada e devolvem os volumes macro e throughput por trecho. Volumes extensivos não são interpolados como se fossem profundidade pontual. IDs e quantidades de fronteira são os mesmos nos dois lados, inclusive em faces e setores de nível 24. Peças repetidas são vistas do mesmo fluxo, não reservatórios independentes. Nenhum mapa público, descoberta, conexão de movimento ou unidade de viagem foi modificado.

## Amostras e métricas C2/W1

Foram gerados seis casos com H1 no nível 5, C2 no nível 5 e W1 padrão. O modo técnico escolheu até 32 regiões testemunhas favorecendo oferta de escoamento e emendas, para buscar exemplos verificáveis. **Isso não é uma seleção de nascentes para gameplay nem um censo dos rios do mundo.** Cada manifesto foi exportado e permanece fixado; a estatística global de disponibilidade inclui todas as células, não apenas as testemunhas.

Médias sobre terra acima do datum, ponderadas por área H1. P/PET são amostras C2 nos centros H1; diferem das médias por vértice da auditoria climática anterior por quadratura e classificação espacial, sem alteração de chuva.

| Seed | Raio (km) | P (mm/ano) | PET (mm/ano) | ET efetiva (mm/ano) | Escoamento local disponível (mm/ano) | Terra sem escoamento local no ano |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 0 | 63.710 | 148,44 | 730,27 | 119,05 | 21,16 | 90,18% |
| 42 | 63.710 | 157,51 | 691,00 | 127,76 | 19,45 | 90,65% |
| 2026 | 63.710 | 207,83 | 657,93 | 162,51 | 26,03 | 88,98% |
| 42 | 6.371 | 63,37 | 681,69 | 53,01 | 4,32 | 97,93% |
| 42 | 637.100 | 178,29 | 763,12 | 147,21 | 20,08 | 88,70% |
| 42 | 1.000.000.000 | 178,29 | 763,12 | 147,21 | 20,08 | 88,70% |

A aridez C2 não foi compensada com chuva, vazão fixa ou nascentes. Na seed 42 de referência, a área terrestre apresenta oferta local temporária em **4,91%**, sazonal em **2,15%**, regular na janela em **2,29%** e nula em **90,65%**. Isso classifica oferta macro, não rios físicos ou biomas. Existem neve persistente, liberação por degelo, estoque em solo/superfície e colunas com água; não há percentual de ambientes imposto.

No conjunto de provas preparado, houve 1 trecho alimentado na seed 42 de referência e 8 no caso da mesma seed com raio de 6.371 km. Os outros quatro conjuntos não demonstraram transferência física aprovada em suas testemunhas. **Zero nesse conjunto não significa zero rios no planeta.** Na referência, 10 saídas ficaram pendentes de capacidade regional, 5 incompatíveis e a maioria das demais não teve os dois lados preparados; não foram ativadas artificialmente.

O trecho demonstrado da referência é o nó H1 **3982**. No período 1, P local é 93 mm e escoamento local chega a 421 mm por **degelo/estoques anteriores**, não criação de água. A residência em canal mantém alimentação nos outros períodos. Sua geometria continua amostrada, sem largura/leito T1 definitivo. O destino seguinte não validado mantém a água em pendência; por isso essa demonstração não declara exportação contínua até o oceano.

Na referência há 33 grupos candidatos H1 com estoque positivo em pelo menos um período, **não 33 lagos confirmados**. Nenhuma permanência de lago foi declarada. O resumo fornece todas as colunas e bacias com suas contas; os resíduos anual, por período e por bacia foram zero em todos os seis casos.

## Ferramenta técnica e desempenho

A partir de `backend`:

```powershell
.\.venv\Scripts\python.exe -m scripts.preview_water --suite --prepare-examples --export-plans --measure-memory --output ../artifacts/water-w1
```

Sem `--prepare-examples`, a preparação é global sem provas regionais implícitas. O modo de exemplos é offline e não abre banco. Ele reutiliza os planos V4/H1/C2 exportados, quando presentes, ou os reproduz explicitamente. Não altera saves nem o mapa do jogador.

Artefatos:

- [Comparação dos seis mundos e contas por bacia](../artifacts/water-w1/comparison.json).
- [Disponibilidade/estoques/sazonalidade da seed 42](../artifacts/water-w1/seed-42-r63710000/water.png).
- [Bacias e drenagem](../artifacts/water-w1/seed-42-r63710000/basins.png).
- [Trecho HR1 alimentado e seus quatro períodos](../artifacts/water-w1/seed-42-r63710000/regional-water.png).
- [Neve em equivalente líquido](../artifacts/water-w1/seed-42-r63710000/snow_storage.png) e [conta de pendências](../artifacts/water-w1/seed-42-r63710000/pending_accounting.png).

As pastas contêm também o plano W1 e as provas HR1. Azul nos estoques é profundidade macro equivalente, não contorno de lago ou inundação. Linhas globais são representantes H1; ciano identifica uma ligação alimentada respaldada por HR1, cinza indica pendência, laranja armazenamento desconhecido e vermelho incompatibilidade. A imagem regional usa os segmentos HR1 efetivos da prova.

Preparo W1: aproximadamente **1,48–1,55 s**, excluindo V4/H1/C2 preexistentes. Na referência, o conjunto opcional de testemunhas levou ~4,95 s, incluindo uma passagem W1 preliminar para selecionar disponibilidade e o preparo HR1 dessas regiões. Esse custo não ocorre a cada visita. O horizonte é limitado a oito ciclos × quatro períodos × até 6.144 nós; só os quatro períodos finais e estoques iniciais correspondentes são persistidos.

Na referência, o payload compacto tem **2.099.764 bytes (~2,10 MB)**, recarga JSON/validação ~**109 ms**, e consulta de nó em memória mediana ~**0,010 ms**. Essas consultas excluem ORM/cabeçalhos; a leitura fria de serviço também verifica as provas HR1. O pico instrumentado do preparo foi **11.133.665 bytes (~10,62 MiB)**, retenção ~7,50 MB, excluindo fontes/provas preexistentes, imagens e ORM. Não é RSS. A instrumentação foi executada separadamente dos tempos normais.

## Arquivos desta fase

| Arquivo | Entrega |
| --- | --- |
| `backend/app/game/world/genesis/water/config.py` | Configuração W1 e limites explícitos. |
| `.../water/balance.py` | Buckets, neve/degelo, ET limitada, residência, transferências e verificação de conservação. |
| `.../water/plan.py` | Manifesto/provas, forçamento climático, plano imutável e recarga sem solver. |
| `.../water/query.py` | Regimes, quantidades macro, fronteiras, segmentos e candidatos indeterminados. |
| `.../water/service.py`, `__init__.py` | Opt-in, persistência, eventos/proveniência e cache limitado. |
| `.../water/preview.py` | Métricas por bacia e imagens globais/regionais. |
| `backend/app/db/models/world_water.py`, `models/__init__.py` | Plano e snapshots W1 registrados no ORM. |
| `backend/app/game/world/reset.py` | Exclusão na ordem das duas dependências de W1. |
| `backend/alembic/versions/m21m4h5i6j7k_add_water_w1.py` | Migração aditiva sem mudança dos dados anteriores. |
| `backend/app/tests/test_genesis_water.py`, `test_genesis_water_persistence.py` | Núcleo, continuidade, fontes, recursos, persistência e compatibilidade. |
| `backend/scripts/preview_water.py` | Amostras multi-seed/raio, provas técnicas, exportações e benchmarks. |
| `docs/world-genesis-phase-0.6.md`, `artifacts/water-w1/` | Decisões, resultados, planos, provas e imagens. |

As alterações das fases anteriores já presentes no workspace foram preservadas. Não foram implementados T1, datasets, flora, fauna, ambientes, assentamentos, expedições, NPCs, monstros ou novos sistemas de movimentação.

## Testes e verificação

**503 testes selecionados passaram em 196,44 s: 469 anteriores e 34 casos W1.** Depois, verificações dirigidas também cobriram a guarda de endereços de manifesto e o metadado de área macro. Não foi executada a suíte completa do backend/frontend. Permanece apenas o aviso preexistente Starlette/httpx.

Casos W1: confluência sem duplicação; oceano somente como saída; ET limitada por água/PET; infiltração/retenção e ET posterior; neve/degelo; preenchimento, excesso e secagem de bucket; bacia fechada; pendência preservada entre anos; residência com arredondamento conservado; regimes sem apagar traços; configurações inválidas; fontes anteriores intactas; roundtrip sem solver; cache imutável; ordem do manifesto; trechos alimentados com provas controladas; fluxos compartilhados entre faces/setores em níveis 5/13/24; armazenamento HR1 desconhecido bloqueado; estágio oceânico sem fonte infinita; C1 somente por opt-in; corrupção/ciclos; hash W1 congelado e processos com `PYTHONHASHSEED` diferente; múltiplos raios até 10¹² m; orçamento de memória; métricas/figuras; opt-in sem materialização distante; snapshots/eventos conservados; coluna global adiada; exploração sem extensão de prova; eventos não flushados detectados; cabeçalhos/checksums; rollback; exclusão por campanha; upgrade/runtime/downgrade com os pais preservados.

A seleção de regressão inclui `test_genesis*.py`, `test_map*.py`, `test_travel*.py`, `test_world_gen*.py`, `test_regional_boundaries.py`, `test_cross_region_routes.py`, `test_explor*.py`, `test_campaign_reset.py`, `test_region_skeleton.py`, `test_neighbor_region_materialization.py`, `test_world_simulation_integration.py`, `test_simulation_scope.py` e `test_world_time*.py`.

Também passaram `compileall`, `git diff --check` e a conferência da cabeça única Alembic `m21m4h5i6j7k`. Os seis planos/provas exportados foram recarregados e conferidos sem recalcular o balanço. Os resíduos por bacia e período foram verificados e as imagens globais/regionais inspecionadas. Nenhuma migração foi aplicada ao banco real.

## Limitações e próximas etapas

W1 produz variedade macro de oferta temporária, sazonal, regular na janela, regiões secas e armazenamento/neve. **Isso é suficiente para orientar T1, não para certificar a distribuição de todos os ambientes planejados.** A área sem escoamento local permanece grande e não foi compensada artificialmente. Os seis casos não são validação de todos os presets possíveis nem uma meta ecológica de cobertura.

Limites materiais: clima macro e quatro períodos; inicialização seca com ciclos finitos, sem equilíbrio garantido; solo uniforme; ausência de aquíferos, sublimação, tempestades e infiltração de margens; área evaporante/capacidade de depressão aproximadas; pendências sem localização/perdas totalmente resolvidas; prova física apenas no subconjunto HR1 fixado. Correntes/cotas de água, largura, batimetria e inundação local não foram inventadas.

**Podemos avançar para T1.** Ele deve fornecer uma fonte única e versionada de altitude local, leitos e capacidade/hypsometria/vertedouros, além de condições comuns nas emendas. Em seguida será necessário reconciliar as provas e os volumes W1 pendentes mediante uma revisão/overlay explícito, sem descartar estoques ou reescrever territórios modificados. Só depois desse fechamento local é prudente integrar datasets de ambientes, solos, flora e fauna como consumidores de disponibilidade realmente respaldada. Os contratos macro já estão disponíveis; lagos permanentes, rios perenes e ecossistemas não devem ser inferidos dos candidatos pendentes.
