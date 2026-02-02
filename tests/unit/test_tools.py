import pytest
from sidestage.tools import WorldTools
from sidestage.storage import Storage

def test_world_tools_wrapper(tmp_path):
    """Test the WorldTools wrapper logic separately."""
    storage = Storage(db_path=tmp_path / "world.db")
    tools = WorldTools(storage=storage)
    
    # Test create
    resp = tools.create_npc("TestNPC", "A test guy")
    assert "TestNPC" in resp
    npc_data = storage.list_npcs()[0]
    npc_id = npc_data.id
    
    # Update
    update_resp = tools.update_npc(npc_id, body="Updated body")
    assert "Updated body" in update_resp
    
    updated_npc = storage.get_npc(npc_id)
    assert updated_npc is not None
    assert updated_npc.body == "Updated body"
    
    # Test list
    list_resp = tools.list_npcs()
    assert "TestNPC" in list_resp
