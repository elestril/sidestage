from sidestage.ids import CharacterId, SceneId
from sidestage.message import Message
from sidestage.message_repository import InMemoryMessageRepository


async def test_append_then_get_by_scene_returns_list_containing_message():
    repo = InMemoryMessageRepository()
    msg = Message.create(SceneId("scene1"), CharacterId("hero"), "hello")

    await repo.append(msg)
    result = await repo.get_by_scene(msg.scene_id)

    assert isinstance(result, list), (
        "InMemoryMessageRepository.get_by_scene must return a list; got "
        f"{type(result).__name__}."
    )
    assert msg in result, (
        "After awaiting repo.append(msg), awaiting repo.get_by_scene(msg.scene_id) "
        "must return a list containing msg. Expected the appended Message to be "
        f"present in the result, but got {result!r}."
    )


async def test_get_by_scene_returns_messages_in_insertion_order():
    repo = InMemoryMessageRepository()
    scene = SceneId("scene1")
    msg1 = Message.create(scene, CharacterId("hero"), "first")
    msg2 = Message.create(scene, CharacterId("hero"), "second")
    msg3 = Message.create(scene, CharacterId("villain"), "third")

    await repo.append(msg1)
    await repo.append(msg2)
    await repo.append(msg3)
    result = await repo.get_by_scene(scene)

    assert result == [msg1, msg2, msg3], (
        "InMemoryMessageRepository.get_by_scene must return messages in the order "
        "they were appended (insertion order). After appending msg1, msg2, msg3 to "
        "the same scene, expected get_by_scene to return [msg1, msg2, msg3] but "
        f"got {result!r}."
    )


async def test_get_by_scene_returns_empty_list_when_no_messages_for_scene():
    repo = InMemoryMessageRepository()

    result = await repo.get_by_scene(SceneId("nonexistent"))

    assert result == [], (
        "InMemoryMessageRepository.get_by_scene must return an empty list when no "
        "messages exist for the given scene_id. Expected [] for an unknown scene "
        f"but got {result!r}."
    )


async def test_get_by_scene_returns_empty_list_when_other_scenes_have_messages():
    repo = InMemoryMessageRepository()
    other_msg = Message.create(SceneId("other"), CharacterId("hero"), "hi")
    await repo.append(other_msg)

    result = await repo.get_by_scene(SceneId("target"))

    assert result == [], (
        "InMemoryMessageRepository.get_by_scene must return an empty list for a "
        "scene_id that has no appended messages, even when other scenes do contain "
        f"messages. Expected [] for SceneId('target') but got {result!r}."
    )


async def test_get_by_scene_filters_by_scene_id():
    repo = InMemoryMessageRepository()
    scene_a = SceneId("scene_a")
    scene_b = SceneId("scene_b")
    msg_a1 = Message.create(scene_a, CharacterId("hero"), "a1")
    msg_b1 = Message.create(scene_b, CharacterId("hero"), "b1")
    msg_a2 = Message.create(scene_a, CharacterId("villain"), "a2")
    msg_b2 = Message.create(scene_b, CharacterId("villain"), "b2")

    await repo.append(msg_a1)
    await repo.append(msg_b1)
    await repo.append(msg_a2)
    await repo.append(msg_b2)

    result_a = await repo.get_by_scene(scene_a)
    result_b = await repo.get_by_scene(scene_b)

    assert result_a == [msg_a1, msg_a2], (
        "InMemoryMessageRepository.get_by_scene must return only messages whose "
        "scene_id matches the requested SceneId, preserving insertion order. For "
        f"scene_a expected [msg_a1, msg_a2] but got {result_a!r}."
    )
    assert result_b == [msg_b1, msg_b2], (
        "InMemoryMessageRepository.get_by_scene must return only messages whose "
        "scene_id matches the requested SceneId, preserving insertion order. For "
        f"scene_b expected [msg_b1, msg_b2] but got {result_b!r}."
    )
    assert msg_b1 not in result_a and msg_b2 not in result_a, (
        "InMemoryMessageRepository.get_by_scene(scene_a) must NOT include messages "
        f"whose scene_id is scene_b. Got {result_a!r} which leaked scene_b messages."
    )
    assert msg_a1 not in result_b and msg_a2 not in result_b, (
        "InMemoryMessageRepository.get_by_scene(scene_b) must NOT include messages "
        f"whose scene_id is scene_a. Got {result_b!r} which leaked scene_a messages."
    )
