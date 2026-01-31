import pytest
from sidestage.time import Gametime
from sidestage.models import Scene, Event
from sidestage.storage import Storage
from agno.db.sqlite import SqliteDb

def test_gametime_conversion():
    gt = Gametime(seconds=3600) # 1 hour
    assert gt.to_string() == "Day 0, 01:00:00"
    
    gt2 = Gametime.from_string("Day 1, 12:00:00")
    assert gt2.seconds == (24 * 3600) + (12 * 3600)
    assert gt2.to_string() == "Day 1, 12:00:00"

def test_scene_crud(tmp_path):
    db_file = tmp_path / "test.db"
    db = SqliteDb(db_file=str(db_file))
    storage = Storage(db=db)
    
    scene = Scene(
        id="scene_1",
        name="Test Scene",
        description="A test scene",
        current_gametime=3600
    )
    
    storage.add_scene(scene)
    retrieved = storage.get_scene("scene_1")
    assert retrieved.name == "Test Scene"
    assert retrieved.current_gametime == 3600
    
    scenes = storage.list_scenes()
    assert len(scenes) == 1
    assert scenes[0].id == "scene_1"

def test_event_storage(tmp_path):
    db_file = tmp_path / "test.db"
    db = SqliteDb(db_file=str(db_file))
    storage = Storage(db=db)
    
    event = Event(
        id="event_1",
        name="Test Event",
        scene_id="scene_1",
        gametime=3600,
        walltime="2026-01-30T22:30:00",
        description="Something happened"
    )
    
    storage.add_event(event)
    # We don't have get_event yet but we verified it doesn't crash
