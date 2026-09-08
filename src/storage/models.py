"""Storage controlled values (frozen contract).

Single definitions reused by the manifest model and config validation.
"""

from kmx.exceptions import ConfigurationError

ACQUISITION_MODES = ("api", "bulk", "db", "pdf", "web", "manual")
RIGHTS_STATUSES = ("cleared", "pending_review", "restricted")
PARSE_STATUSES = ("staged", "parsed", "quarantined")


class _Vocabulary:
    VALUES = ()

    def __new__(cls):
        raise TypeError(f"{cls.__name__} is a constants namespace")

    @classmethod
    def parse(cls, value):
        if value not in cls.VALUES:
            raise ConfigurationError(f"unknown {cls.__name__.lower()}: {value!r}")
        return value

    @classmethod
    def is_valid(cls, value):
        return value in cls.VALUES


class AcquisitionMode(_Vocabulary):
    VALUES = ACQUISITION_MODES


class RightsStatus(_Vocabulary):
    VALUES = RIGHTS_STATUSES


class ParseStatus(_Vocabulary):
    VALUES = PARSE_STATUSES
