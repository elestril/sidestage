from datetime import datetime, timedelta, timezone
import pytest
from pathlib import Path
from sidestage.time import Gametime
from sidestage.models import SceneModel, EventModel, EventType
from sidestage.storage import Storage


class TestGametimeConversion:
    def test_from_seconds_and_str(self):
        gt = Gametime.from_seconds(3600)  # 1 hour
        assert str(gt) == "Day 0, 01:00:00"

    def test_from_string(self):
        gt = Gametime.from_string("Day 1, 12:00:00")
        assert gt.total_seconds() == (24 * 3600) + (12 * 3600)
        assert str(gt) == "Day 1, 12:00:00"

    def test_round_trip(self):
        for secs in [0, 1, 59, 3600, 86400, 90061, 999999]:
            gt = Gametime.from_seconds(secs)
            assert gt.total_seconds() == secs
            assert Gametime.from_string(str(gt)).total_seconds() == secs

    def test_zero(self):
        gt = Gametime.from_seconds(0)
        assert str(gt) == "Day 0, 00:00:00"
        assert gt.total_seconds() == 0

    def test_convenience_constructor(self):
        gt = Gametime(seconds=7200)
        assert gt.total_seconds() == 7200
        assert str(gt) == "Day 0, 02:00:00"

    def test_isinstance_datetime(self):
        gt = Gametime.from_seconds(0)
        assert isinstance(gt, datetime)

    def test_repr(self):
        gt = Gametime.from_seconds(3600)
        assert repr(gt) == "Gametime(seconds=3600)"


class TestGametimeArithmetic:
    def test_add_timedelta(self):
        gt = Gametime.from_seconds(3600)
        result = gt + timedelta(hours=1)
        assert isinstance(result, Gametime)
        assert result.total_seconds() == 7200

    def test_sub_timedelta(self):
        gt = Gametime.from_seconds(7200)
        result = gt - timedelta(hours=1)
        assert isinstance(result, Gametime)
        assert result.total_seconds() == 3600

    def test_sub_gametime_returns_timedelta(self):
        gt1 = Gametime.from_seconds(7200)
        gt2 = Gametime.from_seconds(3600)
        result = gt1 - gt2
        assert isinstance(result, timedelta)
        assert result.total_seconds() == 3600

    def test_radd(self):
        gt = Gametime.from_seconds(3600)
        result = timedelta(hours=1) + gt
        assert isinstance(result, Gametime)
        assert result.total_seconds() == 7200


class TestGametimeEdgeCases:
    def test_from_string_invalid_raises(self):
        with pytest.raises(ValueError, match="Invalid gametime format"):
            Gametime.from_string("not a time")

    def test_large_value(self):
        secs = 365 * 24 * 3600  # 1 year
        gt = Gametime.from_seconds(secs)
        assert gt.total_seconds() == secs
        assert str(gt).startswith("Day 365,")


def test_scene_crud(tmp_path: Path):
    storage = Storage(db_path=tmp_path / "test.db")

    scene = SceneModel(
        id="scene_1",
        name="Test SceneModel",
        body="A test scene",
        current_gametime=3600
    )

    storage.add_scene(scene)
    retrieved = storage.get_scene("scene_1")
    assert retrieved is not None
    assert retrieved.name == "Test SceneModel"
    assert retrieved.current_gametime == 3600

    scenes = storage.list_scenes()
    assert len(scenes) == 1
    assert scenes[0].id == "scene_1"

def test_event_storage(tmp_path: Path):
    storage = Storage(db_path=tmp_path / "test.db")

    event = EventModel(
        id="event_1",
        name="Test EventModel",
        scene_id="scene_1",
        gametime=3600,
        walltime=datetime.fromisoformat("2026-01-30T22:30:00"),
        body="Something happened",
        event_type=EventType.CHAT_MESSAGE,
    )

    storage.add_event(event)
    # We don't have get_event yet but we verified it doesn't crash
