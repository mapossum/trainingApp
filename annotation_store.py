import os
import json

import config


def _annotation_path(area_id):
    return os.path.join(config.ANNOTATIONS_DIR, f"{area_id}.geojson")


def load_annotations(area_id):
    """Load annotations for an area. Returns a GeoJSON FeatureCollection dict."""
    path = _annotation_path(area_id)
    if os.path.exists(path):
        with open(path, 'r') as f:
            return json.load(f)
    return {
        "type": "FeatureCollection",
        "properties": {"area_id": area_id},
        "features": []
    }


def save_annotations(area_id, feature_collection):
    """Save a GeoJSON FeatureCollection for an area."""
    feature_collection.setdefault("properties", {})
    feature_collection["properties"]["area_id"] = area_id
    path = _annotation_path(area_id)
    with open(path, 'w') as f:
        json.dump(feature_collection, f, indent=2)


def get_annotation_count(area_id):
    """Return the number of features in an area's annotations."""
    path = _annotation_path(area_id)
    if not os.path.exists(path):
        return 0
    try:
        with open(path, 'r') as f:
            data = json.load(f)
        return len(data.get("features", []))
    except Exception:
        return 0


def load_state():
    """Load app state (completion flags, last viewed, sort preference)."""
    if os.path.exists(config.STATE_PATH):
        with open(config.STATE_PATH, 'r') as f:
            return json.load(f)
    return {"last_viewed": None, "complete": {}, "sort_by": "ortho_name"}


def save_state(state):
    """Save app state."""
    with open(config.STATE_PATH, 'w') as f:
        json.dump(state, f, indent=2)


def update_state(updates):
    """Merge updates into existing state."""
    state = load_state()
    for key, value in updates.items():
        if key == "complete" and isinstance(value, dict):
            state.setdefault("complete", {}).update(value)
        else:
            state[key] = value
    save_state(state)
    return state
