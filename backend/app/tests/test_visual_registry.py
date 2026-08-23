"""Phase 21N — Canon Entity Visual Metadata."""

from app.game.visual.registry import VISUAL_SUBJECT_KINDS, describe_visual_subject_kind

_KINDS_ACTUALLY_USED_ACROSS_VISUAL_MODULES = {
    "npc", "item_definition", "location", "settlement", "region", "subregion",
    "organization", "threat_species", "regional_threat",
}


def test_registry_covers_every_subject_kind_actually_used_by_the_visual_modules():
    registered_keys = {kind.key for kind in VISUAL_SUBJECT_KINDS}

    assert registered_keys == _KINDS_ACTUALLY_USED_ACROSS_VISUAL_MODULES


def test_registry_has_no_duplicate_keys():
    keys = [kind.key for kind in VISUAL_SUBJECT_KINDS]

    assert len(keys) == len(set(keys))


def test_describe_visual_subject_kind_returns_the_matching_entry():
    entry = describe_visual_subject_kind("npc")

    assert entry is not None
    assert entry.campaign_scoped is True


def test_describe_visual_subject_kind_reflects_campaign_global_subjects():
    entry = describe_visual_subject_kind("item_definition")

    assert entry is not None
    assert entry.campaign_scoped is False


def test_describe_visual_subject_kind_returns_none_for_an_unregistered_kind():
    assert describe_visual_subject_kind("not_a_real_kind") is None
