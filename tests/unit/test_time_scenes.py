import pytest
from pathlib import Path
from sidestage.time import Gametime
from sidestage.models import SceneModel, EventModel, EventType
from sidestage.storage import Storage

def test_gametime_conversion():
    gt = Gametime(seconds=3600) # 1 hour
    assert gt.to_string() == "Day 0, 01:00:00"
    
    gt2 = Gametime.from_string("Day 1, 12:00:00")
    assert gt2.seconds == (24 * 3600) + (12 * 3600)
    assert gt2.to_string() == "Day 1, 12:00:00"

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
        walltime="2026-01-30T22:30:00",
        body="Something happened",
        event_type=EventType.CHAT_MESSAGE,
    )
    
    storage.add_event(event)
    # We don't have get_event yet but we verified it doesn't crash
