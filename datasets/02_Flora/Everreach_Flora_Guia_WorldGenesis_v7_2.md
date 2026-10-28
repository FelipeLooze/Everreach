# Everreach — Flora v7.2: vida em ambientes extremos

## Escopo e compatibilidade

Preserva **exatamente** os dicionários das 3.000 espécies, seus 6.000 itens e os 3.000 perfis ecológicos do v7.1. Adiciona 96 espécies autorais, cada uma com duas partes/item correspondentes (3096 espécies / 6192 partes / 6192 itens). As 8 associações de espécies existentes são **overlays** de micro-habitat, sem modificar os registros legados.

Os 16 habitats extremos possuem seis novas candidatas cada. Essas candidatas **não são população instanciada, spawn ou promessa de presença**; estruturas, água, profundidade, substrato, nutrientes e fonte de energia reais precisam existir. Micro-habitats normalmente são locais pontuais, não substitutos do bioma principal.

## Classes de magia

- **48 mundanas**: raras devido às condições específicas, sem efeito arcano.
- **32 latentes**: propensão arcana observável ou investigável, sem efeito mecânico pronto.
- **16 excepcionais**: exigem `anomalia_canonica_obrigatoria_id` EXATO, autorização para essa anomalia, fonte geográfica persistida e sobreposição real de local; permanecem bloqueadas por padrão.

A escala de raridade 0–100 não é porcentagem de spawn. Não gerar estoque nem preço de venda, efeitos alquímicos ou cura de maneira automática.

## Distinção biológica

`consorcio_simbiotico` é um **novo tipo taxonômico não-botânico** que exige suporte explícito do importador. É uma associação de organismos, não uma planta comum nem alga fotossintética. Fungos e líquens mantêm classificações próprias. Nenhuma alga fotossintética é colocada nos ambientes sem luz; as algas de banquisa e oceano polar exigem camadas iluminadas na estação adequada.

Em águas muito profundas, exigir detritos marinhos, substratos/partículas com nutrientes, gradiente quimiossintético ou fonte canônica adequada e **existente**. Uma dorsal oceânica não cria fonte hidrotermal. Grutas e rios subterrâneos exigem evidência hídrica W1/W2/P1; P1 é passagem hídrica, não vegetação. `null` = desconhecido, não válido por padrão.

## Regras de descoberta e aquisição

1. E1 confirma ambiente candidato físico, sem exigir vegetação anterior.
2. V4/T1/C3/JR1/W1/W2/P1 fornecem dados efetivos para geologia, luz, condições hídricas e acesso; onde faltam dados essenciais, estado `pendente`.
3. Somente depois de validar micro-habitat, nutriente/energia, potencial de colonização e origem biológica, instanciar população persistente com localização e biomassa finita.
4. Não fazer nova rolagem de espécie em visitas à mesma célula. Escala planetária não multiplica livremente espécies excepcionais; usar orçamento regional/canônico e distribuição determinística.
5. Observação, identificação e coleta utilizam `EV-PROF-BOT-001` e `EV-PROF-BOT-002`, ferramentas compatíveis, equipamento de acesso e preservação. Dificuldade de acesso diferente da dificuldade de manuseio.
6. Coleta consome biomassa realmente disponível. Não criar material, poder, estoque de NPC, preço ou recompensa pelo simples cadastro.

## Interfaces e importação

- Campos legados preservados em `flora`, `itens`, `perfis_ecologicos_world_genesis_v7_1`.
- Novos registros incluem `ecologia_extrema_v7_2` e `regras_extremos_v7_2`.
- `extensoes_de_habitat_legado_v7_2` adiciona 8 candidaturas para micro-habitats; importador deve tratá-las como overlays condicionais e não aceitar o bioma inteiro.
- `definicoes.tipos_extensao_v7_2` documenta `consorcio_simbiotico`.
- `indices.candidatos_por_ambiente_natural_ev_eco_1_1_1` é uma visão derivada completa, não autoritativa de geração.

## Estado da validação

Testes estruturais foram realizados sobre o JSON gerado e o ZIP foi verificado. **Não foi testado o importador, nem a Fase 1.0, nem a simulação do World Genesis**. A calibração das pressões, fontes químicas e probabilidade de estabelecimento cabe ao backend e ao playtest visual.
