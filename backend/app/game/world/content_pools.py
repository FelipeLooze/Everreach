"""Phase 15 — curated content pools for procedural world generation.

Every pool here is picked from using a `random.Random` seeded through
app.game.world.generation.derive_seed, never Python's global `random`
module directly, so generation stays reproducible per-campaign (see
Phase 15A). Pools are deliberately hand-curated (not LLM-generated) so
generation never depends on Ollama being reachable and stays instant —
the LLM's role in Everreach stays narration/classification, never world
persistence (see the repo's core architecture principle).
"""

CLIMATE_SUMMARIES = [
    "Verões amenos e invernos úmidos moldam o ritmo das colheitas em toda a região.",
    "O clima é instável, com chuvas fortes na primavera e secas prolongadas no verão.",
    "Ventos constantes vindos do norte trazem um frio seco por boa parte do ano.",
    "Um clima temperado e previsível favorece a agricultura na maior parte do território.",
    "Nevoeiros densos cobrem os vales pela manhã, dando lugar a dias quentes e claros.",
    "As estações são marcadas, com invernos rigorosos nas terras altas e verões úmidos nas baixadas.",
]

CULTURAL_SUMMARIES = [
    "Comunidades locais valorizam acordos orais e a palavra empenhada tem peso de lei costumeira.",
    "Uma forte tradição de guildas artesanais organiza boa parte da vida econômica e social.",
    "Festivais sazonais ligados à colheita reúnem vilarejos distantes uma vez por estação.",
    "A desconfiança de forasteiros é comum fora dos grandes centros de comércio.",
    "Histórias orais sobre os fundadores das primeiras vilas ainda circulam nas tavernas.",
    "O respeito por anciãos e conselhos locais é a base da autoridade na maioria dos assentamentos.",
]

HISTORICAL_SUMMARIES = [
    "Ruínas espalhadas atestam um povo mais antigo, cuja queda ninguém hoje consegue explicar por completo.",
    "Uma guerra de fronteira há gerações redesenhou os limites entre os territórios vizinhos.",
    "Rotas comerciais estabelecidas há séculos ainda definem quais assentamentos prosperam.",
    "Um período de pragas dizimou vilas inteiras há algumas gerações, cujos vestígios ainda são evitados.",
    "A região foi unificada sob um único conselho apenas há poucas gerações, após séculos de fragmentação.",
    "Lendas locais falam de uma catástrofe antiga que moldou boa parte da geografia atual.",
]

# Phase 15 follow-up — the Region's own name and its anchor subregion's
# name are now generated too (no proper noun in Everreach's starting
# point is fixed anymore — every campaign gets its own).
REGION_NAME_POOL = [
    "Vale Verdejante",
    "Terras de Halwen",
    "Planície de Cordal",
    "Vale do Sol Poente",
    "Confins de Marrow",
    "Terras Altas de Sernn",
    "Vale das Águas Claras",
    "Campos de Kessler",
    "Terras de Draven",
    "Vale Ferrow",
]

ANCHOR_SUBREGION_NAME_POOL = [
    "Campos Iniciais",
    "Terras do Primeiro Passo",
    "Campina Central",
    "Planície de Chegada",
    "Terras Baixas do Começo",
]

SUBREGION_NAME_POOL = [
    "Bosque Sussurrante",
    "Terras Altas de Arven",
    "Fronteira Norte",
    "Terra dos Grandes Lagos",
    "Planalto Oriental",
    "Terras Selvagens do Sul",
    "Montanhas Cinzentas",
    "Vale de Halwen",
    "Charco Negro",
    "Costa dos Ventos",
    "Terras Baixas do Rio",
    "Passagem da Fronteira",
    "Floresta Profunda",
]

