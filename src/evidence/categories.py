"""The 24 shared clinical Evidence categories (frozen contract)."""

from pathlib import Path

import yaml

from kmx.exceptions import ConfigurationError

CATEGORY_VALUES = (
    "indication",
    "contraindication",
    "drug_disease",
    "drug_drug",
    "drug_food_substance",
    "allergy_hypersensitivity",
    "dosing",
    "renal",
    "hepatic",
    "paediatric",
    "geriatric",
    "pregnancy",
    "lactation",
    "laboratory",
    "vital_signs",
    "monitoring",
    "adverse_effects",
    "duplication",
    "polypharmacy",
    "administration",
    "high_alert_safety",
    "pharmacogenomic",
    "treatment_appropriateness",
    "counselling",
)
assert len(CATEGORY_VALUES) == 24


class EvidenceCategory:
    """The frozen category vocabulary.

    follow_up is Evidence content, not a 25th category.
    """

    __slots__ = tuple(CATEGORY_VALUES) + ("ALL",)

    def __init__(self):
        raise TypeError("EvidenceCategory is a constants namespace; use is_valid/parse")

    @classmethod
    def parse(cls, value):
        if value not in CATEGORY_VALUES:
            raise ConfigurationError(f"unknown Evidence category: {value!r}")
        return value

    @classmethod
    def is_valid(cls, value):
        return value in CATEGORY_VALUES


def load_categories(root):
    """Load config/categories.yaml and fail closed unless it equals the frozen set."""
    path = Path(root) / "config/categories.yaml"
    data = yaml.safe_load(path.read_text()) or {}
    categories = data.get("categories")
    if categories != list(CATEGORY_VALUES):
        raise ConfigurationError("config/categories.yaml does not match the frozen 24 categories")
    return tuple(categories)
