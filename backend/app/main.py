from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import (
    actions,
    campaigns,
    character,
    inventory,
    journal,
    map as map_routes,
    quests,
    state,
    story,
    visual_assets,
)
from app.core.config import get_settings
from app.core.logging import configure_logging

settings = get_settings()
configure_logging(settings.log_level)

app = FastAPI(title="Everreach — Game API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(campaigns.router)
app.include_router(state.router)
app.include_router(actions.router)
app.include_router(map_routes.router)
app.include_router(inventory.router)
app.include_router(character.router)
app.include_router(quests.router)
app.include_router(journal.router)
app.include_router(story.router)
app.include_router(visual_assets.router)


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok"}
