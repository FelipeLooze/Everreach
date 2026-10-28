"""Refresh derived response views from existing receipts; never replay a transfer.

The historical receipts and plant states remain authoritative. This only updates
technical JSON with the current inventory precision when reviewing an old proof.
"""
import json
from dataclasses import asdict
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from scripts.validate_plant_resources import OUT
from app.db.models.item import ItemInstance
from app.db.models.world_vegetation import GenesisPlantIndividual
from app.game.items.containers import get_item_unit_weight
from app.game.items.encumbrance import get_character_encumbrance


def main():
    for seed in (42,0,7,2026,12345):
        p=OUT/f"seed-{seed}-proof.json";data=json.loads(p.read_text(encoding="utf-8"))
        engine=create_engine("sqlite:///"+str(OUT/f"seed-{seed}-proof.sqlite"))
        with Session(engine) as db:
            for record in data["records"]:
                ind=db.get(GenesisPlantIndividual,(data["campaign_id"],record["individual_id"]))
                assert ind.state==record["reopened_state"]
                lot=db.get(ItemInstance,record["receipt"]["item_instance_id"])
                assert lot.quantity==1
                record["inventory_weight"]=get_item_unit_weight(db,lot)
                record["receipt"]["encumbrance"]=asdict(get_character_encumbrance(db,record["actor_id"]))
        engine.dispose();p.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding="utf-8")
    print("Five existing proof views refreshed; plant states and transfers unchanged",flush=True)


if __name__=="__main__":main()
