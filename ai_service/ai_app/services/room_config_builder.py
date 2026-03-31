from typing import Dict, List, Any
import json

def build_config_from_entities(entity_ids: Any) -> Dict[str, List[str]]:
    config = {
        "lights": [],
        "climate": [],
        "covers": [],
        "motion": [],
    }

    if entity_ids is None:
        return config

    # If stored wrongly as a string: '["light.x", "climate.y"]'
    if isinstance(entity_ids, str):
        try:
            entity_ids = json.loads(entity_ids)
        except Exception:
            entity_ids = [entity_ids]

    # If still not a list/tuple, coerce
    if not isinstance(entity_ids, (list, tuple)):
        entity_ids = [entity_ids]

    for entity in entity_ids:
        if not isinstance(entity, str) or "." not in entity:
            continue

        domain, _ = entity.split(".", 1)

        if domain == "light":
            config["lights"].append(entity)
        elif domain == "climate":
            config["climate"].append(entity)
        elif domain == "cover":
            config["covers"].append(entity)
        elif domain == "binary_sensor":
            config["motion"].append(entity)

    return config