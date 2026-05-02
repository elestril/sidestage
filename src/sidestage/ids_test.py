import pytest

from sidestage.ids import CampaignId, CharacterId, MessageId, SceneId


def test_id_wraps_string_value_and_exposes_it():
    assert CampaignId("camp1").value == "camp1", (
        "CampaignId must wrap a string and expose it via .value; "
        "expected CampaignId('camp1').value == 'camp1'"
    )
    assert SceneId("scene1").value == "scene1", (
        "SceneId must wrap a string and expose it via .value; "
        "expected SceneId('scene1').value == 'scene1'"
    )
    assert CharacterId("bob").value == "bob", (
        "CharacterId must wrap a string and expose it via .value; "
        "expected CharacterId('bob').value == 'bob'"
    )
    assert MessageId("m1").value == "m1", (
        "MessageId must wrap a string and expose it via .value; "
        "expected MessageId('m1').value == 'm1'"
    )


def test_same_type_same_value_are_equal():
    assert CharacterId("bob") == CharacterId("bob"), (
        "Two IDs of the same type with the same string value must compare equal; "
        "expected CharacterId('bob') == CharacterId('bob')"
    )
    assert SceneId("s") == SceneId("s"), (
        "Two SceneIds with the same value must compare equal"
    )
    assert CampaignId("c") == CampaignId("c"), (
        "Two CampaignIds with the same value must compare equal"
    )
    assert MessageId("m") == MessageId("m"), (
        "Two MessageIds with the same value must compare equal"
    )


def test_different_id_types_with_same_string_are_not_equal():
    assert CharacterId("bob") != SceneId("bob"), (
        "IDs of different types must not be equal even with identical string values; "
        "CharacterId('bob') must not equal SceneId('bob')"
    )
    assert CampaignId("x") != MessageId("x"), (
        "CampaignId('x') must not equal MessageId('x') - different ID types are distinct"
    )
    assert SceneId("y") != CampaignId("y"), (
        "SceneId('y') must not equal CampaignId('y') - different ID types are distinct"
    )
    assert CharacterId("z") != MessageId("z"), (
        "CharacterId('z') must not equal MessageId('z') - different ID types are distinct"
    )


def test_id_types_are_hashable_and_usable_as_dict_keys():
    d = {
        CampaignId("c1"): "campaign",
        SceneId("s1"): "scene",
        CharacterId("ch1"): "character",
        MessageId("m1"): "message",
    }
    assert d[CampaignId("c1")] == "campaign", (
        "CampaignId must be hashable and equal instances must retrieve the same dict value"
    )
    assert d[SceneId("s1")] == "scene", (
        "SceneId must be hashable and equal instances must retrieve the same dict value"
    )
    assert d[CharacterId("ch1")] == "character", (
        "CharacterId must be hashable and equal instances must retrieve the same dict value"
    )
    assert d[MessageId("m1")] == "message", (
        "MessageId must be hashable and equal instances must retrieve the same dict value"
    )
    s = {CharacterId("a"), CharacterId("a"), CharacterId("b")}
    assert len(s) == 2, (
        "Hashable IDs with equal value must collapse in a set; "
        "expected {CharacterId('a'), CharacterId('a'), CharacterId('b')} to have length 2"
    )
