# World Genesis WGS2.2 — cobertura multissetorial

## Decisões

- A representação continua sendo a cube-sphere TP1 existente. Ela já fornece endereços canônicos nas seis faces, métrica de grande círculo e vizinhança que atravessa emendas. Uma grade de latitude/longitude criaria problemas polares; uma malha geodésica global exigiria trocar os endereços e o território persistido. Não há motivo para essa troca nesta fase.
- WGS2 v1 continua com seu seletor, perfil, geometria de 700 m e formato de save. A nova modalidade tem opt-in explícito `world_genesis_ap1_tp1_wgs2_v2`, versão autoritativa `natural_formations_wgs2_v2` e contrato `WGS2_COVERAGE_V2`. Não há conversão de campanhas existentes.
- A forma horizontal é escolhida deterministicamente dentro do intervalo sugerido pelo registro v24, com teto de 3.400 m nesta versão. A cobertura é a lista esparsa das células TP1 cujos centros ficam dentro de um disco geodésico de raio igual à metade da dimensão. Isso define uma regra reproduzível, embora não pretenda modelar a interseção exata de polígonos de células.
- As células cobertas são persistidas em `genesis_formation_coverage_cells`, com checksum comum da instância e unicidade por campanha, formação e endereço. Só é criado um nó de acesso `Location` quando a célula é preparada. Ele aponta para a formação canônica e liga-se ao exterior por `LocationConnection` com contrato `WGS2_COVERAGE_ACCESS`; deslocamento continua no grafo TP1 já existente.
- Formação, células de cobertura e nós de acesso são coisas distintas. Não são criadas Locations para todas as células na materialização da formação. A cobertura não é enviada no estado público do mapa; uma visita revela somente o acesso local.
- A busca da cobertura é limitada a oito saltos e verifica se a própria fronteira do índice ainda toca a forma. Se o planeta/resolução superar esse limite, a geração falha claramente em vez de persistir uma cobertura truncada.
- A semente do seletor WGS2 v2 é separada por versão. A cobertura não depende de ordem de visita; endereços, dimensões, formas e IDs são funções da seed, versão e célula-origem. Instâncias distintas continuam isoladas por campanha.

## Alternativas consideradas

- **Uma localização por célula coberta:** rejeitada porque duplicaria a identidade da formação e criaria milhares de entidades de gameplay. A versão implementada guarda uma linha esparsa por relação física e cria acesso local apenas sob demanda.
- **Conversão para outra projeção ou troca do TP1:** rejeitada para preservar anchors, setores, rotas e saves. A esfera cube-sphere existente cobre polos e emendas sem coordenadas de longitude persistidas.
- **Varredura global para encontrar todas as interseções:** rejeitada. O gerador consulta somente um conjunto local limitado de células.
- **Resolver sobreposições com um solver de colisão:** não implementado. Coberturas de formas compatíveis podem coexistir. Se várias instâncias cobrem a mesma célula e nenhuma instância foi candidata naquele endereço, o acesso local escolhe a menor chave de formação, de modo determinístico. O catálogo v24 ainda não oferece uma matriz canônica de incompatibilidades.

## Funcionalidades entregues

- Perfil novo WGS2 multissetorial, selecionável na criação de campanha.
- Seleção de dimensões dentro da faixa v24 e até 3.400 m; WGS2 v1 permanece no teto anterior de 700 m.
- Indexação e persistência de cobertura multi-face, inclusive através de emendas, baseada em distância esférica real.
- Reutilização da mesma instância ao preparar outra célula coberta sem candidato local próprio; o novo acesso é materializado sob demanda.
- Acesso local no grafo de conexões existente, validado por checksum, anchors, distância e associação persistida à formação.
- Inspeção da formação canônica a partir do nó de acesso; o endpoint não retorna o polígono ou coordenadas das demais células.
- Migração aditiva z38 e limpeza das linhas de cobertura no caminho de exclusão explícita de campanha.
- WGS2 v1, AP1/TP1/WGS1 e o catálogo v24 não foram alterados.

## Validação executada

