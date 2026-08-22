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
