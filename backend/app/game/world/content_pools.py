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

# Phase 15C — "Campos de Cardal" is the fixed anchor subregion containing
# the pinned starting village (see 15B); every other name here is a pool
# candidate for the rest of the massive region and may or may not be
# selected for a given campaign's generation_seed.
ANCHOR_SUBREGION_NAME = "Campos de Cardal"

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
# anchor subregion's own settlement (Cardal) is hand-authored, not
# generated from this pool.
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
    "MAJOR_CITY": ["market_square", "inn", "tavern", "temple", "general_store", "barracks", "notice_board"],
    "CITY": ["market_square", "inn", "tavern", "temple", "general_store", "notice_board"],
    "TOWN": ["inn", "tavern", "general_store", "notice_board"],
    "VILLAGE": ["inn", "general_store", "notice_board"],
    "HAMLET": ["notice_board"],
    "ISOLATED_SETTLEMENT": [],
    "FORTRESS_SETTLEMENT": ["barracks", "inn", "notice_board"],
    "MINING_SETTLEMENT": ["mine_entrance", "warehouse", "tavern", "notice_board"],
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
