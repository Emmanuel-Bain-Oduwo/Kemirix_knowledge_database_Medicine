"""The ING/CD/PROD builders with the strict product proof gate (KMX-003).

Every build call is atomic: registry row, external identifiers, name index
entries and containment edges commit together or not at all. Reuse always
happens through exact active external identifiers — never names — so a
refresh re-encounters the same identity and reuses it instead of
renumbering. Minting a level requires the lane's frozen kmx_levels contract
to authorize that level. The product builder enforces the regulator proof
gate: only approved regulator product lanes with an exact regulator
product identifier may create KMX-PROD; everything else fails closed to
PRODUCT_IDENTITY_UNPROVEN for kmx.mapping_exception.
"""

from dataclasses import dataclass

from .allocation import allocate_kmx_id
from .exceptions import MappingExceptionBoundaryError
from .models import KmxLevel
from .resolver import (
    APPROVED_PRODUCT_CREATORS,
    ResolutionRequest,
    Resolved,
    resolve_identity,
)
from .transaction_helper import owning_transaction

RELATIONSHIP_CONTAINS = "contains"
RELATIONSHIP_PRECISE_INGREDIENT = "precise_ingredient"

MULTIPLE_INGREDIENT_CONCEPT = "MIN"


@dataclass(frozen=True)
class Built:
    """One minted or reused identity."""

    kmx_id: str
    level: str
    created: bool


@dataclass(frozen=True)
class PreciseParent:
    """A PIN association to a base ingredient, only when officially proven."""

    base_kmx_id: str
    relationship_proven: bool


