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
