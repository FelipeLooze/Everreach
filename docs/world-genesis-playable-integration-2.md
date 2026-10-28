# World Genesis — Integração Jogável 2

## Decisões e contratos

A auditoria da integração 1 e dos serviços de região, local, viagem, exploração, descoberta, mapa, topologia esférica, T1, E1 e Vg2 confirmou um caminho existente para autoria e movimentação: `Location`, `LocationConnection`, os registros de descoberta por personagem e `move_character`. A mudança conecta o World Genesis a esse caminho. TP1 não cria um segundo grafo, relógio, mapa ou descoberta.

TP1 é uma extensão optativa do AP1 para campanhas que ainda não tinham começado quando foram iniciadas. O primeiro start grava a versão `territory_tp1` no descritor da campanha. Um AP1 já iniciado sem esse campo continua sem conversão e conserva seus IDs, posições e regras. Campanhas legadas continuam com `world_profile = NULL` ou `legacy`. A revisão Alembic z35 só acrescenta dois campos anuláveis: `locations.genesis_site` e `location_connections.spatial_contract`.

Cada lugar TP1 tem um `LocationSpatialAnchor` imutável e endereço de célula derivado do raio e da resolução física do V4. Com o raio AP1 de 63.710 km, os pontos de exploração usam células de aproximadamente um quilômetro; o nível é escolhido por `ceil(log2(2R/1 km))` e respeita o limite de níveis do cube-sphere. A célula e o ponto persistidos determinam o local, sem depender da ordem de visitas. Regiões agrupam setores em coberturas espaciais amplas, e Subregions cobrem os setores menores. Esses nomes descrevem agrupamentos geográficos de gameplay, sem afirmar que sejam continentes, biomas, nações ou regiões políticas. O endereço projetado `Location.x/y` serve ao mapa esquemático atual; `SurfacePoint` continua sendo a posição física autoritativa.

Ao chegar a um lugar novo, TP1 prepara seu setor T4, consulta e persiste um ponto E1 e a comunidade Vg2, e salva fatos locais observáveis. A comunidade mantém o contrato finito de fundadores existente; a observação usa o encontro Vg2 atual. O lugar inicial é preparado durante o start. Para um destino, a preparação ocorre somente depois da validação da rota e da stamina, dentro de savepoint. Uma falha desfaz os novos locais e conexões. Revisitas validam as autoridades persistidas e reutilizam os mesmos IDs e estoques.

Cada lugar preparado acrescenta até quatro vizinhos determinísticos (oeste, leste, sul, norte) à tabela existente de Locations e as conexões dirigidas correspondentes à tabela existente de LocationConnections. Isso cria fronteiras, inclusive entre faces do cubo, sem materializar uma vizinhança recursivamente. Destinos apenas preparados como vizinhos ainda não têm E1 nem plantas materializadas. Somente explorar os arredores registra as conexões e locais como conhecidos pela descoberta que já existia.

TP1 mede a distância pelo percurso de grande círculo, com correção de relevo amostrada até 100 m, e armazena metros no contrato. A unidade legada `LocationConnection.distance` conserva seu significado nas campanhas antigas. Nas rotas TP1, um custo equivale explicitamente a 1.000 m; o serviço de viagem existente, com 15 minutos por unidade e modificadores de terreno, produz 4 km/h antes de efeitos de ritmo. Rotas acima do orçamento de amostragem (33 pontos, cerca de 3,2 km) são recusadas como não reconhecidas pelo contrato TP1. Uma inclinação local acima de 45° bloqueia a caminhada a pé. O teste de oceano exige T1 abaixo do datum e a classificação de oceano de referência H1; uma depressão continental abaixo do datum sozinha não bloqueia a rota. H1 é uma classificação macroscópica de referência, não confirmação de coluna d'água local. Cada conexão guarda pontos, amostras, assinaturas, comprimento e custo com checksum; a viagem valida esse contrato e a superfície T1 antes de mover o personagem. Risco permanece zero porque ainda não há evidência de ameaça para essa rota.