- `test_genesis_wgs2_multicell.py`: **5 passed**. Inclui selector versionado, cobertura multi-célula cruzando uma emenda, polo, validação do contrato de acesso e materialização de `EV-LOC-0037` v24 reutilizada a partir de outra célula coberta. Com a dimensão de teste de **2.949 m**, o footprint teve **23 células TP1 em duas faces**, sem criar Location por célula. A formação, as relações e o acesso foram commitados, relidos, inspecionados e validados. O caso controla o seletor e injeta evidência física de teste; portanto valida persistência/geometria/integração, não a taxa orgânica de ocorrência.
- `test_genesis_wgs2_families.py` junto com os testes WGS2.2: **9 passed** em execução anterior; regressão de distribuição/seletor legado e contratos de perfil.
- Migração de campanha antiga e criação explícita de perfil: **2 passed**. O save anterior manteve perfil e `playable_state` inalterados; a migração não fez conversão automática.
- Regressão `test_genesis_local_formations.py`: **14 passed** em 189,69 s, cobrindo os caminhos WGS1/WGS2 anteriores, cavernas, água, persistência, descoberta, visita e exploração HTTP via TestClient. A alteração posterior da ordem de resolução de cobertura afeta somente o ramo WGS2 v2.
- `py_compile` nos módulos Python alterados: passou.
- Smoke real Uvicorn + SQLite temporário, perfil WGS2 v2, rotas normais de criação/início/observação/mapa/reinício, seeds 42, 0 e 7. Inícios: **53,412 s**, **46,948 s**, **47,236 s**. Seed 42 verificou cinco células próximas sem candidato; seed 0 caminhou 2,632 km e verificou 14 células sem candidato; seed 7 caminhou 10,686 km, verificou 44 células, encontrou uma oportunidade `EV-LOC-0084` que foi rejeitada porque o E1 não confirmou o habitat argiloso exigido. As três retomadas mantiveram local/mapa; nenhum payload público revelou campos de coordenadas ocultas. Os resultados não foram convertidos em alegação de ocorrência orgânica.
- Advertência observada: aviso de depreciação do Starlette sobre `httpx` no TestClient, sem falha de teste.

## Registro historico anterior a WGS2.2.1

- O smoke Uvicorn real foi executado em três seeds, mas não encontrou ocorrência orgânica elegível perto das rotas percorridas. Portanto, ele comprova inicialização, observação, deslocamento TP1, mapa sem vazamento e retomada; não comprova uma inspeção de formação nem uma segunda visita HTTP à mesma cobertura.
- O percurso da segunda célula é validado no teste técnico de materialização/persistência, com fixture de evidência confirmada e candidato controlado. Essa demonstração não é apresentada como jornada orgânica de jogador.
- A prova integrada de múltiplas células confirma uma formação do dataset (`EV-LOC-0037`) e seus acessos físicos, mas usa fixture para tornar a evidência geológica e o candidato reproduzíveis. Não mede ocorrência orgânica nem diversidade de formas em múltiplas seeds.
- A regra usa centro de célula, não interseção conservadora de área; uma lasca da forma que toque uma célula sem conter o centro não entra na cobertura. Isso é intencional para manter consulta e persistência limitadas.
- Cobertura pode ter milhares de metros, mas a ordem de magnitude do catálogo selecionado e os caminhos de exploração continuam limitados; estruturas acima de 3,4 km exigem revisão explícita do limite de busca e de travessia.
- Locais sobrepostos ainda não têm regras semânticas do dataset. A prioridade é apenas estável/determinística; não se afirma incompatibilidade ou exclusividade física.
- O relatório não aprova WGS2 v2 para campanhas reais: recomenda manter o opt-in experimental até o smoke HTTP com deslocamento entre duas células cobertas, descoberta progressiva e retomada após reinício.

## Pendencias historicas anteriores a WGS2.2.1

1. Executar um percurso Uvicorn com ocorrência natural elegível, incluindo inspeção, retorno/reinício e nova visita ao segundo acesso da mesma formação.
2. Medir ocorrência orgânica em mais seeds e confirmar formas com dimensão > uma célula sem colisão de identidade.
3. Só depois discutir incompatibilidades específicas de pares do catálogo e aprovação do perfil.

## WGS2.2.1 - validacao final da exploracao

### Politica e correcao

- A consulta de sobreposicoes ordenava por `formation_id`, identificador local da campanha. Agora ordena por `GenesisNaturalFormation.stable_key`, igual entre campanhas e independente da ordem de insercao.
- Acesso publico ja materializado fica fixado a sua instancia. Um novo setor sobreposto nao redireciona esse acesso. O candidato proprio da celula ainda e avaliado antes do fallback de cobertura.
- Novas rotas usam `WGS2_COVERAGE_ACCESS_V2` com `selection_policy=wgs2-overlap-priority-stable-key-r2`. O validador aceita tambem `WGS2_COVERAGE_ACCESS` antigo. Nenhum save foi migrado.
- O footprint e computado antes de inserir/flushar instancia e cobertura. Se ultrapassar o indice limitado a oito saltos, a geracao falha sem gravar a formacao nem cobertura parcial. Teto de 3.400 m mantido.

