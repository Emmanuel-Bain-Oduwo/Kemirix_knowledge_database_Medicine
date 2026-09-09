"""The deterministic KMX resolver (KMX-002).
Frozen algorithm (owner directive 2026-09-09, Phase 7):
    collect exact identifiers
      -> lookup active external bindings
         identifier disagreement            -> IDENTIFIER_CONFLICT
         exactly one KMX                    -> resolved
         one identifier, several KMX        -> MULTIPLE_MATCHES
      -> no exact identifier
         name fallback only when the source contract permits
         one unique structural candidate   -> resolved
         none                               -> NO_MATCH
         multiple/ambiguous formulation    -> FORMULATION_AMBIGUITY
A product-level request from any lane other than the approved regulator
product creators fails closed as PRODUCT_IDENTITY_UNPROVEN. The resolver is
a pure function over the repository: it performs no writes, makes no
network calls and contains no probabilistic, similarity or LLM logic.
Identity is exact or it is a mapping exception — never a guess.
"""

from .exceptions import MappingExceptionBoundaryError
from .models import KmxLevel

APPROVED_PRODUCT_CREATORS = ("ppb_register", "ema", "mhra")
RESOLVED = "resolved"
MAPPING_EXCEPTION = "mapping_exception"


class ResolutionRequest:
    """One immutable resolution attempt for a source item."""

    __slots__ = (
        "identifiers",
        "normalized_name",
        "desired_level",
        "lane_id",
        "source_id",
        "source_version_key",
        "source_record_key",
        "name_fallback_permitted",
    )

    def __init__(
        self,
        *,
        identifiers,
        normalized_name=None,
        desired_level=None,
        lane_id,
        source_id,
        source_version_key=None,
        source_record_key,
        name_fallback_permitted=False,
    ):
        if not identifiers and not normalized_name:
            raise MappingExceptionBoundaryError(
                "a resolution request needs exact identifiers or a normalized name"
            )
        self.identifiers = tuple((str(system), str(value)) for system, value in identifiers)
        for system, value in self.identifiers:
            if not system.strip() or not value.strip():
                raise MappingExceptionBoundaryError("external identifiers must be non-empty")
        self.normalized_name = normalized_name
        self.desired_level = desired_level
        if desired_level is not None and desired_level not in KmxLevel.ALL:
            raise MappingExceptionBoundaryError(f"unknown KMX level: {desired_level!r}")
        self.lane_id = lane_id
        self.source_id = source_id
        self.source_version_key = source_version_key
        self.source_record_key = source_record_key
        self.name_fallback_permitted = name_fallback_permitted

    def provenance(self):
        """Safe provenance dict recorded with every mapping exception."""
        return {
            "lane_id": self.lane_id,
            "source_id": self.source_id,
            "source_version_key": self.source_version_key,
            "source_record_key": self.source_record_key,
            "normalized_name": self.normalized_name,
            "identifiers": [
                {"system": system, "value": value} for system, value in self.identifiers
            ],
        }


class Resolved:
    """Exactly one deterministic KMX identity."""

    __slots__ = ("kmx_id", "level")

    def __init__(self, kmx_id, level):
        self.kmx_id = kmx_id
        self.level = level


class MappingExceptionOutcome:
    """A fail-closed outcome the caller must record, never guess past."""

    __slots__ = ("reason_code", "candidate_kmx_ids", "request")

    def __init__(self, reason_code, candidate_kmx_ids, request):
        self.reason_code = reason_code
        self.candidate_kmx_ids = tuple(candidate_kmx_ids)
        self.request = request


def resolve_identity(repository, request):
    """Run the frozen deterministic algorithm. Pure: no writes, no guessing."""
    if (
        request.desired_level == KmxLevel.PRODUCT
        and request.source_id not in APPROVED_PRODUCT_CREATORS
    ):
        return MappingExceptionOutcome("PRODUCT_IDENTITY_UNPROVEN", [], request)
    matched = {}
    for system, value in request.identifiers:
        bindings = repository.external_bindings(system, value)
        ids = {binding.kmx_id for binding in bindings}
        if len(ids) > 1:
            # One exact identifier bound to several identities: the data
            # disagrees with itself; only humans resolve this.
            return MappingExceptionOutcome("MULTIPLE_MATCHES", sorted(ids), request)
        for binding in bindings:
            matched[binding.kmx_id] = binding
    if matched:
        if len(matched) > 1:
            # Different identifiers point at different identities: the
            # item's own identifiers disagree with each other.
            return MappingExceptionOutcome("IDENTIFIER_CONFLICT", sorted(matched), request)
        only = next(iter(matched.values()))
        if request.desired_level is not None and only.level != request.desired_level:
            return MappingExceptionOutcome("IDENTIFIER_CONFLICT", [only.kmx_id], request)
        return Resolved(only.kmx_id, only.level)
    if not request.name_fallback_permitted or not request.normalized_name:
        return MappingExceptionOutcome("NO_MATCH", [], request)
    candidates = repository.name_candidates(request.normalized_name, level=request.desired_level)
    if not candidates:
        return MappingExceptionOutcome("NO_MATCH", [], request)
    if len({candidate.kmx_id for candidate in candidates}) == 1:
        only = candidates[0]
        return Resolved(only.kmx_id, only.level)
    return MappingExceptionOutcome(
        "FORMULATION_AMBIGUITY",
        sorted({candidate.kmx_id for candidate in candidates}),
        request,
    )
