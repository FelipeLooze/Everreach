# WGS2.3 — microhabitats e integração com Vg2

> A auditoria WGS2.3.1, registrada ao final deste documento, identificou uma dependência de ordem no perfil V3. A correção está disponível somente no novo perfil V4; as observações históricas da WGS2.3 abaixo continuam válidas para a execução que as produziu.

## Decisões e escopo

WGS2.3 opta por um perfil de campanha explícito, `world_genesis_ap1_tp1_wgs2_v3`. O perfil mantém AP1, TP1, o seletor WGS2 v2, a cobertura WGS2_COVERAGE_V2 e os contratos E1/Vg2/R1/GA1/GA2. Só campanhas novas que escolham esse perfil recebem o contrato de microambiente e a busca limitada por origens ainda não preparadas. WGS1 e WGS2 v1/v2 conservam seus perfis e seus resultados.

O Vg2 conserva o espaçamento físico de patch de 1.000 m usado pelo perfil V2. Assim, fora de um contexto local ativo, a configuração de amostragem e as regras de Vg2 permanecem iguais; o perfil novo apenas permite que o contexto resolvido seja passado ao sampler.

Não foi necessária migração de banco. O contrato imutável fica em `GenesisNaturalFormation.data.microenvironment`; comunidades e indivíduos Vg2 guardam o snapshot ambiental sob o qual foram materializados. Uma formação não repõe nem recalcula comunidades ou indivíduos já persistidos. Novos pontos e nascimentos usam o contexto local disponível no momento da materialização.

## Cobertura WGS2.2.1: origem ainda não preparada

A auditoria confirmou que a busca original só encontrava instâncias com cobertura já persistida. Assim, visitar B antes de preparar a origem A podia omitir uma formação que cobre B.

No perfil V3, a busca procura endereços candidatos dentro de 6.800 m, calcula o seletor e a extensão determinística de cada candidato, e só prepara uma origem quando a pegada esférica calculada realmente contém B. O índice existente continua limitado pelo contrato de oito saltos; o algoritmo não varre o planeta nem prepara todos os candidatos próximos. A instância mantém a chave canônica derivada de versão, seed, endereço de origem e arquétipo. Os acessos seguem no grafo `Location`/`LocationConnection` existente.

Um teste real do materializador executa A→B e B→A, com A inicialmente não preparado. As duas ordens produzem a mesma instância, chave, conjunto de cobertura e acesso em B. A busca não prepara o sítio TP1 A; ela persiste a formação e a evidência ambiental necessárias para reconhecer sua cobertura.

## Contrato ambiental

Versão: `WGS2_MICROENVIRONMENT_V1`. Busca de origem: `WGS2_ORIGIN_LOOKUP_R1`.

O contrato registra a instância e chave canônica da formação, arquétipo do catálogo v24, assinatura e checksum do snapshot E1, altura e declividade T1, condição terrestre H1, checksum JR1, habitat E1 elegível, índice regional P/PET, variação procedural de abrigo, geometria esférica de influência, modificadores autorizados, estado ativo/neutro e assinatura íntegra.

A forma suportada nesta etapa é EV-LOC-0236, depressão sombreada. O modificador ativo exige cumulativamente terra confirmada, campos T1/JR1 disponíveis, habitat E1 `EV-BIO-SEMIARIDO_ARBUSTIVO` e `grau_abrigado` conhecido. Sem qualquer requisito, o registro é neutro e explicita o motivo. A área de influência é centrada na formação, com raio de um terço do vão horizontal, e queda linear geodésica até zero. A cobertura física multissetorial continua sendo a da WGS2; não se criam cópias ambientais independentes por célula.

A sombra só altera uma cópia dos fatos usada pelo Vg2: aplica um proxy local e limitado de redução de PET ao índice P/PET. E1, temperatura, chuva, assinatura climática, W1, H1 e estoques regionais permanecem intactos. Uma redução quantizada em zero segue exatamente a avaliação regional. O modelo é um modificador de elegibilidade, não um cálculo de insolação ou balanço de água. Fontes hídricas não são criadas: EV-LOC-0068 e outros arquétipos sem evidência local hídrica não recebem umidade.

## Integração ecológica e observação

`VegetationSamplerV2` recebe o contexto local apenas no perfil V3. O sampler aplica a cópia antes dos filtros existentes de habitat e elegibilidade; não altera catálogo, espécies, pesos globais, teto de cobertura, E1 ou o estoque de plantas. Fora da influência, o sampler recebe `None` e preserva o caminho Vg2 regional. A resolução consulta apenas formações indexadas pela célula TP1 atual, valida identidade/assinatura e calcula a distância esférica.