# Phase 15D — per-subregion flavor text, independent of the Region-level
# summaries above (a subregion's culture/economy is not just a smaller
# copy of the whole Region's).
SUBREGION_CULTURE_SUMMARIES = [
    "Famílias locais transmitem seus ofícios de geração em geração, com pouca entrada de forasteiros.",
    "Uma rede de pequenos conselhos comunitários resolve a maioria das disputas sem recorrer a autoridades distantes.",
    "Crenças ligadas aos ciclos das estações moldam boa parte do calendário social.",
    "Viajantes e comerciantes itinerantes são bem recebidos e trazem notícias de outras partes da região.",
    "Um forte senso de autossuficiência torna a população local reservada com estranhos.",
    "Cantos e histórias tradicionais são preservados com cuidado nas poucas comunidades maiores.",
    "A vida gira em torno de um punhado de famílias influentes que ocupam a região há gerações.",
    "Práticas religiosas variam bastante de um assentamento a outro, sem uma autoridade única.",
]

# Phase 15E — one major physical geography feature archetype per biome.
# Each entry is (name, Location.type, description). Kept distinct from the
# subregion's own name (a geography feature is a specific place inside the
# subregion, not a synonym for it).
GEOGRAPHY_BY_BIOME = {
    "PLAINS": [
        ("Planície das Espigas", "plains", "Uma vasta planície de capim alto, pontuada por poucas árvores isoladas."),
        ("Campo Aberto do Meiodia", "plains", "Terras baixas e planas, boas para pastagem e cultivo em grande escala."),
    ],
    "FOREST": [
        ("Floresta das Sombras Longas", "forest", "Uma mata densa e antiga, cuja copa fechada mantém o chão sempre em penumbra."),
        ("Bosque do Silêncio", "forest", "Árvores altas e próximas tornam a passagem lenta e o som abafado."),
    ],
    "HILLS": [
        ("Colinas Onduladas", "hills", "Uma sucessão de colinas baixas cobertas de vegetação rasteira."),
        ("Terras Altas Rochosas", "hills", "Elevações rochosas cortadas por trilhas estreitas e íngremes."),
    ],
    "MOUNTAINS": [
        ("Cordilheira dos Picos Cinzentos", "mountain_range", "Uma cadeia de montanhas altas, com passagens estreitas e perigosas."),
        ("Muralha de Pedra", "mountain_range", "Uma barreira natural de rocha que isola o que fica além dela."),
    ],
    "WETLANDS": [
        ("Pântano das Águas Paradas", "marsh", "Um terreno alagadiço, difícil de atravessar e cheio de vida escondida."),
        ("Brejo Cinzento", "marsh", "Névoa constante paira sobre um solo encharcado e traiçoeiro."),
    ],
    "RIVER_VALLEY": [
        ("Rio Correntoso", "river", "Um rio largo e caudaloso que corta o vale de ponta a ponta."),
        ("Vale do Grande Rio", "river", "Terras férteis às margens de um rio importante para a região."),
    ],
    "LAKE_COUNTRY": [
        ("Grande Lago Sereno", "lake", "Um lago extenso, cujas águas calmas sustentam vilas de pescadores."),
        ("Lago das Mil Ilhas", "lake", "Um corpo de água pontuado por pequenas ilhotas dispersas."),
    ],
    "COASTAL": [
        ("Costa Batida pelo Vento", "coast", "Falésias e praias rochosas encontram o mar aberto."),
        ("Litoral das Marés Altas", "coast", "Uma faixa costeira sujeita a marés fortes e ventos constantes."),
    ],
    "FRONTIER": [
        ("Terras Ermas da Fronteira", "wilderness", "Um território pouco povoado, na fronteira do que é considerado seguro."),
        ("Descampado Selvagem", "wilderness", "Vastidão aberta e inóspita, raramente cruzada por viajantes."),
    ],
}

# Phase 15F — settlement names are generated by combining two syllable
# pools (rather than a fixed list) so an arbitrarily large massive region
# never runs out of distinct names. "Arven" (used as flavor text in
# earlier commit messages) can emerge naturally from this combination.
SETTLEMENT_NAME_PARTS_A = [
    "Ar", "Bel", "Cor", "Dun", "El", "Fen", "Gal", "Hal", "Il", "Kar",
    "Lor", "Mor", "Nor", "Or", "Pel", "Quen", "Rav", "Sil", "Tor", "Ul",
    "Val", "Wyn",
]
SETTLEMENT_NAME_PARTS_B = [
    "ven", "dor", "wick", "helm", "ford", "gard", "mere", "stead", "holt",
    "brook", "haven", "moor", "ridge", "vale", "crest", "wyn",
]

