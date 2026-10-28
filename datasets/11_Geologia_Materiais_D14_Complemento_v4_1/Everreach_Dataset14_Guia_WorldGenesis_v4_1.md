# Everreach — Dataset 14 Complemento Geológico v4.1

**Objetivo:** preencher a lacuna entre a taxonomia mineral do Dataset 14 v4 e os dados que o World Genesis V4/T1 precisará fornecer. **Não altera os 120 materiais, os 14 atributos, os 360 perfis de extração ou os 18 nomes de modelos existentes.**

## Arquivos
- `Everreach_Dataset14_Complemento_Geologico_4_1.json`: **20** rochas e substratos, **18** pontes, **24** rotas alternativas, contrato e políticas de calibração.
- `Everreach_Dataset14_Indice_Geologico_4_1.json`: índice leve de lookup.
- `Everreach_Dataset14_Validacao_Geologica_4_1.json`: resultados de verificações e fixtures.
- `Everreach_Dataset14_Materiais_Fantasia_120_Ocorrencia_v4.json`: base v4 imutável; SHA-256 `1101b05722d85fdc9168d0ed6117e1a3c960343d40a992ada6417e86d92a7eec`.

## Separação das camadas
1. V4/T1 define **história tectônica, litologia, estruturas e formação geológica física**, antes dos biomas.
2. Traduzir os dados reais do World Genesis para o **contrato lógico** `contrato_adaptador_world_genesis` (campos ainda **NÃO verificados** no código).
3. Aplicar a ponte de cada um dos 18 `modelo_geologico`, exigindo `substratos_aceitos_any` e `evidencias_obrigatorias_all`. Ausência de evidência = inelegível, não inventar substrato.
4. Para cada material, testar o modelo primário da v4 e opcionalmente as **24 rotas aditivas**, sem somar probabilidades nem multiplicar slots de formação.
5. Aplicar autorização canônica, orçamento regional/global, unicidade por oportunidade geológica; persistir depósito finito.
6. Só depois usar clima e biomas para **exposição, erosão, acesso, vegetação e detecção**. Biomas nunca criam jazidas.

## Raridade em planeta gigantesco — BLOQUEIO DE SEGURANÇA DE BALANCEAMENTO
Os números do v4 por milhão de formações elegíveis são **referências históricas**. Não ativar diretamente. Um planeta com área 100 vezes a Terra não informa quantas unidades geológicas elegíveis serão produzidas. O novo dataset registra projeções ingênuas de 1.000 até 10 bilhões de oportunidades hipotéticas, **não frequências recomendadas**.

- `intensidades_v4_ativas_na_geracao = false`.
- Classes comuns/rara/muito rara dependem de orçamento aprovado e medição de unidades geológicas.
- Classe lendária: **zero geração aleatória**, sem evento canônico autorizado.
- Contar **unidades geológicas persistentes**, nunca tiles, passos, visitas nem checks de loot.
- Alternativas de origem **não multiplicam** oportunidades de spawn para um mesmo material.
- Metas de raridade calibradas só depois de rodar cenários de T1 reais e medir a distribuição regional.

## Ouro e ferro: duas origens diferentes
- Ouro original: `aluvião` (secundária em rios) mantido. Adiciona `veio_montanhoso` e `veio_profundo` (primários), com evidência mineralizante e estrutura real.
- Ferro original: `veio_montanhoso` mantido. Adiciona `sedimentar` (acumulação ferrífera) sem exigir montanha nem inferir da altitude.
- Um sedimento aluvial sozinho não cria ouro: precisa de fonte transportada, processo de concentração e orçamento válido.

## Questões que continuam abertas (precisam do Codex)
- Identificadores reais no World Genesis V4/T1, formatos de unidades geológicas, tectônica e persistência.
- Resolução e densidade de oportunidades geológicas físicas, mapear os 20 substratos.
- Procedimentos e limites de geração por macrorregião/planeta; resultados de testes com seeds reais.
- Implementação de tipos de fonte especiais (organismos, meteoritos, veios arcanos, anomalias canônicas).

Esses arquivos **não geram jazidas, itens, fragmentos soltos ou inventário** por si; são um contrato de dados e propostas de elegibilidade. O catálogo ativo continua com os **120 nomes fantásticos**; granito, basalto etc. são descritores de terreno, não itens obrigatórios do jogador.