O contexto acompanha snapshots de comunidade e indivíduo e é utilizado pelos caminhos existentes de elegibilidade, estabelecimento e ciclo de vida. Snapshots mais antigos permanecem congelados se uma formação for descoberta depois; visitas não regeneram indivíduos nem repõem cobertura. R1, GA1 e GA2 continuam sendo as autoridades de recursos e ciclo de vida.

EV-FL-1506 (`Tília da Cinza Clara`) foi usada como espécie existente para provar a transição controlada: com todos os demais fatos ambientais válidos e P/PET regional em 0,14, a regra de árvore do Vg1/Vg2 a torna incompatível abaixo de 0,15. O modificador alto documentado pelo contrato eleva o índice local estimado para aproximadamente 0,1591 e a espécie fica elegível. O teste usa uma fixture ambiental determinística, explicitamente marcada como controlada; não afirma que essa espécie surgiu organicamente no playtest.

A observação pública acrescenta somente “Sombra local: uma depressão protegida reduz a exposição solar” quando o modificador pode ser percebido. Espécies, estoque, coordenadas físicas e fatos subterrâneos não são revelados por esse texto. Plantas descritas continuam sendo apenas indivíduos Vg2 efetivamente estabelecidos.

## Playtest HTTP isolado

Executado com Uvicorn real, LLMs desativadas e SQLite temporário. O script reproduzível é `backend/scripts/playtest_wgs2_microhabitats_http.py`; métricas e resultados estão em `artifacts/wgs2-microhabitats/playtest.json`. A fixture escolheu EV-LOC-0236 somente após encontrar habitat semiarido e evidência E1/T1/JR1 reais; a escolha controlada do arquétipo e da variação existe só no processo de teste.

Resultados da execução final (seed 42):

- Perfil V3 iniciado em 18,802 s.
- EV-LOC-0236 ativo, vão horizontal 1.870 m, cinco células de cobertura, mesma formação acessada em ambas as células.
- Caminhada até a segunda célula/preparação: 1,396 s; acesso local: 0,916 s; reinspeção após reinício: 1,793 s.
- Contexto microambiental resolvido em 0,000161 s; consulta da comunidade Vg2 em 0,201390 s.
- Comunidade persistida e estabelecida; dominante: EV-FL-1989. Um indivíduo EV-FL-1989 foi materializado, permaneceu vivo e conservou a assinatura microambiental após reinício. Isso demonstra persistência do indivíduo, não causalidade da espécie pelo modificador.
- Amostra Vg2 no ponto local: P/PET 0,24975; amostra fora, a 5 km: 0,21978 e nenhum contexto local. Os pontos usam suas próprias amostras E1; portanto, essa diferença inclui variação regional além do efeito local.
- EV-FL-1506 ficou elegível nos dois pontos do playtest real. A mudança de status é demonstrada pelo teste controlado anterior, não pelo playtest.
- Assinatura, endereço, identidade, acessos, descoberta e inspeção persistiram após reinício. O mapa não expôs coordenadas desconhecidas. A limpeza explícita da campanha de teste removeu a formação e suas cinco linhas de cobertura.

Os tempos são medições pontuais deste percurso, não uma comparação A/B com WGS2 v2 nem uma afirmação de redução de latência. O custo de inicialização observado não foi atribuído ao WGS2.3.

## Persistência e pontos corrigidos

O playtest revelou e corrigiu três defeitos que testes unitários menores não cobriam:

1. A gravação final do payload da formação sobrescrevia o contrato recém-adicionado. O contrato agora permanece no payload persistido final.
2. A divisão inteira aplicada a uma distância float produzia peso float. O peso de queda é quantizado para inteiro; uma contribuição que arredonde a zero segue o caminho regional sem erro.
3. Acesso WGS2 visitável podia não ter snapshot E1 no raio exato. No perfil V3, a criação do acesso materializa E1 para aquele ponto visitado, permitindo observação após reinício; perfis antigos não mudam.

Comunidades ou indivíduos materializados antes da formação não são invalidados nem refeitos quando o contexto local passa a existir. Mantêm o snapshot original. Pontos ainda não materializados usam o contrato atual. Não há migração nem alteração de campanha antiga.

## Validação

- 137 testes de regressão WGS2/Vg2, persistência, calibração, GA1 e GA2: aprovados em 279,24 s; um aviso de depreciação do `Starlette TestClient`/httpx. Na configuração final, 14 testes WGS2/microhabitat foram repetidos e passaram em 1,23 s.
- Playtest WGS2.3 com Uvicorn e SQLite temporário: aprovado, incluindo criação, início, exploração, observação, consulta dentro/fora da influência e retomada após reinício.
- O primeiro smoke revelou os defeitos listados acima; o smoke final passou depois das correções.
- Nenhuma migração foi executada no banco principal, e a API de teste confirmou o uso de um banco temporário.