A observação da vegetação chama E1 no ponto atual e Vg2 no local atual. A preparação verifica materiais e autoridades já consolidados; ela não transforma potencial ambiental em bioma nem cria água, flora adicional, fauna ou perigos. Narrativa recebe a descrição e os fatos da posição atual. O contexto regional usa o fato local confirmado, sem inferir economia ou perigo de uma área não povoada. O atalho de direção só resolve uma conexão TP1 que o personagem já descobriu; o nome canônico do destino continua oculto.

O mapa existente filtra locais e rotas pelas descobertas e pela precisão conhecida. Os destinos não descobertos e suas posições ficam fora da resposta; âncoras físicas e contratos de rota nunca são serializados no mapa. Conhecer uma rota pode mostrar seu destino de forma aproximada pelas regras existentes, enquanto somente visitar concede precisão. A posição exata não aparece para lugares desconhecidos.

## Playtest HTTP

O playtest usou Uvicorn, requests HTTP normais e um banco SQLite recém-criado em diretório temporário. Alembic subiu até z35 nesse arquivo. A ferramenta de computador não encontrou navegador nem aplicativo nesta sessão; portanto, o percurso visual pela interface permanece pendente. Os testes HTTP/componentes não são apresentados como validação visual.

As seeds 42 e 8675309 iniciaram o AP1, observaram, examinaram e coletaram uma parte vegetal disponível, viajaram para dois destinos, observaram cada destino, retornaram, esperaram 16 horas, conferiram o mapa, reiniciaram o backend e retomaram a campanha. As três posições de cada percurso tinham âncoras persistidas. A coleta retirou uma unidade do estoque e criou um item de massa positiva, e o estoque permaneceu reduzido após retornar. Após o reinício, a posição, a lista de plantas observadas, os itens e o mapa coincidiram com o estado anterior. A resposta do mapa continha somente os três lugares visitados; nenhum campo de coordenada esférica ou endereço de destino desconhecido foi exposto.

| Seed | Classificação ambiental E1 nos três pontos | Cobertura Vg2 no início e pontos | Plantas observadas nos destinos |
| --- | --- | --- | --- |
| 42 | Deserto frio nos três pontos | 421.052 ppm no início; 418.549 ppm no segundo destino | 8 por destino |
| 8675309 | Deserto frio nos três pontos | 276.922 ppm no início; 274.423 ppm no segundo destino | 5 no primeiro; 7 no segundo |

O T1 mediu entre 911,7–913,1 m nos pontos da seed 42 e 1.923,7–1.924,6 m na seed 8675309. Essas diferenças vieram dos campos físicos amostrados; E1 manteve o mesmo rótulo porque as condições dos pontos continuaram na mesma classe.

Os pontos próximos compartilham a classificação deserto frio nas duas seeds; isso é o que as fontes atuais retornaram, e não uma diferença fabricada para o playtest. As comunidades e indivíduos são próprios de cada campanha e dos pontos consultados.

Cada chegada preparou aproximadamente 0,4–1,4 s de trabalho de local no playtest. As consultas E1 separadas mediram 0,4–1,1 s no primeiro acesso e 0,07–0,18 s no acesso aquecido. Os tempos de ponta a ponta registrados foram:

| Operação HTTP | Seed 42 | Seed 8675309 |
| --- | ---: | ---: |
| Start AP1 (frio) | 36,78 s | — |
| Start do segundo mundo | — | 24,42 s |
| Preparação e viagem ao primeiro e segundo destinos | 1,86–2,59 s | 2,30–2,34 s |
| Revisita e retorno | 1,01–1,29 s | 1,53–2,03 s |
| Observação vegetal | 4,02–5,18 s | 4,29–4,95 s |
| Mapa conhecido | 0,022 s | 0,007 s |
| Start após reinício do backend | 3,60 s | 3,25 s |