# Phase 15F — which major settlement types make plausible sense for a
# given biome (settlements should have a reason to exist, spec). The
# starting settlement's TYPE stays fixed ("village", see seed.py) even
# though its NAME is now generated from the same SETTLEMENT_NAME_PARTS_*
# pool above — this table isn't consulted for it.
SETTLEMENT_TYPE_BY_BIOME = {
    "PLAINS": ["TOWN", "TRADE_SETTLEMENT", "VILLAGE"],
    "FOREST": ["VILLAGE", "ISOLATED_SETTLEMENT", "RELIGIOUS_SETTLEMENT"],
    "HILLS": ["TOWN", "MINING_SETTLEMENT", "FORTRESS_SETTLEMENT"],
    "MOUNTAINS": ["MINING_SETTLEMENT", "FORTRESS_SETTLEMENT"],
    "WETLANDS": ["ISOLATED_SETTLEMENT", "VILLAGE"],
    "RIVER_VALLEY": ["TRADE_SETTLEMENT", "TOWN", "CITY"],
    "LAKE_COUNTRY": ["TRADE_SETTLEMENT", "TOWN"],
    "COASTAL": ["TRADE_SETTLEMENT", "CITY"],
    "FRONTIER": ["ISOLATED_SETTLEMENT", "FORTRESS_SETTLEMENT", "HAMLET"],
}

SETTLEMENT_PROFILE_BY_TYPE = {
    "MAJOR_CITY": "grande centro urbano e comercial da região",
    "CITY": "cidade estabelecida, com mercado próprio e vida urbana organizada",
    "TOWN": "cidade de porte médio, ponto de passagem regional",
    "TRADE_SETTLEMENT": "assentamento erguido em torno do comércio de passagem",
    "MINING_SETTLEMENT": "assentamento de mineração que vive da extração de minério",
    "RELIGIOUS_SETTLEMENT": "assentamento organizado em torno de um templo importante",
    "FORTRESS_SETTLEMENT": "assentamento fortificado que controla uma passagem estratégica",
    "VILLAGE": "pequena vila agrícola",
    "HAMLET": "pequeno povoado isolado",
    "ISOLATED_SETTLEMENT": "assentamento remoto, distante das rotas principais",
}

POPULATION_TIER_BY_TYPE = {
    "MAJOR_CITY": 5,
    "CITY": 4,
    "TOWN": 3,
    "TRADE_SETTLEMENT": 3,
    "MINING_SETTLEMENT": 3,
    "RELIGIOUS_SETTLEMENT": 3,
    "FORTRESS_SETTLEMENT": 3,
    "VILLAGE": 2,
    "HAMLET": 1,
    "ISOLATED_SETTLEMENT": 1,
}

# Phase 15G — settlement-internal services. Each key maps to
# (name, Location.type, description). Which keys a settlement gets
# depends on its SettlementType (SERVICES_BY_SETTLEMENT_TYPE below) — not
# every settlement has every service (spec: do not make every village
# contain identical services).
SETTLEMENT_SERVICE_POOL = {
    "inn": ("Estalagem", "inn", "Um lugar para viajantes descansarem e conseguirem uma refeição quente."),
    "tavern": ("Taverna", "tavern", "Bebida, conversa e as últimas notícias que circulam por ali."),
    "blacksmith": ("Ferraria", "blacksmith", "Forja e bigorna, onde ferramentas e armas simples são feitas e reparadas."),
    "general_store": ("Loja Geral", "shop", "Suprimentos básicos para viajantes e moradores."),
    "temple": ("Templo", "temple", "Um pequeno espaço de culto e reflexão."),
    "notice_board": ("Quadro de Avisos", "notice_board", "Onde recados, pedidos de ajuda e anúncios locais são fixados."),
    "warehouse": ("Armazém", "warehouse", "Depósito de mercadorias à espera de transporte ou venda."),
    "mine_entrance": ("Entrada da Mina", "mine_entrance", "O acesso principal aos túneis de extração de minério."),
    "barracks": ("Quartel", "barracks", "Onde os guardas locais se organizam e descansam."),
    "market_square": ("Praça do Mercado", "market_square", "Um espaço aberto tomado por barracas de comerciantes."),
}