## Limitações e próximos passos

Somente a sombra da depressão EV-LOC-0236 está ativa. Abrigo de vento, umidade, drenagem, sombra de outras formações, fontes de água e microhabitats extremos aguardam evidências e contratos físicos próprios. O proxy de PET é deliberadamente simples e local; não representa fluxo de radiação ou alteração de temperatura/chuva. O teste controlado comprova a regra de elegibilidade, mas o playtest orgânico observado não teve diferença de status para EV-FL-1506 e não atribui causalmente a comunidade à formação.

WGS2.3 oferece uma primeira integração persistente e observável com Vg2, sem iniciar uma simulação ecológica nova. O próximo passo é expandir apenas os modificadores sustentados pelos dados e autoridades correspondentes, mantendo cada nova autoridade versionada e sem converter saves automaticamente.

## WGS2.3.1 — consistência ecológica

### Diagnóstico e versão

Havia dependência de ordem no perfil `world_genesis_ap1_tp1_wgs2_v3`. O resolver V1 consultava somente linhas de cobertura de formações já persistidas. A preparação TP1 chamava a busca R1 antes da comunidade, mas uma materialização vegetal direta — inclusive a procura inicial de chegada, antes de existir `playable_state` — podia salvar a comunidade sem o modificador. A descoberta pelo personagem não é uma autoridade física. O snapshot anterior permanece válido como registro de como aquela campanha V3 foi gerada e não é reinterpretado.

O perfil opt-in `world_genesis_ap1_tp1_wgs2_v4` usa `regional_canopy_wgs2_canonical_v1` e fixa `WGS2_CANONICAL_MICRO_R1`. A assinatura ambiental local `WGS2_LOCAL_ENVIRONMENT_R1` inclui o ponto E1 e o contexto efetivo, inclusive a queda espacial, para distinguir consultas sob a mesma formação em distâncias diferentes. AP1, E1, Vg2, R1, GA1, GA2, catálogo e WGS2 v2 continuam sendo as autoridades usadas; não há migração automática.

Antes da primeira comunidade ou indivíduo, o novo resolver calcula candidatos EV-LOC-0236 pelo seletor WGS2 v2, endereço e seed, restringe a busca à célula física e sua vizinhança, calcula o alcance esférico exato e avalia a mesma evidência E1/T1/H1/JR1 e os mesmos parâmetros usados pela materialização. Uma prévia não cria `Location`, decisão, formação, descoberta, comunidade ou indivíduo. A materialização posterior usa a mesma geometria, variação, ponto canônico e decisão; o resolver recusa um contrato ou decisão persistida divergente. Alterações E1/T1/JR1/J1 existentes exigem reconciliação, sem regravar snapshots anteriores.

No perfil V4, a origem física da formação é o centro canônico da célula TP1, inclusive na célula de chegada. Isso permite resolvê-la durante o bootstrap, antes de conhecer o ponto inicial escolhido pelo jogador. Se a âncora real de chegada estiver deslocada desse centro, a rota até a formação registra a distância geodésica real. As consultas de vizinhança dos ciclos L1/L2/GA2 usam a mesma prévia canônica ou o snapshot vegetal já persistido. O sampler V4 exige uma decisão local explícita, inclusive `None`, para evitar uma chamada que omita acidentalmente a resolução física.

O percurso de teste entre faces também expôs que a busca histórica de 6.800 m de diâmetro pode atingir o limite de oito saltos numa emenda, embora o vão WGS2 máximo seja 3.400 m. No V4, como a origem e o índice de cobertura usam centros canônicos, os únicos candidatos que podem cobrir a célula estão a até 1.700 m de seu centro. A busca usa esse limite e verifica a pegada de cada candidato. V3 mantém sua busca histórica.

### Prova de ordem e causalidade no mesmo ponto

O teste `test_genesis_wgs2_canonical_ecology.py` usa dois bancos SQLite isolados, com a mesma seed 42, perfil, identificador de campanha de teste, ponto e instante. A fixture força apenas o candidato EV-LOC-0236 e suas variações de escala/abrigo; os fatos E1/T1/H1/JR1 são os dados reais da seed. A origem A está na face 2, nível 17, célula `(131071, 70000)`; a comunidade B está na face 1, célula `(0, 70000)`, a aproximadamente 485,5 m do centro de A.

Preparar A primeiro ou materializar B primeiro produziu valores idênticos:

- Chave canônica: `949302c047164ac8e50a8f5f0f88a86d0e08a6db1c15acde8350a560e1512d68`.
- Assinatura do contrato: `b127d4ef8ea168cbb6eca4e43383cf84cc510324cf948efce976a0de7dc165ca`.
- Assinatura ambiental local: `8f3719641a07f4152a6c9a4190c4ca32b62656b2a9ec4ef9175f75cbf0515f7c`.
- Checksum da comunidade inicial: `f72c586cf5870a302ffbe20bc6647b2ec1a417ee4b29e6d77f4d8f284599b103`.
- Indivíduo EV-FL-2222 `vgi:35ebafee3b2d1fa6dea4457efdd2d4b8`, com checksum de baseline `4b942e2704313437dce0a3534179afe3b8b06ce92aca8d6f6ced552ace1c3b89`.

Na ordem B→A, a comunidade e o indivíduo foram criados quando não havia linha de formação, acesso nem descoberta; a busca real de cobertura a partir de B materializou a origem física de A e confirmou a assinatura prevista, sem preparar a célula TP1 A. O teste também resolveu o mesmo ponto antes da criação do descritor TP1. Uma remoção R1 real, seguida de quatro dias no relógio do mundo, processamento GA2 e reinício, preservou a morte do indivíduo e o snapshot da comunidade. Isso é uma alteração temporal explícita; não é uma diferença inicial causada pela ordem.

No mesmo ponto B e com os mesmos dados regionais, o alcance da sombra produziu redução de exposição de 66.208 ppm e alterou o proxy local P/PET de **0,336488 para 0,345642**. A prévia Vg2 passou de 51,636% para 52,2256% de cobertura, com 12 populações em cada avaliação. EV-FL-1506 estava elegível nas duas avaliações reais. Em fixture separada com P/PET regional 0,14 e os demais fatos válidos, a sombra alta eleva o proxy para aproximadamente 0,1591 e muda EV-FL-1506 de incompatível para elegível. Temperatura, precipitação e estoques hídricos permanecem iguais; nenhum dos resultados afirma que essa espécie se estabeleceu organicamente.

### Custo e proteção de estado

Na mesma formação persistida, ponto e sessão aquecida, dez consultas tiveram medianas de 0,063 ms para o índice de cobertura V3 e 10,962 ms para a resolução canônica V4 com validação das autoridades físicas: acréscimo observado de aproximadamente 10,899 ms nesse caso. Com a reutilização de fonte validada simulada no lote ecológico já protegido pelo writer fence, a mediana foi 0,017 ms após o primeiro acesso. São medições locais, não um benchmark planetário nem uma estimativa de todas as campanhas. As listas geométricas são limitadas a 128 células por sessão e as fontes a 128 por lote; os dados de fonte não atravessam lotes ecológicos. H1/C3/W1/W2 não são reconstruídos para cada ponto.

A busca usa o limite de oito saltos da cobertura WGS2 e falha explicitamente se uma configuração futura extrapolar esse limite. Fora do raio ou quando a contribuição arredonda para zero, a avaliação é a regional. O texto público do perfil V4 pode informar sombra observável sem nomear a formação não descoberta; a consulta física não abre rotas nem adiciona descobertas.

### Validação final

- **78 testes direcionados** passaram em 75,22 s: ordem e persistência canônicas, WGS2 anterior, microambientes, topologia, Vg2, coleta R1 e cenários selecionados GA1/GA2. O único aviso foi a depreciação do `Starlette TestClient`/httpx. Outros sete testes da tela de criação de campanha passaram; o Vitest informou atraso ao encerrar, com código de saída zero.
- Um smoke com Uvicorn, LLMs desativadas e SQLite temporário criou e iniciou o perfil V4, consultou plantas, percorreu uma conexão TP1, reiniciou a API e confirmou posição e mapa. Início: 18,417 s; movimento: 1,273 s. O mapa não expôs campos de coordenadas desconhecidas. Dados: `artifacts/wgs2-3-1/smoke.json`; script: `backend/scripts/playtest_wgs2_canonical_http.py`.
- O teste de isolamento usa bancos separados e também duas campanhas distintas na mesma sessão; IDs de instância e assinaturas permanecem específicos de cada campanha. A prova cobre emenda entre faces, contribuição zero, ponto fora do raio, ausência de descoberta, rejeição de decisão adulterada e bloqueio de alterações E1 não reconciliadas.

Continua ativo somente o microambiente de sombra EV-LOC-0236. O proxy é uma aproximação de elegibilidade, não um saldo de água ou modelo de insolação. A influência é avaliada pela distância exata, enquanto o índice WGS2 de acessos continua classificando cobertura pelo centro das células; perto de uma borda, a influência pode existir sem que essa célula ofereça automaticamente um acesso à formação. As medições de desempenho são pontuais; o custo de consultas frequentes fora do lote ecológico permanece maior que o índice de cobertura V3. Perfis V3 já iniciados conservam sua limitação histórica e não recebem a nova interpretação automaticamente.
