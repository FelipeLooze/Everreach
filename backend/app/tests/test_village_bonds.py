"""Starting village, part 3: family, master and apprentice, friends and
rivals — shared surnames, ages that add up, and every villager able to talk
about the others without the narrator inventing relatives."""

from app.db.models.npc import NPC
from app.db.models.npc_bond import NPCBond
from app.game.character.service import create_character
from app.game.npcs import bonds, profile
from app.game.world.seed import create_campaign, seed_initial_region


def _village(db_session):
    campaign = create_campaign(db_session, "Laços")
    region, village = seed_initial_region(db_session, campaign.id)
    create_character(db_session, campaign.id, "Logan", region.id, village.id)
    db_session.flush()
    people = db_session.query(NPC).filter(NPC.campaign_id == campaign.id, NPC.location_id == village.id).all()
    return campaign, village, people


def _role(people, prefix):
    return next(npc for npc in people if npc.role.startswith(prefix))


def _surname(npc):
    return npc.name.split(" ", 1)[1]


def test_family_shares_a_surname_and_the_ages_add_up(db_session):
    campaign, _settlement, people = _village(db_session)
    ties = db_session.query(NPCBond).filter(NPCBond.campaign_id == campaign.id).all()
    kinds = sorted(tie.kind for tie in ties)
    assert kinds.count(bonds.RIVALS) == 2 and kinds.count(bonds.PARENT) == 3

    for tie in ties:
        a, b = db_session.get(NPC, tie.first_npc_id), db_session.get(NPC, tie.second_npc_id)
        if tie.kind in (bonds.PARENT, bonds.SPOUSES, bonds.SIBLINGS):
            assert _surname(a) == _surname(b), (tie.kind, a.name, b.name)
        if tie.kind == bonds.PARENT:
            assert a.age >= b.age + 20

    teen = _role(people, "rapaz curioso") if any(n.role.startswith("rapaz") for n in people) else _role(people, "moça")
    assert _surname(teen) == _surname(_role(people, "agricultor"))
    names = [npc.name for npc in people]
    assert len(names) == len(set(names))


def test_a_villager_knows_their_own_ties_and_the_village_gossip(db_session):
    _campaign, _settlement, people = _village(db_session)
    apprentice = _role(people, "aprendiz")
    woodcutter = _role(people, "lenhador")

    lines = "\n".join(profile.context_lines(db_session, apprentice, trust=0))
    assert f"pai: {woodcutter.name} (lenhador)" in lines
    assert "no other relatives than those listed" in lines
    assert "these are ALL of them" in lines

    elder = _role(people, "ancião")
    elder_lines = "\n".join(profile.context_lines(db_session, elder, trust=0))
    assert "Family: none" in elder_lines
    assert f"{woodcutter.name} (lenhador) é pai de {apprentice.name}" in elder_lines
    assert "rivais — o lenhador derruba as árvores" in elder_lines


def test_deleting_the_campaign_removes_the_bonds(db_session):
    from app.game.world.reset import delete_campaign

    campaign, _settlement, _people = _village(db_session)
    assert delete_campaign(db_session, campaign.id)
    assert db_session.query(NPCBond).count() == 0


def test_unrelated_villagers_never_share_a_surname(db_session):
    campaign, _settlement, people = _village(db_session)
    family = {}
    for tie in db_session.query(NPCBond).filter(NPCBond.campaign_id == campaign.id):
        if tie.kind in (bonds.PARENT, bonds.SPOUSES, bonds.SIBLINGS):
            family.setdefault(tie.first_npc_id, set()).add(tie.second_npc_id)
            family.setdefault(tie.second_npc_id, set()).add(tie.first_npc_id)

    def related(a, b):  # through any chain of family ties
        seen, todo = {a}, [a]
        while todo:
            for other in family.get(todo.pop(), ()):
                if other not in seen:
                    seen.add(other)
                    todo.append(other)
        return b in seen

    for a in people:
        for b in people:
            if a.id < b.id and _surname(a) == _surname(b):
                assert related(a.id, b.id), (a.name, a.role, b.name, b.role)