### Resultados separados

**PROVA TECNICA CONTROLADA.** EV-LOC-0037 com 2.949 m cobre 23 celulas TP1 em duas faces, incluindo emenda, e passa verificacoes de distancia esferica/checksum. Outra prova cobre uma unica face. Um footprint de teste de 10 km exercita a recusa acima de oito saltos e confirma que nenhum Location, instancia ou linha de cobertura parcial foi persistido. Nao se exige intersecao exata de poligonos.

**EXPLORACAO HTTP CONTROLADA.** `backend/scripts/playtest_wgs2_multicell_http.py` usa SQLite temporario, seed 42, perfil WGS2 v2, registro real v24 EV-LOC-0037 e evidencia terrestre E1 confirmada em fixture de teste. A fixture e criada antes do percurso e nao altera o seletor/endpoint de producao. O personagem cria/inicia campanha, observa, viaja por conexoes TP1, descobre e inspeciona a formacao; retorna ao territorio, percorre outra conexao TP1 ate uma celula coberta, acessa e inspeciona a mesma formacao.

- Dimensao: **3.249 m**; **15 celulas** na face 1. Origem `(1,17,75775,108544)`, segunda celula `(1,17,75774,108544)`. Segundo acesso: `wgs2_cell_access_1_17_75774_108544_74c2662a5c6ef2462f673800`, caminhada geodesica de **10,0 m**.
- As duas inspecoes resolveram a mesma instancia, sem duplicacao. Reinicio real do Uvicorn preservou identidade, dimensoes, checksum `3ae485da9988ba5e5fbd1749e3d73335125f703a8af91cb2d4fd162770459540`, enderecos, acessos, descobertas e local do personagem. Inspecao pos-reinicio passou; mapa publico nao vazou coordenadas ocultas.
- Antes do DELETE: **1 formacao / 15 coberturas**. Depois do endpoint de exclusao: **0 / 0**. JSON: `%TEMP%/everreach-wgs2-2-1-http-wpuh1pht/report.json`.

**DESCOBERTA ORGANICA.** Nao comprovada. Nos smokes anteriores: seed 42, cinco celulas sem candidato; seed 0, 2,632 km e 14 celulas sem candidato; seed 7, 10,686 km e 44 celulas, mas EV-LOC-0084 rejeitada por falta da evidencia de habitat argiloso no E1. A jornada acima e controlada, nao e evidencia de frequencia organica.

### Ordem, desempenho e testes

- Duas campanhas de mesma seed/perfil, com as mesmas coberturas inseridas em ordens opostas, selecionaram `stable_key=formation-a`. Uma instancia sobreposta inserida depois nao alterou acesso publico fixado. Candidato proprio elegivel nao foi suprimido pela cobertura existente. Duas campanhas materializaram os mesmos dois acessos em ordens opostas e terminaram com a mesma identidade canonica por celula.
- Tempos ponta a ponta: movimento TP1 + preparo/resolucao da segunda celula **3,648 s**; viagem ao segundo acesso **1,880 s**; reinspecao apos reinicio **2,339 s**; inicio da campanha **47,681 s**. Narrativa externa desabilitada. Sao tempos de acoes HTTP, nao medicao isolada de SQL/identidade/validacao; sem novo benchmark geral ou perfil de memoria.
- `test_genesis_wgs2_multicell.py`: **9 passed**; conjunto multicell + families + sphere topology: **64 passed**, incluindo emenda, polo, limite, persistencia, overlap, candidato proprio e validacao. Um aviso Starlette/httpx de deprecacao no TestClient nao causa falha. O percurso HTTP completo passou apos a nova versao do contrato. Regressao dirigida WGS1 (`wgs1_http_exploration_cave_water_interaction_and_revisit` e persistencia de decisao): **2 passed** em 190,35 s.

### Conclusao e limites

WGS2.2 esta tecnicamente fechada para identidade multissetorial, acesso local progressivo, revisita apos reinicio e independencia de ordem para o mesmo conjunto de candidatos/coberturas testado. Nao garante identificar origens ainda nao consultadas globalmente. A prova de duas faces e tecnica; o percurso HTTP final permaneceu em uma face. O perfil fica experimental ate validar frequencia organica e experiencia humana.