SERVICES_BY_SETTLEMENT_TYPE = {
    "MAJOR_CITY": ["market_square", "inn", "tavern", "temple", "general_store", "blacksmith", "barracks", "notice_board"],
    "CITY": ["market_square", "inn", "tavern", "temple", "general_store", "blacksmith", "notice_board"],
    "TOWN": ["inn", "tavern", "general_store", "blacksmith", "notice_board"],
    "VILLAGE": ["inn", "general_store", "blacksmith", "notice_board"],
    "HAMLET": ["notice_board"],
    "ISOLATED_SETTLEMENT": [],
    "FORTRESS_SETTLEMENT": ["barracks", "inn", "blacksmith", "notice_board"],
    "MINING_SETTLEMENT": ["mine_entrance", "warehouse", "tavern", "blacksmith", "notice_board"],
    "RELIGIOUS_SETTLEMENT": ["temple", "inn", "notice_board"],
    "TRADE_SETTLEMENT": ["warehouse", "general_store", "inn", "market_square", "notice_board"],
}

# Phase 15G — districts, for MAJOR_CITY/CITY only (name, district type key).
CITY_DISTRICTS = [
    ("Distrito Central", "central"),
    ("Distrito dos Mercadores", "merchant"),
    ("Distrito dos Artesãos", "artisan"),
    ("Distrito Residencial", "residential"),
    ("Distrito Pobre", "poor"),
    ("Distrito Religioso", "religious"),
    ("Portões", "gates"),
]

# Phase 15I — major Points of Interest. Persistent regardless of player
# discovery, one pool shared across all subregions (not biome-keyed —
# ruins/caves/forts can plausibly appear almost anywhere).
POI_POOL = [
    ("Ruínas de Telmar", "ruins", "Restos de pedra cobertos por vegetação, de um povoado cuja queda ninguém hoje consegue explicar."),
    ("Caverna Funda", "cave", "Uma caverna extensa cujos túneis mais distantes nunca foram totalmente mapeados."),
    ("Mina Abandonada", "abandoned_mine", "Uma escavação antiga, abandonada há tempo suficiente para que ninguém lembre exatamente por quê."),
    ("Templo Esquecido", "temple_ruins", "Um templo em ruínas, ainda visitado por poucos peregrinos que conhecem o caminho."),
    ("Forte em Ruínas", "fort_ruins", "Os restos de uma fortificação que já controlou a passagem por ali."),
    ("Torre Solitária", "tower", "Uma torre de pedra isolada, cujo propósito original se perdeu no tempo."),
    ("Sítio Sagrado", "sacred_site", "Um lugar que comunidades próximas ainda tratam com reverência."),
    ("Campo de Batalha Antigo", "battlefield", "O terreno ainda guarda sinais de um conflito de gerações passadas."),
    ("Vale das Sombras", "dangerous_valley", "Um vale estreito com reputação sinistra entre os que vivem por perto."),
]

# Phase 15J — Regional Organizations & Major NPCs. Every major settlement
# gets one organization whose type/name matches its own SettlementType —
# a mining settlement gets a miners' guild, not a random org type.
ORG_TYPE_BY_SETTLEMENT_TYPE = {
    "MAJOR_CITY": "POLITICAL",
    "CITY": "COMMERCIAL",
    "TOWN": "COMMERCIAL",
    "VILLAGE": "COMMUNITY",
    "HAMLET": "COMMUNITY",
    "ISOLATED_SETTLEMENT": "COMMUNITY",
    "FORTRESS_SETTLEMENT": "MILITARY",
    "MINING_SETTLEMENT": "GUILD",
    "RELIGIOUS_SETTLEMENT": "RELIGIOUS",
    "TRADE_SETTLEMENT": "COMMERCIAL",
}

