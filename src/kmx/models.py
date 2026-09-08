"""KMX levels and validated KMX identifiers.

Only KMX-ING, KMX-CD and KMX-PROD exist. The numeric portion of a KMX ID
never carries clinical meaning.
"""

import re
from dataclasses import dataclass

from .exceptions import KemirixError


class KmxLevel:
    """The three frozen KMX levels (namespace-safe constants, not an enum).

    Kept as simple class constants because the level vocabulary is also the
    join/truth level vocabulary; a single definition avoids enum duplication
    across evidence and rules.
    """

    INGREDIENT = "ingredient"
    CLINICAL_DRUG = "clinical_drug"
    PRODUCT = "product"
    ALL = (INGREDIENT, CLINICAL_DRUG, PRODUCT)

    def __new__(cls):
        raise TypeError("KmxLevel is a constants namespace, not instantiable")


LEVEL_PREFIXES = {
    KmxLevel.INGREDIENT: "KMX-ING",
    KmxLevel.CLINICAL_DRUG: "KMX-CD",
    KmxLevel.PRODUCT: "KMX-PROD",
}
PREFIX_LEVELS = {"ING": KmxLevel.INGREDIENT, "CD": KmxLevel.CLINICAL_DRUG, "PROD": KmxLevel.PRODUCT}

KMX_ID_PATTERN = re.compile(r"^KMX-(ING|CD|PROD)-[0-9]{6}$")


def is_valid_kmx_id(value):
    """True only for KMX-(ING|CD|PROD)-###### identifiers."""
    return isinstance(value, str) and bool(KMX_ID_PATTERN.fullmatch(value))


@dataclass(frozen=True)
class KmxId:
    """A validated KMX identifier value object."""

    value: str

    def __post_init__(self):
        if not is_valid_kmx_id(self.value):
            raise KemirixError(f"invalid KMX id: {self.value!r}")

    @property
    def level(self):
        return PREFIX_LEVELS[self.value.split("-")[1]]

    @classmethod
    def build(cls, level, number):
        prefix = LEVEL_PREFIXES.get(level)
        if prefix is None or level not in KmxLevel.ALL:
            raise KemirixError(f"unsupported KMX level: {level!r}")
        if not isinstance(number, int) or not 0 <= number <= 999_999:
            raise KemirixError(f"invalid KMX sequence: {number!r}")
        return cls(f"{prefix}-{number:06d}")

    def __str__(self):
        return self.value
