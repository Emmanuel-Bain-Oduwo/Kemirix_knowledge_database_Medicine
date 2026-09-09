"""The deterministic RxNorm-to-KMX bulk loader (passes A through G).

Runs over the STORED release original only. Relation directions follow the
official RRF convention (RXCUI2 RELA RXCUI1):
    SCDC has_ingredient IN        PIN form_of IN
    SCD consists_of SCDC          SCD has_ingredients MIN
    MIN has_part IN / PIN         SBD tradename_of SCD
Zero KMX-PROD is ever created: RxNorm is not a regulator product lane, and
the Phase 8 builder proof gate enforces that structurally as well.
"""

from ..exceptions import SourceContractError
from .rrf import iter_rrf

SAB = "RXNORM"
PRESCRIBABLE_CVF = "4096"

RELA_FORM_OF = "form_of"
RELA_HAS_INGREDIENT = "has_ingredient"
RELA_HAS_PRECISE_INGREDIENT = "has_precise_ingredient"
RELA_CONSISTS_OF = "consists_of"
RELA_HAS_INGREDIENTS = "has_ingredients"
RELA_HAS_PART = "has_part"
RELA_TRADENAME_OF = "tradename_of"


class RxNormKmxLoader:
    """Loads KMX ING/CD identities from a stored RxNorm full release."""

    def __init__(self, builder, repository, exception_recorder=None):
        self._builder = builder
        self._repository = repository
        self._exception_recorder = exception_recorder or builder._repository

    def load(self, zip_path):
        """Run all passes over the stored release; return statistics."""
        concepts = self._load_concepts(zip_path)
        relations = self._load_relations(zip_path)
        stats = {
            "in_seen": 0,
            "pin_seen": 0,
            "scd_seen": 0,
            "sbd_seen": 0,
            "ing_created": 0,
            "ing_reused": 0,
            "pin_linked": 0,
            "pin_unlinked": 0,
            "cd_created": 0,
            "cd_reused": 0,
            "aliases": 0,
            "exceptions": 0,
            "prescribable_concepts": 0,
        }

        # Pass A: canonical IN anchors.
        for rxcui, concept in concepts["IN"].items():
            stats["in_seen"] += 1
            if concept["cvf"] == PRESCRIBABLE_CVF:
                stats["prescribable_concepts"] += 1
            built = self._builder.build_ingredient(
                lane_id="S01",
                source_id="rxnorm_athena",
                allowed_levels=("ingredient", "clinical_drug"),
                preferred_name=concept["str"],
                normalized_name=self._normalize(concept["str"]),
                identifiers=[("RXNORM", rxcui)],
                concept_type="IN",
            )
            self._count(built, stats, "ing")

        # Pass B: precise ingredients, associated only through form_of.
        for rxcui, concept in concepts["PIN"].items():
            stats["pin_seen"] += 1
            if concept["cvf"] == PRESCRIBABLE_CVF:
                stats["prescribable_concepts"] += 1
            bases = relations[RELA_FORM_OF].get(rxcui, [])
            base_rxcui = bases[0] if len(bases) == 1 else None
            precise_parent = None
            if base_rxcui is not None and base_rxcui in concepts["IN"]:
                from kmx.builders import PreciseParent

                base_kmx = self._repository.external_bindings("RXNORM", base_rxcui)
                if len(base_kmx) == 1:
                    precise_parent = PreciseParent(base_kmx[0].kmx_id, relationship_proven=True)
            if precise_parent is None:
                stats["pin_unlinked"] += 1
            built = self._builder.build_ingredient(
                lane_id="S01",
                source_id="rxnorm_athena",
                allowed_levels=("ingredient", "clinical_drug"),
                preferred_name=concept["str"],
                normalized_name=self._normalize(concept["str"]),
                identifiers=[("RXNORM", rxcui)],
                concept_type="PIN",
                precise_parent=precise_parent,
            )
            self._count(built, stats, "ing")
            if precise_parent is not None:
                stats["pin_linked"] += 1

        # Pass C/D: SCD structural identities with CD->ING containment.
        for rxcui, concept in concepts["SCD"].items():
            stats["scd_seen"] += 1
            if concept["cvf"] == PRESCRIBABLE_CVF:
                stats["prescribable_concepts"] += 1
            ingredient_rxcuis = self._scd_ingredients(rxcui, relations, concepts)
            members = []
            for ingredient in sorted(ingredient_rxcuis):
                if ingredient not in concepts["IN"] and ingredient not in concepts["PIN"]:
                    continue
                bindings = self._repository.external_bindings("RXNORM", ingredient)
                if len(bindings) == 1:
                    members.append(bindings[0].kmx_id)
            if not members:
                self._record_exception(
                    rxcui,
                    "FORMULATION_AMBIGUITY",
                    concept["str"],
                    sorted(ingredient_rxcuis),
                )
                stats["exceptions"] += 1
                continue
            built = self._builder.build_clinical_drug(
                lane_id="S01",
                source_id="rxnorm_athena",
                allowed_levels=("ingredient", "clinical_drug"),
                preferred_name=concept["str"],
                normalized_name=self._normalize(concept["str"]),
                identifiers=[("RXNORM", rxcui)],
                ingredient_kmx_ids=sorted(members),
            )
            self._count(built, stats, "cd")

        # Pass F: SBD brand aliases projected onto existing CDs only through
        # the officially proven tradename_of relation. Never a PROD.
        for rxcui, concept in concepts["SBD"].items():
            stats["sbd_seen"] += 1
            targets = relations[RELA_TRADENAME_OF].get(rxcui, [])
            target = targets[0] if len(targets) == 1 else None
            if target is None:
                continue
            bindings = self._repository.external_bindings("RXNORM", target)
            if len(bindings) != 1:
                continue
            from kmx.normalizer import normalize_name

            self._repository.insert_name(
                kmx_id=bindings[0].kmx_id,
                normalized_name=normalize_name(concept["str"]),
                name_type="brand",
                source_id="rxnorm_athena",
            )
            stats["aliases"] += 1

        return stats

    # --- internals ---

    def _load_concepts(self, zip_path):
        concepts = {"IN": {}, "PIN": {}, "SCD": {}, "SBD": {}}
        for row in iter_rrf(zip_path, "RXNCONSO", sab=SAB):
            tty = row["TTY"]
            if tty not in concepts:
                continue
            concepts[tty][row["RXCUI"]] = {
                "str": row["STR"],
                "cvf": row["CVF"],
            }
        return concepts

    def _load_relations(self, zip_path):
        wanted = {
            RELA_FORM_OF,
            RELA_HAS_INGREDIENT,
            RELA_HAS_PRECISE_INGREDIENT,
            RELA_CONSISTS_OF,
            RELA_HAS_INGREDIENTS,
            RELA_HAS_PART,
            RELA_TRADENAME_OF,
        }
        relations = {name: {} for name in wanted}
        for row in iter_rrf(zip_path, "RXNREL", sab=SAB):
            rela = row["RELA"]
            if rela not in wanted:
                continue
            # Official direction: RXCUI2 --RELA--> RXCUI1.
            relations[rela].setdefault(row["RXCUI2"], []).append(row["RXCUI1"])
        return relations

    def _scd_ingredients(self, rxcui, relations, concepts):
        """Ingredient RXCUIs of one SCD through its SCDCs and MINs."""
        ingredients = set()
        for scdc in relations[RELA_CONSISTS_OF].get(rxcui, []):
            ingredients.update(relations[RELA_HAS_INGREDIENT].get(scdc, []))
            ingredients.update(relations[RELA_HAS_PRECISE_INGREDIENT].get(scdc, []))
        for mincui in relations[RELA_HAS_INGREDIENTS].get(rxcui, []):
            ingredients.update(relations[RELA_HAS_PART].get(mincui, []))
        ingredients.discard(rxcui)
        return ingredients

    def _record_exception(self, rxcui, reason, name, candidates):
        try:
            self._exception_recorder.record_mapping_exception(
                lane_id="S01",
                source_id="rxnorm_athena",
                source_version_key=None,
                source_record_key=f"RXCUI-{rxcui}",
                reason_code=reason,
                normalized_input={"name": name},
                candidate_kmx_ids=[f"RXNORM-{c}" for c in candidates],
            )
        except Exception as error:  # pragma: no cover - recording must not crash
            raise SourceContractError(
                f"mapping exception recording failed ({type(error).__name__})"
            ) from None

    @staticmethod
    def _normalize(text):
        from kmx.normalizer import normalize_name

        return normalize_name(text)

    @staticmethod
    def _count(built, stats, prefix):
        if built.created:
            stats[f"{prefix}_created"] += 1
        else:
            stats[f"{prefix}_reused"] += 1
