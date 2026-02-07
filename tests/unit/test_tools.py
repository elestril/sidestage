import pytest
from pathlib import Path
from sidestage.tools import WorldTools
from sidestage.storage import Storage

@pytest.mark.anyio
async def test_world_tools_wrapper(tmp_path: Path):
    """Test the WorldTools wrapper logic separately (Storage fallback path)."""
    storage = Storage(db_path=tmp_path / "world.db")
    tools = WorldTools(storage=storage)

    # Test create
    resp = await tools.create_character("TestCharacter", "A test guy")
    assert "TestCharacter" in resp
    npc_data = storage.list_characters()[0]
    assert npc_data.name == "TestCharacter"
    character_id = npc_data.id

    # Update
    update_resp = await tools.update_character(character_id, body="Updated body")
    assert "Updated body" in update_resp

    updated_char = storage.get_character(character_id)
    assert updated_char is not None
    assert updated_char.body == "Updated body"

    # Test list
    list_resp = await tools.list_characters()
    assert "TestCharacter" in list_resp
