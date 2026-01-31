import yaml
import re
from typing import Dict, Any, Type, Optional
from sidestage.models import Entity, NPC, Location, Item, Scene, Event

def entity_to_markdown(entity: Entity) -> str:
    """
    Serializes an Entity to a standardized Markdown format with YAML frontmatter.
    """
    data = entity.model_dump()
    body = data.pop("body", "")
    
    # Ensure type is explicitly in the frontmatter for easier identification
    data["type"] = entity.__class__.__name__
    
    # Sort keys for consistent output, but keep name and id at the top if possible
    ordered_data = {}
    for key in ["name", "id", "type"]:
        if key in data:
            ordered_data[key] = data.pop(key)
    ordered_data.update(data)
    
    frontmatter = yaml.dump(ordered_data, sort_keys=False).strip()
    return f"---\n{frontmatter}\n---\n\n{body}"

def markdown_to_entity(content: str) -> Entity:
    """
    Parses a Markdown string with YAML frontmatter into an Entity object.
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
    entity_type = data.get("type", "Entity")
    
    type_map: Dict[str, Type[Entity]] = {
        "NPC": NPC,
        "Location": Location,
        "Item": Item,
        "Scene": Scene,
        "Event": Event,
        "Entity": Entity
    }
    
    model_cls = type_map.get(entity_type, Entity)
    # Remove 'type' from data as it's not a field in the models
    if "type" in data:
        del data["type"]
        
    return model_cls(**data)
