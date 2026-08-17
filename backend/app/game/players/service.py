from sqlalchemy.orm import Session

from app.db.models.simulated_player import SimulatedPlayer


def simulated_players_at_location(db: Session, location_id: str) -> list[SimulatedPlayer]:
    return db.query(SimulatedPlayer).filter(SimulatedPlayer.location_id == location_id).all()


def simulated_players_in_campaign(db: Session, campaign_id: str) -> list[SimulatedPlayer]:
    return db.query(SimulatedPlayer).filter(SimulatedPlayer.campaign_id == campaign_id).all()
