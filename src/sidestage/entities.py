import yaml
import re
from typing import Dict, Any, Type, Optional
from sidestage.models import (
    EntityModel,
    CharacterModel,
    LocationModel,
    ItemModel,
    SceneModel,
    EventModel,
    EventType,
)


def entity_to_markdown(entity: EntityModel) -> str:
    """
    Serializes an Entity to a standardized Markdown format with YAML frontmatter.
    """
    data = entity.model_dump(mode="json")
    body = data.pop("body", "")

    # Ensure type is explicitly in the frontmatter for easier identification
    data["type"] = entity.entity_type

    # Sort keys for consistent output, but keep name and id at the top if possible
    ordered_data = {}
    for key in ["name", "id", "type"]:
        if key in data:
            ordered_data[key] = data.pop(key)
    ordered_data.update(data)

    frontmatter = yaml.dump(ordered_data, sort_keys=False).strip()
    return f"---\n{frontmatter}\n---\n\n{body}"

def markdown_to_entity(content: str, override_id: Optional[str] = None) -> EntityModel:
    """
    Parses a Markdown string with YAML frontmatter into an Entity object.
    If override_id is provided, it is used as the entity ID, overriding any ID in the frontmatter.
    """
    pattern = re.compile(r"^---\s*\n(.*?)\n---\s*\n(.*)$", re.DOTALL)
    match = pattern.match(content.strip())

    if not match:
        raise ValueError("Invalid format: Missing YAML frontmatter or body")

    frontmatter_raw = match.group(1)
    body = match.group(2).strip()

    data = yaml.safe_load(frontmatter_raw)
    if not isinstance(data, dict):
        raise ValueError("Invalid YAML frontmatter")

    data["body"] = body
    if override_id:
        data["id"] = override_id

    entity_type = data.get("type", "Character")

    type_map: Dict[str, Type[EntityModel]] = {
        "Character": CharacterModel,
        "Location": LocationModel,
        "Item": ItemModel,
        "Scene": SceneModel,
        "Event": EventModel,
        "Entity": EntityModel,
        "ChatMessage": EventModel,
        "JoinEvent": EventModel,
        "LeaveEvent": EventModel,
        "AdjustGametime": EventModel,
        "Error": EventModel,
    }

    model_cls = type_map.get(entity_type, EntityModel)
    # Remove 'type' from data as it's not a field in the models
    if "type" in data:
        del data["type"]

    # If type was an EventType value, ensure event_type is set
    if model_cls is EventModel and "event_type" not in data:
        event_type_values = {et.value for et in EventType}
        if entity_type in event_type_values:
            data["event_type"] = entity_type

    return model_cls(**data)
