"""Capabilities are independent; registering an animal does not enable medical advice."""
import json
from pathlib import Path

SPECIES = json.loads((Path(__file__).resolve().parents[1] / "data/species.json").read_text(encoding="utf-8"))


def registry():
    return [
        {**item, "capabilities": {
            "profile": True, "manual_logs": True,
            "knowledge": False, "care_plan": False, "nutrition": False, "emergency_rules": False,
            **item.get("capabilities", {}),
        }} for item in SPECIES
    ]


def supports(species, capability):
    item = next((s for s in registry() if s["id"] == species), None)
    return bool(item and item["capabilities"].get(capability))