ORG_NAME_TEMPLATE_BY_TYPE = {
    "POLITICAL": "Conselho de {name}",
    "COMMERCIAL": "Guilda dos Mercadores de {name}",
    "COMMUNITY": "Conselho de {name}",
    "MILITARY": "Guarnição de {name}",
    "GUILD": "Guilda dos Mineradores de {name}",
    "RELIGIOUS": "Ordem de {name}",
}

LEADER_TITLE_BY_ORG_TYPE = {
    "POLITICAL": "líder do conselho",
    "COMMERCIAL": "mestre da guilda",
    "COMMUNITY": "líder do conselho",
    "MILITARY": "comandante da guarnição",
    "GUILD": "mestre da guilda",
    "RELIGIOUS": "sumo sacerdote",
}

# Deliberately excludes "Corren"/"Dessa"/"Bram" and "Ashvale"/"Marrow"/
# "Holt": those are the fixed given/family names of the 3 SimulatedPlayers
# (Phase 7) always placed at the starting village — a generated NPC name
# colliding with one of them made app.game.engine._handle_talk's
# substring-based TALK-target resolution genuinely ambiguous (both an NPC
# and a SimulatedPlayer would match), a real bug caught by
# test_apply_intent_talk_completes_matching_quest_objective flaking.
NPC_GIVEN_NAME_POOL = [
    "Ilya", "Thane", "Rowan", "Sable", "Perrin",
    "Wren", "Colm", "Astra", "Dorian", "Lena", "Garrick", "Nessa", "Aldric",
]
NPC_FAMILY_NAME_POOL = [
    "Sernn", "Talbrook", "Ferrow", "Kessler",
    "Draven", "Wystan", "Corrin", "Hallow", "Brennig", "Sowerby", "Quill",
]

LEADER_PERSONALITY_POOL = [
    "Ponderado e cauteloso, prefere ouvir antes de decidir.",
    "Direto e prático, tem pouca paciência para formalidades.",
    "Carismático e falante, conhece quase todos pelo nome.",
    "Reservado e desconfiado de forasteiros, mas justo com os seus.",
    "Ambicioso e atento a oportunidades que beneficiem seu povo.",
    "Calmo mesmo sob pressão, respeitado por sua serenidade.",
]

LEADER_BACKSTORY_POOL = [
    "Assumiu a posição após anos de serviço dedicado à comunidade.",
    "Herdou a responsabilidade de um antecessor que confiava em seu julgamento.",
    "Chegou de outro lugar há anos, mas conquistou a confiança local com o tempo.",
    "Cresceu ali mesmo e nunca considerou viver em outro lugar.",
    "Assumiu o posto em um momento difícil e conseguiu estabilizar a situação.",
]

# Phase 15K — Regional Economy Baseline. Reuses Phase 14 in full
# (SettlementWealthBand, LocalSupplyLevel) — no parallel economy system.
WEALTH_BAND_BY_SETTLEMENT_TYPE = {
    "MAJOR_CITY": "WEALTHY",
    "CITY": "PROSPEROUS",
    "TRADE_SETTLEMENT": "PROSPEROUS",
    "TOWN": "MODEST",
    "MINING_SETTLEMENT": "MODEST",
    "RELIGIOUS_SETTLEMENT": "MODEST",
    "FORTRESS_SETTLEMENT": "MODEST",
    "VILLAGE": "POOR",
    "HAMLET": "POOR",
    "ISOLATED_SETTLEMENT": "POOR",
}

