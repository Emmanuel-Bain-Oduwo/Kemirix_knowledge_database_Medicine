"""Rule evaluation outcomes (frozen contract).

Missing required patient data returns CANNOT_FULLY_EVALUATE, never NO_MATCH.
Wrong formulation or product returns NO_MATCH for clinical drug/product Rules.
"""

from kmx.exceptions import ConfigurationError

OUTCOME_VALUES = ("MATCH", "NO_MATCH", "CANNOT_FULLY_EVALUATE")


class RuleOutcome:
    """The exact three Rule evaluation outcomes."""

    MATCH, NO_MATCH, CANNOT_FULLY_EVALUATE = OUTCOME_VALUES
    ALL = OUTCOME_VALUES

    def __new__(cls):
        raise TypeError("RuleOutcome is a constants namespace")

    @classmethod
    def parse(cls, value):
        if value not in OUTCOME_VALUES:
            raise ConfigurationError(f"unknown Rule outcome: {value!r}")
        return value
