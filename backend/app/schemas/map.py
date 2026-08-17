from pydantic import BaseModel


class MapRegion(BaseModel):
    id: str
    name: str
    description: str
    discovery_status: str

class MapLocation(BaseModel):
    id: str
    region_id: str
    name: str
    type: str
    x: int
    y: int
    discovery_status: str

class MapConnection(BaseModel):
    from_location_id: str
    to_location_id: str
    direction: str | None
    connection_type: str
    distance: float
    danger: int
    travel_time_modifier: float

class MapResponse(BaseModel):
    regions: list[MapRegion]
    locations: list[MapLocation]
    connections: list[MapConnection]