Os tempos de ação incluem checkpoints, atualização de estados e validação narrativa; não representam o tempo isolado de materialização. Dois processos de teste Python estavam concorrendo pela CPU, então os starts e as operações HTTP refletem contenção local. O ambiente desabilitou provedores LLM no playtest HTTP: custo externo zero e narrativa pelo caminho de reserva. Não há medição de provedor externo nesta entrega. A observação de plantas é o maior custo recorrente medido.

Em cada chegada, o percurso preparou somente o setor do destino. Cada campanha terminou com três setores materializados, quatro agrupamentos Region e 20 conexões dirigidas; os vizinhos preparados não tiveram seus setores detalhados antecipadamente. Foram persistidos 33 pontos E1 e 39 indivíduos Vg2 na seed 42, e 17 pontos E1 e 20 indivíduos na seed 8675309, incluindo encontros vegetais próximos. O resumo de IDs, pontos de teste, assinaturas, custos, amostras e tempos está em [http-playtest.json](../artifacts/playable-integration-2/http-playtest.json). O script reproduzível que cria seu próprio banco, executa a migração e reinicia Uvicorn está em [playtest_genesis_territory.py](../backend/scripts/playtest_genesis_territory.py).

## Validação

- `test_genesis_territory.py`: **6 passaram** após a asserção final de contexto do narrador. Inclui duas seeds, rotas, setores, dois destinos, ida e retorno, relógio, coleta preservada, observação por posição, rollback por falta de stamina e falha injetada, idempotência, independência da ordem, compatibilidade AP1 e travessias em três raios.
- `test_genesis_playable.py` e o teste isolado de migração: as duas seeds AP1, perfil legado e roundtrip de uma save V1 populada passaram; a rodada combinada registrou **10 testes aprovados**.
- Regressão direcionada: **159 passaram** em viagens, acompanhantes, exploração, R1, GA1/GA2, campanhas HTTP, residentes, mapas e planejamento, fronteiras, contextos narrativos, topologia, materialização e contratos espaciais. Um caso Alembic dessa rodada iniciou no diretório errado; após fixar o diretório do subprocesso em `backend`, ele passou isoladamente e na rodada combinada de 10 testes.
- Migração V1 populada para `head` e downgrade em SQLite temporário, verificando a preservação de colunas antigas e a nulidade dos novos campos.
- Testes de interface AP1: 8 aprovados; build TypeScript/Vite concluído.
- Hash do banco padrão antes e depois: `88f5540c…d5971f3` (inalterado). Nenhuma migração foi aplicada a ele.

## Limites e próxima etapa

As rotas descrevem travessias curtas pedestres entre centros de células. Amostragem a cada 100 m não encontra um desfiladeiro ou obstáculo mais estreito do que a amostragem, nem calcula um desvio contínuo; tais caminhos precisam de uma rota alternativa composta pelas conexões adjacentes já geradas, e o trecho local estreito ainda não tem detalhe suficiente para autorização. A classificação marítima H1 é aproximada. A hidrografia P1 não transforma lagos/canais potenciais em barreiras navegáveis ou confirmadas. Não há risco de Living Frontiers, exploração naval, passagens fantásticas, Atlas ou viagem além de uma rota local.

O browser indisponível impede marcar a validação visual da UI como concluída. Para repetir a verificação manual com o arquivo temporário registrado no JSON, execute no backend:

```powershell
$env:DATABASE_URL = 'sqlite:///C:/Users/Felipe/AppData/Local/Temp/everreach-tp1-8ze1gc0t/playtest.sqlite'
$env:INTENT_LLM_PROVIDER = 'disabled'
$env:NARRATIVE_LLM_PROVIDER = 'disabled'
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Na pasta frontend, execute `npm.cmd run dev -- --host 127.0.0.1 --port 5173`. Abra `http://127.0.0.1:5173`, clique em **Campanhas**, continue em **TP1 HTTP 42** com **Exploradora**, e confira observação vegetal, inventário, mapa, viagens para os destinos descobertos, retorno e retomada depois de reiniciar o backend. O fluxo HTTP jogável, as âncoras, a persistência e os custos já estão demonstrados e validados automaticamente.