# What each settlement type is locally abundant in (its export good) —
# None means nothing notable to export, a baseline fact, not a gap.
EXPORT_GOOD_BY_SETTLEMENT_TYPE = {
    "MAJOR_CITY": "Bens de Luxo",
    "CITY": "Bens Manufaturados",
    "TRADE_SETTLEMENT": "Mercadorias Diversas",
    "TOWN": "Ferramentas",
    "MINING_SETTLEMENT": "Minério",
    "RELIGIOUS_SETTLEMENT": None,
    "FORTRESS_SETTLEMENT": None,
    "VILLAGE": "Grão",
    "HAMLET": "Grão",
    "ISOLATED_SETTLEMENT": None,
}

# Phase 15L — Regional Threats, Wildlife & Ecology. Population/habitat
# abstraction (threat_type, description) — never individual creatures.
THREAT_POOL = [
    ("WOLVES", "Uma alcateia de lobos ronda a área, especialmente à noite."),
    ("BOARS", "Javalis selvagens são comuns nos arredores, ocasionalmente invadindo plantações próximas."),
    ("BANDITS", "Grupos de bandidos usam o terreno para emboscar viajantes desavisados."),
    ("MONSTERS", "Criaturas incomuns foram avistadas nesta área, cuja natureza exata poucos conseguem descrever."),
    ("HAZARDOUS_TERRAIN", "O próprio terreno representa um perigo — quedas, gelo instável ou terreno traiçoeiro."),
    ("MAGICAL_ANOMALY", "Fenômenos que desafiam explicação comum ocorrem ocasionalmente nesta área."),
]

# Phase 15 follow-up — the starting settlement's 4 hand-authored flavor
# locations (a nearby forest/road/river/clearing) keep their original
# SHAPE (still exactly these 4, still the anchor subregion's own bespoke
# geography rather than the generic 1-feature-per-subregion pool) but
# their proper names/descriptions are now picked per campaign instead of
# being one fixed string forever.
ANCHOR_FOREST_OPTIONS = [
    ("Bosque da Beira do Vale", "A orla mais próxima de uma mata densa que se espessa e escurece em direção ao oeste."),
    ("Mata do Limiar", "Uma faixa de árvores altas que marca a borda das terras cultivadas."),
    ("Floresta do Véu Cinza", "Uma mata cujo dossel fechado deixa a luz sempre difusa e acinzentada."),
]

ANCHOR_ROAD_OPTIONS = [
    ("Estrada do Moinho", "Uma estrada de terra batida que segue a leste da vila rumo às terras altas."),
    ("Caminho dos Mercadores", "Uma via bem batida, usada com frequência por quem viaja entre assentamentos."),
    ("Trilha do Vale", "Um caminho de terra que serpenteia entre os campos rumo ao resto da região."),
]

ANCHOR_RIVER_OPTIONS = [
    ("Riacho Negro", "Um riacho raso de águas escuras ao sul da vila, bom para pescar."),
    ("Ribeirão Claro", "Um curso de água estreito e transparente que corta o terreno baixo."),
    ("Riacho do Junco", "Águas calmas cercadas por juncos altos, favoritas dos pescadores locais."),
]

ANCHOR_CLEARING_OPTIONS = [
    ("Clareira do Vidro Antigo", "Uma clareira silenciosa no fundo da mata, cuja relva estranhamente não é perturbada por animais."),
    ("Clareira do Sol Parado", "Um espaço aberto entre as árvores onde a luz do sol parece durar mais que o normal."),
    ("Clareira Silenciosa", "Um trecho de grama baixa cercado de árvores, estranhamente quieto mesmo durante o dia."),
]

# Phase 15 follow-up — the starting settlement's 3 role-fixed NPCs (an
# elder/leader, a blacksmith, an innkeeper — many earlier-phase tests
# already look these three up BY ROLE as their standard fixture) keep
# their roles, but their names and flavor text are now generated too.
ELDER_FLAVOR_OPTIONS = [
    (
        "Paciente, atento, fala devagar e raramente repete o que diz.",
        "Nasceu em {village}, vive ali há décadas e lidera o conselho da vila há tanto tempo "
        "quanto a maioria dos moradores consegue lembrar.",
    ),
    (
        "Observadora e ponderada, prefere ouvir tudo antes de dar uma opinião.",
        "Assumiu a liderança informal de {village} depois de anos de serviço à comunidade, "
        "e poucos discordam abertamente de suas decisões.",
    ),
]