class KmxBuilder:
    """Builds KMX identities on top of the repository and resolver."""

    def __init__(self, repository, connection):
        self._repository = repository
        self._connection = connection

    # --- ingredient builder ---

    def build_ingredient(
        self,
        *,
        lane_id,
        source_id,
        allowed_levels,
        preferred_name,
        normalized_name,
        identifiers,
        concept_type=None,
        precise_parent=None,
    ):
        """Mint or reuse one KMX-ING from an exact anchor (RxNorm IN or PIN).

        MIN concepts are refused outright: a multiple-ingredient string never
        becomes one fake single ingredient. A PIN mints its own precise
        identity and is associated to its base ingredient only when the
        official relationship is proven; an unproven association simply
        does not link — never blindly.
        """
        if concept_type == MULTIPLE_INGREDIENT_CONCEPT:
            raise MappingExceptionBoundaryError(
                "MIN concepts never mint a single fake ingredient; resolve the "
                "constituents and represent the combination through CD containment"
            )
        return self._build_identity(
            level=KmxLevel.INGREDIENT,
            lane_id=lane_id,
            source_id=source_id,
            allowed_levels=allowed_levels,
            preferred_name=preferred_name,
            normalized_name=normalized_name,
            identifiers=identifiers,
            extra=self._link_precise_parent(precise_parent),
        )

    # --- clinical drug builder ---

    def build_clinical_drug(
        self,
        *,
        lane_id,
        source_id,
        allowed_levels,
        preferred_name,
        normalized_name,
        identifiers,
        ingredient_kmx_ids,
    ):
        """Mint or reuse one brand-neutral KMX-CD formulation identity.

        The resolved ingredient members, their strengths, the dose form,
        release characteristic and identity-defining route are carried by
        the caller's structured inputs and the distinct normalized identity;
        the builder never merges formulations that differ in them. Reuse is
        exact-identifier only, never by name.
        """
        members = tuple(ingredient_kmx_ids)
        if not members:
            raise MappingExceptionBoundaryError(
                "a clinical drug requires at least one resolved ingredient member"
            )
        for member in members:
            resolved = self._repository.get_kmx(member)
            if resolved is None or resolved.level != KmxLevel.INGREDIENT:
                raise MappingExceptionBoundaryError(
                    f"clinical drug member {member!r} is not a resolved ingredient"
                )

        def extra(built):
            for ordinal, member in enumerate(members, start=1):
                self._add_containment(built.kmx_id, member, RELATIONSHIP_CONTAINS, ordinal)

        return self._build_identity(
            level=KmxLevel.CLINICAL_DRUG,
            lane_id=lane_id,
            source_id=source_id,
            allowed_levels=allowed_levels,
            preferred_name=preferred_name,
            normalized_name=normalized_name,
            identifiers=identifiers,
            extra=extra,
        )

    # --- product builder: strict proof gate ---

    def build_product(
        self,
        *,
        lane_id,
        source_id,
        preferred_name,
        normalized_name,
        regulator_identifier,
        clinical_drug_kmx_ids,
    ):
        """Mint or reuse one KMX-PROD only with exact regulator proof.

        The proof gate: the lane must be an approved regulator product
        creator (S08 ppb_register, S26 ema, S27 mhra) and an exact regulator
        product identifier (system and value) must be supplied together with
        the resolved clinical drug(s) and the product name. A brand name or
        an RxNorm SBD is never sufficient — those fail closed to
        PRODUCT_IDENTITY_UNPROVEN for human review.
        """
        if source_id not in APPROVED_PRODUCT_CREATORS:
            raise MappingExceptionBoundaryError(
                "PRODUCT_IDENTITY_UNPROVEN: source is not an approved regulator "
                f"product lane ({source_id})"
            )
        if (
            not regulator_identifier
            or not regulator_identifier.get("system")
            or not regulator_identifier.get("value")
        ):
            raise MappingExceptionBoundaryError(
                "PRODUCT_IDENTITY_UNPROVEN: an exact regulator product identifier "
                "(system and value) is required"
            )
        members = tuple(clinical_drug_kmx_ids)
        if not members:
            raise MappingExceptionBoundaryError(
                "PRODUCT_IDENTITY_UNPROVEN: a product requires its resolved clinical drug(s)"
            )
        for member in members:
            resolved = self._repository.get_kmx(member)
            if resolved is None or resolved.level != KmxLevel.CLINICAL_DRUG:
                raise MappingExceptionBoundaryError(
                    f"product member {member!r} is not a resolved clinical drug"
                )

        def extra(built):
            for ordinal, member in enumerate(members, start=1):
                self._add_containment(built.kmx_id, member, RELATIONSHIP_CONTAINS, ordinal)

        return self._build_identity(
            level=KmxLevel.PRODUCT,
            lane_id=lane_id,
            source_id=source_id,
            allowed_levels=(KmxLevel.PRODUCT,),  # regulator proof IS the authorization
            preferred_name=preferred_name,
            normalized_name=normalized_name,
            identifiers=[(regulator_identifier["system"], regulator_identifier["value"])],
            extra=extra,
        )

    # --- shared machinery ---

    def _build_identity(
        self,
        *,
        level,
        lane_id,
        source_id,
        allowed_levels,
        preferred_name,
        normalized_name,
        identifiers,
        extra=None,
    ):
        with owning_transaction(self._connection):
            outcome = resolve_identity(
                self._repository,
                ResolutionRequest(
                    identifiers=identifiers,
                    normalized_name=normalized_name,
                    desired_level=level,
                    lane_id=lane_id,
                    source_id=source_id,
                    source_record_key=identifiers[0][1] if identifiers else normalized_name,
                ),
            )
            if isinstance(outcome, Resolved):
                return Built(outcome.kmx_id, outcome.level, created=False)
            if outcome.reason_code == "NO_MATCH" and level not in allowed_levels:
                raise MappingExceptionBoundaryError(
                    f"lane {lane_id} is not authorized to mint KMX at level {level}"
                )
            if outcome.reason_code != "NO_MATCH":
                raise MappingExceptionBoundaryError(
                    f"identity resolution failed closed: {outcome.reason_code}"
                )
            kmx_id = allocate_kmx_id(self._connection, level)
            self._repository.insert_kmx(
                kmx_id=str(kmx_id),
                level=level,
                preferred_name=preferred_name,
                normalized_name=normalized_name,
            )
            for system, value in identifiers:
                self._repository.insert_external_identifier(
                    kmx_id=str(kmx_id),
                    identifier_system=system,
                    identifier_value=value,
                    source_id=source_id,
                )
            self._repository.insert_name(
                kmx_id=str(kmx_id),
                normalized_name=normalized_name,
                name_type="preferred",
                source_id=source_id,
            )
            built = Built(str(kmx_id), level, created=True)
            if extra is not None:
                extra(built)
            return built

    def _link_precise_parent(self, precise_parent):
        if precise_parent is None:
            return None

        def extra(built):
            if not precise_parent.relationship_proven:
                # An unproven PIN/base association simply does not link;
                # the PIN keeps its own precise identity either way.
                return
            base = self._repository.get_kmx(precise_parent.base_kmx_id)
            if base is None or base.level != KmxLevel.INGREDIENT:
                raise MappingExceptionBoundaryError(
                    "precise ingredient parent must be a resolved base ingredient"
                )
            self._add_containment(
                precise_parent.base_kmx_id,
                built.kmx_id,
                RELATIONSHIP_PRECISE_INGREDIENT,
                None,
            )

        return extra

    def _add_containment(self, container, member, relationship_type, ordinal):
        if self._repository.existing_containment(
            container_kmx_id=container,
            member_kmx_id=member,
            relationship_type=relationship_type,
        ):
            return
        self._repository.insert_containment(
            container_kmx_id=container,
            member_kmx_id=member,
            relationship_type=relationship_type,
            ordinal=ordinal,
        )