BLACKSMITH_FLAVOR_OPTIONS = [
    (
        "Direta, trabalhadora, orgulhosa do seu ofício.",
        "Assumiu a forja da família; desconfia de forasteiros que não pagam adiantado.",
    ),
    (
        "Séria e de poucas palavras, mas justa nos preços.",
        "Aprendeu o ofício ainda jovem e nunca considerou fazer outra coisa da vida.",
    ),
]

INNKEEPER_FLAVOR_OPTIONS = [
    (
        "Falante, recolhe fofocas de todo viajante que passa por ali.",
        "Administra a única estalagem de {village}; conhece todos os boatos que circulam por lá.",
    ),
    (
        "Hospitaleiro e curioso sobre quem vem de fora.",
        "Herdou a estalagem da família e trata cada hóspede como uma fonte de boas histórias.",
    ),
]

# Phase 15N — Deep Location Materialization. Generic enough for
# VILLAGE/HAMLET/ISOLATED_SETTLEMENT minor-settlement stubs (Phase 15F
# Tier 2) — filled in only when something (usually the protagonist
# traveling there) actually requires the detail to exist.
MINOR_SETTLEMENT_DESCRIPTIONS = [
    "Um pequeno aglomerado de casas simples, vivendo principalmente da terra ao redor.",
    "Poucas famílias vivem aqui, unidas pelo trabalho diário e pouco mais.",
    "Um povoado modesto, cujas construções de madeira mostram sinais de uso constante.",
    "Um lugar tranquilo, onde forasteiros são raros o suficiente para chamar atenção.",
]

MINOR_SETTLEMENT_FEATURES = [
    ("poço comunitário", "O poço de onde a maior parte da água do povoado é tirada."),
    ("celeiro compartilhado", "Um celeiro simples onde parte da colheita é guardada em conjunto."),
    ("cruzamento de caminhos", "O ponto onde as poucas trilhas locais se encontram."),
]

# Phase 15O — Interiors & Sublocations. Only service types plausible
# enough to have a real "inside" get one; market_square/notice_board/
# mine_entrance/barracks stay as-is (already effectively their own
# interior or exterior by nature).
INTERIOR_DESCRIPTION_BY_SERVICE_TYPE = {
    "inn": "Um salão simples com mesas de madeira gasta e um fogo aceso na maior parte do dia.",
    "tavern": "Ar carregado de fumaça e conversa, bancos e mesas lotados nos horários de maior movimento.",
    "blacksmith": "Calor da forja, ferramentas penduradas nas paredes e o som constante do martelo sobre a bigorna.",
    "shop": "Prateleiras apertadas com mercadorias variadas, um balcão de madeira perto da entrada.",
    "temple": "Um espaço silencioso e penumbroso, com um pequeno altar ao fundo.",
    "warehouse": "Fileiras de caixas e sacos empilhados, o ar pesado com cheiro de madeira e poeira.",
}

SUBREGION_ECONOMY_SUMMARIES = [
    "A economia local depende quase inteiramente da agricultura de subsistência.",
    "Pequenas operações de extração (madeira, pedra ou minério) sustentam a maior parte do comércio.",
    "Caravanas que cruzam a área deixam boa parte da renda local, ainda que passageira.",
    "A criação de gado é a principal fonte de riqueza, com pastagens extensas.",
    "Pesca e outras atividades ligadas à água sustentam a maioria dos assentamentos próximos.",
    "O artesanato especializado é exportado para assentamentos maiores da região.",
    "A economia é modesta e majoritariamente voltada ao próprio sustento, com pouco excedente.",
    "Um recurso local específico (minério, madeira rara, sal) atrai comerciantes de fora.",
]
