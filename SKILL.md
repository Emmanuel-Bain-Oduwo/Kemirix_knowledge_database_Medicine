---
name: kemirix-knowledge-foundation
version: 4.3
updated: 2026-09-07
description: Agent operating skill for the Kemirix medication knowledge foundation: KMX-ING/KMX-CD/KMX-PROD -> full source-specific Clinical Evidence -> deterministic Evidence-linked Rules on OVH infrastructure.
---

# Kemirix Knowledge Foundation - Final Agent SKILL

## 0. Mission and frozen scope

Build **one simple, trackable, auditable pipeline**:

```text
APPROVED SOURCE LANE
        |
        v
ACQUIRE SOURCE ARTIFACT
(API / BULK / DB / PDF / WEB SNAPSHOT / MANUAL VERIFIED FILE)
        |
        +---------------------> OVH OBJECT STORAGE
        |                       immutable raw original + manifest + SHA-256
        v
KMX IDENTITY RESOLUTION
        |
        +--> KMX-ING
        +--> KMX-CD
        +--> KMX-PROD
        |
        v
SOURCE BLOCKS
        |
        v
ONE OF 24 SHARED CLINICAL CATEGORIES
        |
        v
FULL SOURCE-SPECIFIC CLINICAL EVIDENCE
        |
        +--> not executable -> Evidence only
        |
        +--> executable -> FULL DETERMINISTIC RULE
                             same KMX + same category + same jurisdiction
        |
        v
OVH MANAGED POSTGRESQL
  kmx.* | evidence.* | rules.*
        |
        v
DBEAVER REVIEW / QA
```

**Do not add KMX-PRES, graph databases, extra clinical micro-layers, per-source rule engines, or unnecessary services unless the owner explicitly changes the scope.**

### Distribution/security boundary

The distributed agent skill intentionally does **not** contain live source-access URLs, direct API query recipes, authentication material, or operator credentials. Source-access coordinates belong in an operator-controlled registry outside the distributed skill. Agents receive only the approved source ID, acquisition mode, expected artifact type, parser contract, KMX resolver, Evidence role, and Rule role.

Recommended private registry contract:

```yaml
source_id: S06
access_mode: api
access_reference: <operator-controlled reference>
auth_secret_name: <secret-manager key or null>
allowed_artifact_types: [structured_metadata, structured_document]
source_version_policy: pinned
rights_status: cleared | pending_review | restricted
rate_limit_policy: source-specific
```
## 1. Non-negotiable invariants
1. Identity is solved before clinical content is normalized.
2. KMX levels in this build are only ING, CD and PROD.
3. Every source item resolves deterministically to KMX or enters mapping_exception.
4. Never guess when identifiers disagree or when zero/multiple candidates remain.
5. Full Clinical Evidence remains source-specific; never blend unattributed source text.
6. A document may mechanically join at PROD while its clinical truth belongs to ING or CD.
7. Rules never resolve medicine identity again.
8. Rule target KMX, target level, category and jurisdiction are inherited from approved Evidence.
9. Primary/regulatory/guideline Evidence may create Rules; supporting sources do not independently change clinical action.
10. Duplicate projections of the same upstream label/document are not independent clinical votes.
11. If alternatives, monitoring or follow-up are not present in connected Evidence, store not_specified_by_connected_evidence.
12. Object Storage is the immutable raw vault; Managed PostgreSQL is the normalized clinical authority.
13. Never commit secrets, API keys or live access credentials to GitHub.
14. Every raw source snapshot must be versioned and hash-addressable.
15. Ambiguous identity, ambiguous PDF/table extraction and high-stakes Rule activation require human review.

## 2. KMX identity baseline

The baseline medication identity layer is built from the approved standardized terminology snapshot. The policy is semantic, not string-based.

```text
Ingredient concept ------------------------> KMX-ING
Standard clinical drug concept ------------> KMX-CD
Regulator-proven commercial product -------> KMX-PROD
```

### 2.1 KMX-ING

Use for the medicinal ingredient/substance when the clinical statement applies regardless of strength, form, release type, manufacturer or specific product.

### 2.2 KMX-CD

Use for ingredient + clinically meaningful formulation attributes, for example strength, concentration, dose form, release type, or route where those attributes alter the clinical identity.

### 2.3 KMX-PROD

Use only for a real authorized/registered commercial product with a stable regulatory/product identity. A brand-like terminology concept alone is not sufficient.

### 2.4 Stable KMX rule

If an active exact external identifier already maps to a KMX ID, reuse the KMX ID. Source refreshes never renumber established Kemirix identity.

### 2.5 Combination rule

A combination CD can have multiple ING parents:

```text
KMX-ING-A -------\
                   +----> KMX-CD-COMBINATION-X
KMX-ING-B -------/
```

Store the relationship in `kmx.contains` so Ingredient-wide Evidence/Rules remain discoverable from a combination CD.


## 2A. Concrete KMX examples - agents must understand this before source mapping

![Concrete KMX ING/CD/PROD example](kemirix_final_diagrams/07_kmx_examples.png)

### Example KMX-ING

```text
KMX-ING-000412
preferred_name: Metformin
level: ingredient
baseline ingredient anchor: RXCUI 6809 in the approved worked fixture
```

Meaning: this ID represents the **ingredient identity only**. It does not mean a particular strength, release type, manufacturer, brand, pack, or regulator product.

Ingredient-wide Evidence belongs here even when the source document was discovered through a more specific CD or PROD record.

```text
KMX-ING-000412
|
|-- renal/
|   |-- source-specific Evidence package A
|   `-- source-specific Evidence package B
|
|-- adverse_effects/
|   `-- source-specific Evidence package
|
`-- monitoring/
    `-- source-specific Evidence package
```

### Example KMX-CD

A Clinical Drug is ingredient(s) plus clinically meaningful formulation attributes. It is **not a brand**.

Approved fixture examples:

```text
KMX-ING-000412  Metformin
|
|-- KMX-CD-003871  immediate-release tablet identity
`-- KMX-CD-003872  extended-release tablet identity
```

The exact production CD is proved from the baseline terminology and formulation attributes. Typical identity components are:

```text
ingredient(s)
+ strength or concentration
+ dose form
+ release type
+ route when identity-defining
= KMX-CD
```

Formulation-specific Evidence stays on the CD:

```text
KMX-CD-003872
|
|-- dosing/
|   `-- formulation-specific Evidence
`-- administration/
    `-- formulation-specific Evidence
```

### Example KMX-PROD

A Product is an actual regulator-proven product identity:

```text
KMX-CD-...
   |
   `-- regulator product identity + product name + holder
          -> KMX-PROD-...
```

Product-only Evidence remains at PROD, for example when the statement depends on an actual product characteristic or excipient.

### ING versus CD versus PROD - one decision

```text
Does the statement apply regardless of strength/form/release/manufacturer?
  YES -> ING
  NO  -> does it depend on strength/form/release/route/concentration?
          YES -> CD
          NO  -> does it depend on actual product/regulator/excipient identity?
                  YES -> PROD
                  NO  -> mapping_exception / review
```

### Who creates KMX and who only resolves to KMX?

```text
S01 baseline terminology
  -> creates/reuses KMX-ING and KMX-CD

S08 / S26 / S27 regulator product lanes
  -> resolve existing ING
  -> resolve existing CD
  -> create/reuse KMX-PROD from exact regulator product identity

All other lanes
  -> normally DO NOT mint a new medicine identity
  -> resolve native identifiers/names to an existing ING/CD/PROD
```

This is critical: a supporting source record does not create a second KMX for the same medicine. It attaches its native identifier to the existing KMX through `kmx.external_identifier`.

## 3. Universal source-to-KMX resolver

```text
SOURCE ITEM
   |
   +-- exact baseline medication identifier? --> external-ID lookup --> ING or CD
   |
   +-- exact substance identifier? -----------> external-ID lookup --> ING
   |
   +-- verified chemical identifier? ---------> chemical bridge ----> ING
   |
   +-- regulator product identity? -----------> resolve ING -> resolve CD -> PROD
   |
   +-- no exact identifier? ------------------> controlled name -> ING
                                                 + formulation attrs -> unique CD

zero candidates OR multiple candidates OR identifier disagreement
   -> STOP
   -> kmx.mapping_exception
   -> preserve source record + candidate IDs
   -> human review
```

### 3.1 Truth-level decision

Ask one question: **what does the clinical statement actually depend on?**

```text
applies regardless of formulation/product -> ING
strength/form/release/route/concentration -> CD
brand/holder/excipient/regulator product -> PROD
```

`join_level` records where the source mechanically connected. `truth_level` records which KMX level the complete Evidence package actually applies to.
## 4. Shared 24 Clinical Evidence categories

```text
indication
contraindication
drug_disease
drug_drug
drug_food_substance
allergy_hypersensitivity
dosing
renal
hepatic
paediatric
geriatric
pregnancy
lactation
laboratory
vital_signs
monitoring
adverse_effects
duplication
polypharmacy
administration
high_alert_safety
pharmacogenomic
treatment_appropriateness
counselling
```

Do not create source-specific category vocabularies. Every clinical source maps its native headings/fields into this one controlled category set.

### Regulatory/monograph heading pattern

```text
Indications / therapeutic use ----------------> indication
Contraindications ----------------------------> contraindication / allergy_hypersensitivity when explicit
Warnings / precautions -----------------------> drug_disease / renal / hepatic / monitoring / high_alert_safety
Interactions ---------------------------------> drug_drug / drug_food_substance
Dose / posology ------------------------------> dosing
Method of administration ---------------------> administration
Pregnancy ------------------------------------> pregnancy
Lactation ------------------------------------> lactation
Paediatric content ---------------------------> paediatric
Geriatric content ----------------------------> geriatric
Laboratory monitoring ------------------------> laboratory / monitoring
Adverse reactions ----------------------------> adverse_effects
Patient advice -------------------------------> counselling
```

The category is chosen from the **content meaning**, not only the section heading. One source section can support more than one Evidence package when clinically justified, while each package remains complete and source-specific.

## 5. Full Clinical Evidence model

Every Evidence package answers:

```text
Which KMX medicine?
Which truth level: ING / CD / PROD?
Which category?
Which jurisdiction?
Which source/version?
Which exact source blocks support it?
What clinical context/recommendations/risk factors/monitoring/alternatives/follow-up does the source actually provide?
```

Minimal logical object:

```json
{
  "evidence_id": "EVID-...",
  "kmx_subject": "KMX-ING-...",
  "join_level": "product",
  "truth_level": "ingredient",
  "category": "renal",
  "jurisdiction": "...",
  "source_id": "Sxx",
  "source_version": "...",
  "clinical_context": {},
  "recommendations": [],
  "patient_risk_factors": [],
  "monitoring": [],
  "alternatives": [],
  "follow_up": [],
  "source_blocks": [],
  "evidence_hash": "...",
  "status": "draft|approved|stale|retired"
}
```

Organization is by database query/view, not physical folders:

```text
KMX
  -> truth level
     -> category
        -> source-specific Evidence package A
        -> source-specific Evidence package B
        -> source-specific Evidence package C
```

Never merge the source text of A/B/C into one unattributed clinical paragraph.

## 6. Source blocks

A `source_block` is the smallest **source-preserving retrieval unit**, not the final Evidence object.

Examples:
- structured label section
- monograph heading + page range
- recommendation box
- table row with header context
- database row/record
- structured API object

Minimum fields:

```text
block_id
source_id
source_version
source_record_key
native_section_code_or_heading
page_or_record_locator
raw_text_or_structured_payload
object_storage_key
sha256
parse_status
```

A full Evidence package can cite several blocks from the **same source version** when one clinical category naturally spans them.
## 7. The 27 source lanes - final execution contracts

S01-S27 preserve the exact approved registry order already used by the repository.

| ID | Source role | Acquisition | KMX | Evidence | Rule |
|---|---|---|---|---|---|
| S01 | Terminology baseline: standardized medication vocabulary | bulk vocabulary bundle | ING + CD | identity only | no |
| S02 | Terminology extensions and classification vocabularies | bulk vocabulary bundle | ING + CD | identity/classification only | no |
| S03 | Substance identity registry | bulk snapshot or approved API mirror | ING | identity only | no |
| S04 | Chemical ontology and cross-database identity bridge | bulk database + cross-reference service | ING | supporting only when clinically relevant | no direct rule |
| S05 | Medication terminology/classification support source | release ZIP/XML + accessory crosswalk files | ING + CD (follow mapped baseline semantic level) | supporting | no independent high-stakes rule |
| S06 | US structured product-label primary lane | API-first structured label retrieval | ING + CD + PROD mixture | primary regulatory evidence | yes when executable |
| S07 | US structured label projection lane | API-first JSON retrieval | ING + CD + PROD mixture | duplicate projection / structured extraction aid | no independent rule for duplicated content |
| S08 | Kenya regulator product register | dated official table snapshot / operator-approved export | ING + CD + PROD | catalogue/identity only | no |
| S09 | Kenya regulator professional product information lane | PDF/document corpus | ING + CD + PROD mixture | primary regulatory evidence | yes when executable |
| S10 | Kenya essential medicines catalogue lane | official PDF/manual verified file | ING + CD | catalogue only | no |
| S11 | Kenya national formulary lane | manual verified professional document | ING + CD | primary after source/rights approval | yes when executable |
| S12 | Kenya Ministry clinical guideline lane | official guideline PDFs/documents | mostly ING; CD when formulation-specific | primary guideline evidence | yes when patient trigger + decision + action are explicit |
| S13 | Global essential-medicines / antibiotic stewardship lane | official documents/structured publications | ING + CD | mixed: catalogue/classification plus actionable guidance when separately present | only from actionable treatment guidance, never from classification alone |
| S14 | Renal clinical guideline lane | official guideline PDF | mostly ING; CD if formulation-specific | primary for medication-specific computable recommendations | yes only where explicit and computable |
| S15 | Pharmacogenomics clinical guideline lane | approved structured API/data export | usually ING | primary guideline evidence for authoritative recommendations; other annotations supporting | yes for authoritative executable guideline recommendations |
| S16 | Research pharmacokinetic/safety support dataset | bulk TSV release bundle | ING | supporting | no direct high-stakes rule |
| S17 | Curated medication knowledge support database | bulk relational dump/TSV | usually ING | supporting | no direct rule |
| S18 | Machine-extracted adverse-effect support lane | bulk flat files / SQLite release | ING + CD mapping; Evidence commonly ING | supporting adverse-effect evidence | no direct rule |
| S19 | Specialized oncology evidence lane | bulk releases / structured API | ING | supporting specialized oncology/PGx | no general v1 rule |
| S20 | Bioactivity/target database lane | bulk relational database | ING | supporting biomedical | no |
| S21 | Pharmacology target/ligand database lane | bulk relational/CSV/TSV release | ING | supporting | no |
| S22 | Drug-gene interaction support lane | bulk TSV/SQL or approved structured API | ING | supporting | no direct prescribing rule |
| S23 | Target-disease evidence platform lane | bulk partitioned columnar datasets | ING | supporting | no |
| S24 | Curated mechanism-path database lane | versioned repository data files | ING | supporting | no |
| S25 | Clinical terminology / EMR normalization lane | versioned repository export ZIP/API | ING + CD | identity/runtime normalization only | no |
| S26 | EU regulatory professional product-information lane | machine-readable metadata + linked professional product-information documents | ING + CD + PROD mixture | primary regulatory evidence | yes when executable |
| S27 | UK regulatory professional product-information lane | controlled official document retrieval | ING + CD + PROD mixture | primary regulatory evidence | yes when executable |


### 7A. KMX level summary by source lane

This answers the planning question **which lanes are ING, which are CD, which can be PROD, and which are mixed**.

```text
BASELINE CREATION OF ING + CD
S01

ING + CD RESOLUTION / TERMINOLOGY
S02, S05, S10, S11, S13, S25
S12 and S14 are usually ING but may become CD when formulation-specific

ING-ONLY / MOSTLY-ING SUPPORT
S03, S04, S15, S16, S17, S19, S20, S21, S22, S23, S24
S18 can arrive mapped at ING/CD but Evidence is commonly organized at ING unless specificity is proven

ING + CD + PROD MIXED LANES
S06, S07, S08, S09, S26, S27

PRODUCT CREATION
S08, S26, S27 create/reuse PROD only after ING and CD are resolved
S09 joins the existing product created by S08
S06/S07 may join PROD only when exact product identity is proven
```

### 7B. Mixed-lane truth-level rule

```text
A source can join at one KMX level but produce Evidence at another.

join at PROD
  -> ingredient-wide content       -> Evidence truth ING
  -> formulation-specific content  -> Evidence truth CD
  -> product/excipient-specific    -> Evidence truth PROD

join at CD
  -> ingredient-wide content       -> Evidence truth ING
  -> formulation-specific content  -> Evidence truth CD
```

The **Rule always inherits the Evidence truth KMX**, never the original mechanical join KMX.

### S01 - Terminology baseline: standardized medication vocabulary

- **Acquire:** bulk vocabulary bundle
- **Native identity:** stable medication concept identifier + semantic class
- **KMX level:** ING + CD
- **Resolver:** direct semantic mapping
- **Example KMX -> Evidence -> Rule path:** ingredient semantic concept -> KMX-ING; exact clinical-drug semantic concept -> child KMX-CD; Evidence=no; Rule=no
- **Evidence role:** identity only
- **Evidence categories:** none
- **Rule role:** no
- **Parser action:** Delimited vocabulary tables; keep concept, relationship, synonym, strength and vocabulary metadata needed for identity.
- **Storage action:** Release bundle + manifest; normalized ING/CD and identifier rows go to Managed PostgreSQL.
- **Acceptance test:** one real source record must resolve to exactly one KMX join, produce traceable source blocks, and either create the correct Evidence package(s) or explicitly remain identity/catalogue/support only.

### S02 - Terminology extensions and classification vocabularies

- **Acquire:** bulk vocabulary bundle
- **Native identity:** terminology concept IDs + mappings
- **KMX level:** ING + CD
- **Resolver:** map to baseline terminology semantics
- **Example KMX -> Evidence -> Rule path:** extension/classification concept -> mapped baseline semantic level -> existing KMX-ING/KMX-CD; class metadata stored separately
- **Evidence role:** identity/classification only
- **Evidence categories:** none
- **Rule role:** no
- **Parser action:** Read mapping/classification tables; class memberships never mint medicine identity by themselves.
- **Storage action:** Same pinned vocabulary release; write crosswalk/classification rows only.
- **Acceptance test:** one real source record must resolve to exactly one KMX join, produce traceable source blocks, and either create the correct Evidence package(s) or explicitly remain identity/catalogue/support only.

### S03 - Substance identity registry

- **Acquire:** bulk snapshot or approved API mirror
- **Native identity:** substance identifier
- **KMX level:** ING
- **Resolver:** exact external-ID bridge
- **Example KMX -> Evidence -> Rule path:** exact substance identifier -> kmx.external_identifier -> existing KMX-ING; Evidence=no; Rule=no
- **Evidence role:** identity only
- **Evidence categories:** none
- **Rule role:** no
- **Parser action:** Parse substance records; preserve base/salt/active-moiety distinctions; quarantine ambiguous merges.
- **Storage action:** Raw snapshot/response + manifest; external identifier row -> KMX-ING.
- **Acceptance test:** one real source record must resolve to exactly one KMX join, produce traceable source blocks, and either create the correct Evidence package(s) or explicitly remain identity/catalogue/support only.

### S04 - Chemical ontology and cross-database identity bridge

- **Acquire:** bulk database + cross-reference service
- **Native identity:** chemical ontology/cross-reference identifiers
- **KMX level:** ING
- **Resolver:** verified chemical bridge
- **Example KMX -> Evidence -> Rule path:** verified chemical cross-reference -> existing KMX-ING -> optional supporting Evidence only when a clinical connection is explicit; Rule=no
- **Evidence role:** supporting only when clinically relevant
- **Evidence categories:** indication / treatment_appropriateness / other support only when a clinical connection is explicit
- **Rule role:** no direct rule
- **Parser action:** Load exact chemical IDs and cross-references; never infer clinical meaning from structure alone.
- **Storage action:** Raw dump/snapshot in Object Storage; only verified KMX crosswalk/support facts in PostgreSQL.
- **Acceptance test:** one real source record must resolve to exactly one KMX join, produce traceable source blocks, and either create the correct Evidence package(s) or explicitly remain identity/catalogue/support only.

### S05 - Medication terminology/classification support source

- **Acquire:** release ZIP/XML + accessory crosswalk files
- **Native identity:** source terminology ID + baseline crosswalk
- **KMX level:** ING + CD (follow mapped baseline semantic level)
- **Resolver:** source ID -> baseline identifier -> KMX
- **Example KMX -> Evidence -> Rule path:** source terminology ID -> baseline crosswalk -> ING or CD -> supporting source block -> relevant category Evidence; no independent Rule
- **Evidence role:** supporting
- **Evidence categories:** indication, drug_disease, classification/mechanism support
- **Rule role:** no independent high-stakes rule
- **Parser action:** Parse concepts, relationships and accessory crosswalks from the same release only.
- **Storage action:** Pin release; store XML/ZIP/accessory files and manifest together.
- **Acceptance test:** one real source record must resolve to exactly one KMX join, produce traceable source blocks, and either create the correct Evidence package(s) or explicitly remain identity/catalogue/support only.

### S06 - US structured product-label primary lane

- **Acquire:** API-first structured label retrieval
- **Native identity:** baseline medication ID + stable label family/product identifiers
- **KMX level:** ING + CD + PROD mixture
- **Resolver:** baseline ID -> ING/CD; exact product identity -> PROD
- **Example KMX -> Evidence -> Rule path:** structured label record -> baseline ID -> ING/CD or exact product identity -> PROD -> source blocks -> shared category -> full Evidence -> Rule only if executable
- **Evidence role:** primary regulatory evidence
- **Evidence categories:** regulatory categories across indication, contraindication, dosing, renal, hepatic, interactions, populations, administration, monitoring, adverse effects, counselling, high-alert safety
- **Rule role:** yes when executable
- **Parser action:** Store raw structured document first; preserve native sections and document version; category mapping happens after KMX resolution.
- **Storage action:** Per accepted label record: raw search metadata + canonical structured label + manifest.
- **Acceptance test:** one real source record must resolve to exactly one KMX join, produce traceable source blocks, and either create the correct Evidence package(s) or explicitly remain identity/catalogue/support only.

### S07 - US structured label projection lane

- **Acquire:** API-first JSON retrieval
- **Native identity:** baseline medication ID, substance ID, label/product IDs
- **KMX level:** ING + CD + PROD mixture
- **Resolver:** exact identifier lookup
- **Example KMX -> Evidence -> Rule path:** structured projection record -> exact ID -> same ING/CD/PROD -> duplicate/support Evidence -> no independent Rule for duplicated upstream content
- **Evidence role:** duplicate projection / structured extraction aid
- **Evidence categories:** same regulatory categories as the canonical label when present
- **Rule role:** no independent rule for duplicated content
- **Parser action:** Save raw JSON; map fields to source blocks; detect same-label family and avoid double-counting.
- **Storage action:** Query-fingerprint directory + raw JSON + manifest.
- **Acceptance test:** one real source record must resolve to exactly one KMX join, produce traceable source blocks, and either create the correct Evidence package(s) or explicitly remain identity/catalogue/support only.

### S08 - Kenya regulator product register

- **Acquire:** dated official table snapshot / operator-approved export
- **Native identity:** ingredient name, strength/form, product name, holder, registration identity
- **KMX level:** ING + CD + PROD
- **Resolver:** ingredient -> ING; formulation -> CD; regulator product identity -> PROD
- **Example KMX -> Evidence -> Rule path:** ingredient -> ING -> formulation -> CD -> regulator product identity -> PROD; identity/catalogue only
- **Evidence role:** catalogue/identity only
- **Evidence categories:** none
- **Rule role:** no
- **Parser action:** Parse table rows and detail fields deterministically; registration identity is the product anchor.
- **Storage action:** Snapshot + manifest; normalize product identity/crosswalk only.
- **Acceptance test:** one real source record must resolve to exactly one KMX join, produce traceable source blocks, and either create the correct Evidence package(s) or explicitly remain identity/catalogue/support only.

### S09 - Kenya regulator professional product information lane

- **Acquire:** PDF/document corpus
- **Native identity:** regulator product/registration identity
- **KMX level:** ING + CD + PROD mixture
- **Resolver:** join to existing regulator PROD; truth level selected from content scope
- **Example KMX -> Evidence -> Rule path:** professional product document -> join existing PROD -> block scope decides ING/CD/PROD truth -> full Evidence -> Rule if executable
- **Evidence role:** primary regulatory evidence
- **Evidence categories:** regulatory categories
- **Rule role:** yes when executable
- **Parser action:** Page-aware PDF extraction; split by real numbered headings; preserve product join while allowing ING/CD/PROD Evidence truth.
- **Storage action:** Original PDF + manifest + page/block map.
- **Acceptance test:** one real source record must resolve to exactly one KMX join, produce traceable source blocks, and either create the correct Evidence package(s) or explicitly remain identity/catalogue/support only.

### S10 - Kenya essential medicines catalogue lane

- **Acquire:** official PDF/manual verified file
- **Native identity:** medicine name, strength/form, list metadata
- **KMX level:** ING + CD
- **Resolver:** controlled name -> ING; unique formulation -> CD
- **Example KMX -> Evidence -> Rule path:** catalogue row -> controlled name -> ING; explicit unique formulation -> CD; catalogue only
- **Evidence role:** catalogue only
- **Evidence categories:** none
- **Rule role:** no
- **Parser action:** Extract catalogue rows/sections; do not treat list inclusion as prescribing Evidence.
- **Storage action:** Original PDF + catalogue snapshot manifest.
- **Acceptance test:** one real source record must resolve to exactly one KMX join, produce traceable source blocks, and either create the correct Evidence package(s) or explicitly remain identity/catalogue/support only.

### S11 - Kenya national formulary lane

- **Acquire:** manual verified professional document
- **Native identity:** controlled medicine name + formulation where stated
- **KMX level:** ING + CD
- **Resolver:** controlled name -> ING; explicit formulation -> CD
- **Example KMX -> Evidence -> Rule path:** monograph title -> ING; explicit formulation -> CD -> section blocks -> shared categories -> Evidence -> optional Rule after approval
- **Evidence role:** primary after source/rights approval
- **Evidence categories:** dosing, contraindication, drug_drug, renal, hepatic, pregnancy, lactation, paediatric, geriatric, monitoring, administration, counselling, adverse_effects as present
- **Rule role:** yes when executable
- **Parser action:** Preserve monograph headings and page ranges; build one full source-specific package per KMX + category.
- **Storage action:** Original verified document + manifest + source blocks.
- **Acceptance test:** one real source record must resolve to exactly one KMX join, produce traceable source blocks, and either create the correct Evidence package(s) or explicitly remain identity/catalogue/support only.

### S12 - Kenya Ministry clinical guideline lane

- **Acquire:** official guideline PDFs/documents
- **Native identity:** medicine name/class + disease context
- **KMX level:** mostly ING; CD when formulation-specific
- **Resolver:** controlled name/class index; exact formulation -> CD
- **Example KMX -> Evidence -> Rule path:** condition-first guideline -> each medicine mention -> ING or exact CD -> complete recommendation block -> Evidence -> Rule if deterministic
- **Evidence role:** primary guideline evidence
- **Evidence categories:** indication, treatment_appropriateness, dosing, monitoring, follow_up-related content, alternatives where source supplies them
- **Rule role:** yes when patient trigger + decision + action are explicit
- **Parser action:** Guideline-first parser: preserve disease section, recommendation box, practice point, table row and page location.
- **Storage action:** One immutable object per guideline version; never merge raw guidelines.
- **Acceptance test:** one real source record must resolve to exactly one KMX join, produce traceable source blocks, and either create the correct Evidence package(s) or explicitly remain identity/catalogue/support only.

### S13 - Global essential-medicines / antibiotic stewardship lane

- **Acquire:** official documents/structured publications
- **Native identity:** ingredient names, classification codes, formulation attributes
- **KMX level:** ING + CD
- **Resolver:** controlled ingredient/class mapping; formulation -> CD
- **Example KMX -> Evidence -> Rule path:** list/classification record -> ING/CD metadata only; separate actionable guidance -> same ING/CD -> Evidence -> optional Rule
- **Evidence role:** mixed: catalogue/classification plus actionable guidance when separately present
- **Evidence categories:** classification is metadata; actionable guidance may populate indication, treatment_appropriateness, dosing, administration, paediatric and monitoring
- **Rule role:** only from actionable treatment guidance, never from classification alone
- **Parser action:** Keep catalogue/classification and actionable guidance as separate physical source versions.
- **Storage action:** Separate raw objects/manifests for catalogue, classification and actionable guidance.
- **Acceptance test:** one real source record must resolve to exactly one KMX join, produce traceable source blocks, and either create the correct Evidence package(s) or explicitly remain identity/catalogue/support only.

### S14 - Renal clinical guideline lane

- **Acquire:** official guideline PDF
- **Native identity:** medicine/class mentions + renal context
- **KMX level:** mostly ING; CD if formulation-specific
- **Resolver:** controlled KMX name/class index
- **Example KMX -> Evidence -> Rule path:** medicine-specific renal guidance -> usually ING, CD only when formulation-specific -> renal/monitoring Evidence -> Rule only when explicit/computable
- **Evidence role:** primary for medication-specific computable recommendations
- **Evidence categories:** renal, laboratory, monitoring, drug_disease, polypharmacy, treatment_appropriateness
- **Rule role:** yes only where explicit and computable
- **Parser action:** Preserve recommendation/practice-point/table context; do not convert broad narrative into rules.
- **Storage action:** Original PDF + page-aware source blocks + manifest.
- **Acceptance test:** one real source record must resolve to exactly one KMX join, produce traceable source blocks, and either create the correct Evidence package(s) or explicitly remain identity/catalogue/support only.

### S15 - Pharmacogenomics clinical guideline lane

- **Acquire:** approved structured API/data export
- **Native identity:** drug cross-reference + gene/phenotype/genotype context
- **KMX level:** usually ING
- **Resolver:** verified baseline/chemical cross-reference -> ING
- **Example KMX -> Evidence -> Rule path:** drug/gene recommendation -> drug maps to ING -> pharmacogenomic Evidence -> authoritative executable recommendation may create Rule
- **Evidence role:** primary guideline evidence for authoritative recommendations; other annotations supporting
- **Evidence categories:** pharmacogenomic; sometimes dosing/treatment_appropriateness
- **Rule role:** yes for authoritative executable guideline recommendations
- **Parser action:** Preserve gene, phenotype/genotype, recommendation strength and source version as one coherent Evidence package.
- **Storage action:** Raw structured response/export + manifest; no secrets in repository.
- **Acceptance test:** one real source record must resolve to exactly one KMX join, produce traceable source blocks, and either create the correct Evidence package(s) or explicitly remain identity/catalogue/support only.

### S16 - Research pharmacokinetic/safety support dataset

- **Acquire:** bulk TSV release bundle
- **Native identity:** substance identifier
- **KMX level:** ING
- **Resolver:** substance ID -> KMX-ING
- **Example KMX -> Evidence -> Rule path:** substance identifier -> ING -> selected PK/safety/interaction row -> relevant supporting Evidence; Rule=no
- **Evidence role:** supporting
- **Evidence categories:** drug_drug, adverse_effects, high_alert_safety when clinically justified; PK context supports explanations
- **Rule role:** no direct high-stakes rule
- **Parser action:** Load identity table first, then link PK/toxicity/adverse-event/DDI tables by source keys.
- **Storage action:** Whole official release bundle in Object Storage; normalize only KMX-relevant rows.
- **Acceptance test:** one real source record must resolve to exactly one KMX join, produce traceable source blocks, and either create the correct Evidence package(s) or explicitly remain identity/catalogue/support only.

### S17 - Curated medication knowledge support database

- **Acquire:** bulk relational dump/TSV
- **Native identity:** multiple external medication identifiers
- **KMX level:** usually ING
- **Resolver:** identifier consensus; disagreement -> mapping_exception
- **Example KMX -> Evidence -> Rule path:** identifier consensus -> ING; disagreement -> mapping_exception; supporting Evidence only
- **Evidence role:** supporting
- **Evidence categories:** indication, contraindication, mechanism and pharmacovigilance support
- **Rule role:** no direct rule
- **Parser action:** Use multiple identifiers as a consistency check, not a reason to guess.
- **Storage action:** Raw relational/TSV release + manifest; selected normalized support facts only.
- **Acceptance test:** one real source record must resolve to exactly one KMX join, produce traceable source blocks, and either create the correct Evidence package(s) or explicitly remain identity/catalogue/support only.

### S18 - Machine-extracted adverse-effect support lane

- **Acquire:** bulk flat files / SQLite release
- **Native identity:** built-in baseline medication mappings
- **KMX level:** ING + CD mapping; Evidence commonly ING
- **Resolver:** source mapping -> KMX
- **Example KMX -> Evidence -> Rule path:** built-in baseline mapping -> ING/CD; most adverse-effect Evidence stays ING unless formulation specificity is proven
- **Evidence role:** supporting adverse-effect evidence
- **Evidence categories:** adverse_effects
- **Rule role:** no direct rule
- **Parser action:** Preserve model/extraction provenance and product-label context; do not treat model output as prescribing authority.
- **Storage action:** Release files + manifest; supporting Evidence only.
- **Acceptance test:** one real source record must resolve to exactly one KMX join, produce traceable source blocks, and either create the correct Evidence package(s) or explicitly remain identity/catalogue/support only.

### S19 - Specialized oncology evidence lane

- **Acquire:** bulk releases / structured API
- **Native identity:** ontology-grounded therapy identifiers
- **KMX level:** ING
- **Resolver:** verified therapy/chemical bridge -> ING
- **Example KMX -> Evidence -> Rule path:** verified therapy/chemical bridge -> ING + disease/molecular context -> specialized supporting Evidence; no general v1 Rule
- **Evidence role:** supporting specialized oncology/PGx
- **Evidence categories:** pharmacogenomic, treatment_appropriateness, indication
- **Rule role:** no general v1 rule
- **Parser action:** Preserve disease, molecular profile, evidence level/direction and source record intact.
- **Storage action:** Release snapshot + manifest; specialized support packages.
- **Acceptance test:** one real source record must resolve to exactly one KMX join, produce traceable source blocks, and either create the correct Evidence package(s) or explicitly remain identity/catalogue/support only.

### S20 - Bioactivity/target database lane

- **Acquire:** bulk relational database
- **Native identity:** molecule identifier
- **KMX level:** ING
- **Resolver:** exact molecule ID -> KMX-ING
- **Example KMX -> Evidence -> Rule path:** molecule ID -> ING -> mechanism/target support attached to an existing relevant clinical Evidence category; Rule=no
- **Evidence role:** supporting biomedical
- **Evidence categories:** support relevant clinical categories only when an explicit clinical link exists
- **Rule role:** no
- **Parser action:** Temporary restore/read on VM; extract targets/mechanism/bioactivity only for mapped KMX medicines.
- **Storage action:** Raw DB release in Object Storage; do not import entire DB into production knowledge DB.
- **Acceptance test:** one real source record must resolve to exactly one KMX join, produce traceable source blocks, and either create the correct Evidence package(s) or explicitly remain identity/catalogue/support only.

### S21 - Pharmacology target/ligand database lane

- **Acquire:** bulk relational/CSV/TSV release
- **Native identity:** ligand + chemical cross-references
- **KMX level:** ING
- **Resolver:** verified chemical cross-reference -> ING
- **Example KMX -> Evidence -> Rule path:** ligand/chemical cross-reference -> ING -> pharmacology support; Rule=no
- **Evidence role:** supporting
- **Evidence categories:** pharmacology/target support to relevant categories
- **Rule role:** no
- **Parser action:** Read public release tables; retain ligand-target relation and source version.
- **Storage action:** Raw release archive + manifest; selected KMX support only.
- **Acceptance test:** one real source record must resolve to exactly one KMX join, produce traceable source blocks, and either create the correct Evidence package(s) or explicitly remain identity/catalogue/support only.

### S22 - Drug-gene interaction support lane

- **Acquire:** bulk TSV/SQL or approved structured API
- **Native identity:** normalized drug ID / chemical cross-reference
- **KMX level:** ING
- **Resolver:** verified external identifier -> ING
- **Example KMX -> Evidence -> Rule path:** verified external drug identifier -> ING -> pharmacogenomic/drug-gene support; no independent prescribing Rule
- **Evidence role:** supporting
- **Evidence categories:** pharmacogenomic
- **Rule role:** no direct prescribing rule
- **Parser action:** Preserve underlying source claim and licensing/source attribution.
- **Storage action:** Release dump + source-license metadata + manifest.
- **Acceptance test:** one real source record must resolve to exactly one KMX join, produce traceable source blocks, and either create the correct Evidence package(s) or explicitly remain identity/catalogue/support only.

### S23 - Target-disease evidence platform lane

- **Acquire:** bulk partitioned columnar datasets
- **Native identity:** molecule identifier
- **KMX level:** ING
- **Resolver:** molecule ID -> ING
- **Example KMX -> Evidence -> Rule path:** molecule ID -> ING -> selected target-disease rows -> supporting indication/treatment/mechanism package; Rule=no
- **Evidence role:** supporting
- **Evidence categories:** indication, treatment_appropriateness, mechanism/development support
- **Rule role:** no
- **Parser action:** Read partitioned datasets directly with dataframe/Arrow tooling; filter to mapped KMX IDs.
- **Storage action:** Raw partition directories or archive in Object Storage; normalized support in PostgreSQL.
- **Acceptance test:** one real source record must resolve to exactly one KMX join, produce traceable source blocks, and either create the correct Evidence package(s) or explicitly remain identity/catalogue/support only.

### S24 - Curated mechanism-path database lane

- **Acquire:** versioned repository data files
- **Native identity:** chemical/biomedical identifiers in mechanism paths
- **KMX level:** ING
- **Resolver:** approved identifier bridge -> ING
- **Example KMX -> Evidence -> Rule path:** approved path identifier bridge -> ING -> mechanism-path support; Rule=no
- **Evidence role:** supporting
- **Evidence categories:** indication/treatment mechanism support
- **Rule role:** no
- **Parser action:** Read structured path records; preserve nodes/edges as source support, not as a graph database requirement.
- **Storage action:** Pinned release/commit archive + manifest; relevant path summaries only.
- **Acceptance test:** one real source record must resolve to exactly one KMX join, produce traceable source blocks, and either create the correct Evidence package(s) or explicitly remain identity/catalogue/support only.

### S25 - Clinical terminology / EMR normalization lane

- **Acquire:** versioned repository export ZIP/API
- **Native identity:** local clinical concept + SAME-AS/exact terminology mapping
- **KMX level:** ING + CD
- **Resolver:** SAME-AS baseline terminology -> KMX; otherwise approved controlled mapping
- **Example KMX -> Evidence -> Rule path:** exact SAME-AS baseline mapping -> ING/CD -> runtime terminology crosswalk only; Evidence/Rule=no
- **Evidence role:** identity/runtime normalization only
- **Evidence categories:** none
- **Rule role:** no
- **Parser action:** Import concepts + mappings from one repository version; preserve mapping type and status.
- **Storage action:** Version export ZIP + manifest; crosswalk rows only.
- **Acceptance test:** one real source record must resolve to exactly one KMX join, produce traceable source blocks, and either create the correct Evidence package(s) or explicitly remain identity/catalogue/support only.

### S26 - EU regulatory professional product-information lane

- **Acquire:** machine-readable metadata + linked professional product-information documents
- **Native identity:** active substance, strength/form, product number/authorisation, holder
- **KMX level:** ING + CD + PROD mixture
- **Resolver:** substance -> ING; formulation -> CD; regulator product identity -> PROD
- **Example KMX -> Evidence -> Rule path:** regulatory metadata -> substance ING -> formulation CD -> exact product identity PROD -> document block -> choose ING/CD/PROD truth -> Evidence -> Rule if executable
- **Evidence role:** primary regulatory evidence
- **Evidence categories:** regulatory categories
- **Rule role:** yes when executable
- **Parser action:** Use metadata to locate document version; parse numbered clinical sections; if one document covers multiple strengths/forms, split Evidence truth by scope while preserving one document provenance.
- **Storage action:** Metadata snapshot + original professional product-information document + manifest.
- **Acceptance test:** one real source record must resolve to exactly one KMX join, produce traceable source blocks, and either create the correct Evidence package(s) or explicitly remain identity/catalogue/support only.

### S27 - UK regulatory professional product-information lane

- **Acquire:** controlled official document retrieval
- **Native identity:** active substance, strength/form, product licence identity, holder
- **KMX level:** ING + CD + PROD mixture
- **Resolver:** substance -> ING; formulation -> CD; product licence + holder -> PROD
- **Example KMX -> Evidence -> Rule path:** regulatory product record -> substance ING -> formulation CD -> exact product identity PROD -> document block -> choose truth -> Evidence -> Rule if executable
- **Evidence role:** primary regulatory evidence
- **Evidence categories:** regulatory categories
- **Rule role:** yes when executable
- **Parser action:** Archive current professional product document; parse numbered sections; preserve licence history/product join and choose ING/CD/PROD Evidence truth from scope.
- **Storage action:** Original document + manifest keyed by stable regulatory product identity.
- **Acceptance test:** one real source record must resolve to exactly one KMX join, produce traceable source blocks, and either create the correct Evidence package(s) or explicitly remain identity/catalogue/support only.



## 7C. Worked examples of Evidence and Rules at ING, CD and PROD

### Example 1 - ING Evidence

```text
KMX-ING-000412
  category = renal
    |
    +-- EVID-A  source=S06  truth_level=ingredient
    +-- EVID-B  source=S14  truth_level=ingredient
    |
    `-- RULE-A  target_kmx_id=KMX-ING-000412
                target_level=ingredient
                category=renal
```

The two Evidence packages remain separate because they come from different sources. A query/view can show them together under the same KMX + category without blending their source text.

### Example 2 - CD Evidence

```text
KMX-CD-003872
  parent = KMX-ING-000412
  category = administration
    |
    `-- EVID-C  truth_level=clinical_drug
          |
          `-- RULE-C target_kmx_id=KMX-CD-003872
                     target_level=clinical_drug
                     category=administration
```

A formulation-specific statement must not be copied upward to ING.

### Example 3 - PROD Evidence

```text
KMX-PROD-...
  parent = KMX-CD-...
  category = allergy_hypersensitivity
    |
    `-- EVID-D  truth_level=product
          |
          `-- RULE-D target_kmx_id=KMX-PROD-...
                     target_level=product
```

Use PROD only when the clinical meaning actually depends on the real product/regulatory identity.

### Example 4 - Product join but ING truth

```text
source document
   |
   v
join_kmx_id = KMX-PROD-...
join_level  = product
   |
   v
source_block is ingredient-wide
   |
   v
Evidence.kmx_subject = KMX-ING-000412
truth_level          = ingredient
category             = renal
   |
   v
Rule inherits KMX-ING-000412 if executable
```

This is why `join_level` and `truth_level` must both exist.

### Example 5 - Source block -> Evidence record

```json
{
  "source_block_id": "BLOCK-EXAMPLE",
  "source_id": "S06",
  "join_kmx_id": "KMX-CD-003872",
  "join_level": "clinical_drug",
  "native_section": "<native heading>",
  "raw_object_key": "<source>/<snapshot>/<record>/original/<artifact>"
}
```

After category/truth review:

```json
{
  "evidence_id": "EVID-EXAMPLE",
  "kmx_subject": "KMX-ING-000412",
  "join_level": "clinical_drug",
  "truth_level": "ingredient",
  "category": "renal",
  "source_id": "S06",
  "source_blocks": ["BLOCK-EXAMPLE"]
}
```

### Example 6 - Rule inherits, never remaps

```text
APPROVED EVIDENCE
  kmx_subject = KMX-CD-003872
  truth_level = clinical_drug
  category = administration
  jurisdiction = <source jurisdiction>
          |
          v
RULE
  target_kmx_id = KMX-CD-003872
  target_level  = clinical_drug
  category      = administration
  jurisdiction  = <same jurisdiction>
```

No source adapter is allowed to run a second medicine resolver during Rule creation.

## 8. PDF/document parsing - accurate and simple

```text
PDF ARRIVES
   |
   v
SAVE ORIGINAL TO OBJECT STORAGE
   |
   v
SHA-256 + MANIFEST
   |
   v
HAS USABLE DIGITAL TEXT?
   |                     |
  YES                   NO
   |                     |
   v                     v
TEXT EXTRACTION        OCR ONLY THE NECESSARY PAGES
   |                     |
   +----------+----------+
              v
PRESERVE PAGE + HEADING + BLOCK ORDER
              |
              v
TABLE / RECOMMENDATION / SECTION DETECTION
              |
              v
AMBIGUOUS NUMERIC OR TABLE STRUCTURE?
        |                 |
       YES               NO
        |                 |
        v                 v
    QUARANTINE        SOURCE BLOCKS
        |                 |
        +---------> HUMAN QA
                          |
                          v
                     KMX RESOLUTION
                          |
                          v
                   EVIDENCE CATEGORIES
```

Rules for document parsing:
1. Store the untouched original before parsing.
2. Prefer digital text extraction; OCR is fallback only.
3. Never OCR the same born-digital page unnecessarily.
4. Keep page number, heading, section code, table header, row context and source order.
5. Never arbitrary-token-chunk a guideline or professional product information document.
6. Never repair an uncertain clinical number by guessing.
7. If a table extraction shifts columns or loses a unit, quarantine the affected block.
8. Keep `ocr_used`, OCR engine/version and review status in parser metadata.
9. Clinical rule activation requires reviewed Evidence, not raw OCR output.

## 9. API/bulk acquisition pattern

### API-first lane

```text
KMX/external ID
   -> deterministic request specification
   -> source-specific throttle
   -> raw response
   -> Object Storage
   -> checksum/manifest
   -> parse stored copy
   -> KMX/source blocks/Evidence
```

Use operator-controlled access configuration. Cache successful responses. On `429`, honor server retry guidance when available. Retry bounded transient `5xx` failures with exponential backoff. Do not retry deterministic `4xx` validation errors blindly.

### Bulk DB/ZIP/TSV/Parquet lane

```text
pinned official release
   -> hash
   -> Object Storage
   -> VM scratch area / temporary DB restore
   -> filter to mapped KMX medicines
   -> normalized support/identity rows
   -> Managed PostgreSQL
```

The production knowledge DB must not become a copy of every upstream source database.

## 10. OVH Object Storage

One raw bucket is enough:

```text
kemirix-knowledge-raw/
  Sxx/
    <source_version_or_snapshot>/
      <source_record_key>/
        original/
          <original artifact(s)>
        manifest.json
```

`manifest.json` minimum:

```json
{
  "source_id": "Sxx",
  "source_version": "...",
  "source_record_key": "...",
  "acquisition_mode": "api|bulk|db|pdf|web|manual",
  "fetched_at": "...",
  "upstream_published_at": "...",
  "object_key": "...",
  "sha256": "...",
  "adapter_version": "<git sha>",
  "rights_status": "cleared|pending_review|restricted",
  "parse_status": "staged|parsed|quarantined"
}
```

Object Storage is **not** the clinical authority. It is the immutable evidence vault for source originals.

## 11. OVH Managed PostgreSQL

One database: `kemirix_knowledge`.

```text
kmx
  registry
  contains
  external_identifier
  name_index
  mapping_exception

evidence
  source
  source_version
  source_block
  block_subject
  clinical_evidence
  evidence_support

rules
  clinical_rule
  rule_evidence
  rule_test
```

No graph DB is required for this deterministic foundation.

### 11.1 What belongs in PostgreSQL

- stable KMX identity and parent/child containment
- external identifier crosswalks
- source/version registry
- source-block metadata and raw-object pointers
- approved Clinical Evidence
- deterministic Rules and Rule-Evidence links
- test fixtures/status
- mapping exceptions

### 11.2 What does not belong in the production DB

- entire upstream relational databases when only a subset is needed
- original PDFs/ZIPs/large archives
- secrets/API keys
- unreviewed OCR as active clinical truth

## 12. DBeaver / DB viewer workflow

DBeaver connects from the operator laptop to OVH Managed PostgreSQL using TLS.

Use it to inspect:

```text
kmx.registry
  -> ING / CD / PROD rows

kmx.external_identifier
  -> deterministic source crosswalks

evidence.clinical_evidence
  -> KMX + category + source + jurisdiction + status

rules.clinical_rule
  -> target KMX + category + jurisdiction + active status

rules.rule_evidence
  -> exact Evidence packages supporting each Rule

kmx.mapping_exception
  -> identity problems requiring review
```

Create views for coverage and QA rather than adding more storage layers.

## 13. Full Rule model

Rule creation condition:

```text
APPROVED EVIDENCE
   |
   +-- patient condition/trigger present?
   +-- clinical decision/verdict present?
   +-- action present?
          |
          +-- all yes -> Rule candidate
          +-- otherwise -> Evidence only
```

A full Rule contains:
1. target medicine
2. category
3. patient trigger
4. required patient data
5. verdict
6. verdict reason
7. severity
8. severity reason
9. immediate clinical action
10. action reason
11. recommendation
12. recommendation reason
13. alternatives + reason, only when supported
14. patient-specific risk factors + reasons
15. monitoring + why/when, only when supported
16. follow-up + why/when, only when supported
17. connected Clinical Evidence

Frozen inheritance:

```text
Rule.target_kmx_id = Evidence.kmx_subject
Rule.target_level  = Evidence.truth_level
Rule.category      = Evidence.category
Rule.jurisdiction  = Evidence.jurisdiction
```

The Rule builder never maps the medicine again.

### Rule-Evidence field support

`rule_evidence.supports_fields[]` says which Evidence package supports which Rule fields. Example:

```text
primary regulatory Evidence -> verdict / severity / action
approved guideline Evidence -> recommendation / alternatives / monitoring when explicitly supplied
supporting biomedical Evidence -> explanation only, never a silent change to clinical action
```

## 14. Rule validation and tests

Before activation:
1. target KMX exists
2. Rule KMX equals Evidence KMX
3. Rule target level equals Evidence truth level
4. Rule category equals Evidence category
5. primary source role is eligible to create a Rule
6. trigger uses known patient-context primitives
7. every clinical value exists in connected Evidence or approved deterministic policy
8. action is evidence-backed
9. alternatives are evidence-backed
10. monitoring is evidence-backed
11. follow-up is evidence-backed
12. required-data list covers every trigger input
13. tests pass

Minimum tests:

```text
MATCH
NO_MATCH
CANNOT_FULLY_EVALUATE
```

If required patient information is missing, return `CANNOT_FULLY_EVALUATE`, not `NO_MATCH`.
For CD/PROD-specific Rules, include a wrong-formulation/product test that must return `NO_MATCH`.

## 15. OVH VM responsibilities

The VM runs the data-engineering work, not the authoritative database.

```text
Python runtime
source adapters
HTTP client
XML/JSON parsers
PDF parser
OCR fallback
TSV/CSV/Parquet readers
temporary PostgreSQL/SQLite restore when needed
S3-compatible Object Storage client
Managed PostgreSQL client
KMX resolver
Evidence builder
Rule builder
validators/tests
```

The VM can be replaced. The durable state is Object Storage + Managed PostgreSQL + GitHub code/config.

## 16. GitHub repository architecture

```text
Kemirix_knowledge_database_Medicine/
├── README.md
├── SKILL.md
├── .gitignore
├── .env.example
├── pyproject.toml
├── docs/
│   ├── ARCHITECTURE.md
│   ├── KMX_IDENTITY.md
│   ├── SOURCE_MATRIX.md
│   ├── CLINICAL_EVIDENCE.md
│   ├── RULES.md
│   ├── OBJECT_STORAGE.md
│   ├── MANAGED_DATABASE.md
│   ├── DBEAVER.md
│   ├── VM_ARCHITECTURE.md
│   ├── API_RATE_LIMITING.md
│   └── EXECUTION_PLAN.md
├── config/
│   ├── categories.yaml
│   ├── jurisdictions.yaml
│   ├── database.yaml
│   ├── object_storage.yaml
│   ├── source_schema.yaml
│   └── sources/
│       └── 27 source configuration files (S01-S27)
├── src/
│   ├── kmx/
│   ├── evidence/
│   ├── rules/
│   ├── storage/
│   ├── database/
│   └── sources/
│       └── one adapter folder per approved source lane
├── migrations/
│   ├── 001_kmx.sql
│   ├── 002_evidence.sql
│   └── 003_rules.sql
├── scripts/
│   ├── ingest_source.py
│   ├── resolve_kmx.py
│   └── build_rules.py
└── tests/
    ├── kmx/
    ├── evidence/
    └── rules/
```


### What each major folder does

- `docs/`: human architecture/reference documents.
- `config/`: controlled categories, jurisdictions, DB/Object Storage settings, and one source contract per lane. Live access coordinates stay outside the distributed repository or in a private secret-backed operator configuration.
- `src/kmx/`: identity mint/reuse, containment and external-ID resolution.
- `src/evidence/`: source-block-to-Evidence construction and category mapping.
- `src/rules/`: shared Rule builder/validator/evaluator; no source-specific prescribing engines.
- `src/storage/`: Object Storage and manifest helpers.
- `src/database/`: Managed PostgreSQL connections/repositories.
- `src/sources/`: one adapter folder per source lane.
- `migrations/`: only three logical stages: KMX, Evidence, Rules.
- `scripts/`: operator entry points.
- `tests/`: identity, Evidence, Rules and end-to-end canaries.

### Minimal adapter contract

```python
class SourceAdapter:
    def acquire(self): ...
    def save_original(self): ...
    def verify_hash(self): ...
    def iter_source_items(self): ...
    def resolve_kmx(self, item): ...
    def create_source_blocks(self, item): ...
    def build_full_evidence(self, item): ...
    def validate(self): ...
```

Do not put Rule logic in each adapter. A shared Rule builder consumes approved Evidence.

## 17. Worked identity/Evidence example - no remapping

```text
Baseline terminology
  -> Ingredient identity for Medicine X
  -> KMX-ING-000001

Formulation record
  -> Medicine X + formulation attributes
  -> KMX-CD-000101

Regulator product record
  -> KMX-CD-000101 + stable product identity
  -> KMX-PROD-001001
```

Now a regulatory product document may mechanically join to `KMX-PROD-001001`.

If a section applies to Medicine X regardless of formulation:

```text
join_level = product
truth_level = ingredient
kmx_subject = KMX-ING-000001
```

If a section depends on the exact formulation:

```text
join_level = product
truth_level = clinical_drug
kmx_subject = KMX-CD-000101
```

If it depends on the specific product/excipient:

```text
join_level = product
truth_level = product
kmx_subject = KMX-PROD-001001
```

When approved Evidence is executable, the Rule copies that exact `kmx_subject`, `truth_level`, `category`, and `jurisdiction`.

## 18. End-to-end execution plan

### Phase 1 - infrastructure
1. Provision OVH Managed PostgreSQL.
2. Provision one S3-compatible Object Storage bucket.
3. Provision one ingestion/processing VM.
4. Configure TLS DB access and DBeaver.
5. Configure secrets outside GitHub.

### Phase 2 - KMX baseline
1. Load the pinned standardized terminology release.
2. Mint/reuse KMX-ING.
3. Mint/reuse KMX-CD.
4. Build `kmx.contains` including combination medicines.
5. Build external-ID bridges.
6. Create `mapping_exception` workflow.

### Phase 3 - KMX-PROD
1. Ingest approved regulatory product catalogues.
2. Resolve ING.
3. Resolve unique CD.
4. Create/reuse regulator-proven PROD.
5. Persist product external identifiers.

### Phase 4 - Evidence foundation
1. Create source/version/source_block tables.
2. Create the 24-category registry.
3. Implement one structured regulatory lane end-to-end first.
4. Build full source-specific Evidence.
5. Verify ING/CD/PROD truth-level selection.

### Phase 5 - primary clinical lanes
Add regulatory/guideline sources one at a time. Each adapter must pass the same acceptance contract before the next is enabled.

### Phase 6 - Rules
1. Create `clinical_rule`, `rule_evidence`, `rule_test`.
2. Compile only executable approved Evidence from eligible primary lanes.
3. Validate inheritance and field support.
4. Run MATCH / NO_MATCH / CANNOT_FULLY_EVALUATE tests.
5. Human-review before activation.

### Phase 7 - supporting biomedical lanes
Add support sources only after primary Evidence/Rule flow works. They improve explanation/coverage but never become a hidden second prescribing authority.

### Phase 8 - scale
Start with one medicine identity family as the canary. Once ING/CD/PROD + Evidence + Rules are correct, repeat the exact adapter pattern across the catalogue.

## 19. Source integration acceptance checklist

A source is **not integrated** just because it was downloaded.

For every Sxx lane, prove:

```text
source version recorded
raw original stored and hashed
source item parsed
KMX resolution deterministic
no unresolved conflict
source blocks preserve exact location
category mapping controlled
Evidence package is complete and source-specific
Rule eligibility obeys source role
Rule inherits KMX/category/jurisdiction from Evidence
tests pass
DBeaver query can show the full chain
```

Trace should look like:

```text
Sxx source record
  -> object_storage_key
  -> source_block(s)
  -> KMX join
  -> full Evidence package
  -> optional Rule
  -> rule_evidence link back to Evidence
```

## 20. What agents must never do

- never invent a KMX mapping
- never merge salt/base/ingredient identities just because names look similar
- never create PROD from a brand-like name without product/regulator proof
- never turn classification membership into clinical Evidence
- never turn mechanism/target binding into a prescribing Rule
- never treat a duplicate label projection as independent corroboration
- never arbitrary-token-chunk regulatory/guideline documents and lose headings/context
- never silently repair OCR/table numbers
- never write raw giant source DBs into the production knowledge schema
- never create a Rule before approved Evidence exists
- never invent alternatives/monitoring/follow-up absent from the connected Evidence
- never store API keys in GitHub or Object Storage manifests
- never skip `mapping_exception` for ambiguity

## 21. Operator review dashboard queries - conceptual

DBeaver should make these questions easy:

```text
Show all ING/CD/PROD children for one KMX ingredient.
Show every external identifier mapped to one KMX.
Show every approved Evidence package under KMX + category + jurisdiction.
Show every active Rule under KMX + category + jurisdiction.
Show the Evidence packages supporting one Rule.
Show all unresolved mapping exceptions.
Show source coverage gaps by KMX/category.
```

## 22. Final frozen architecture

```text
27 APPROVED SOURCE LANES
        |
        v
OVH VM - acquire / hash / parse / resolve
        |
        +--------------------> OVH OBJECT STORAGE - raw immutable originals
        |
        v
KMX IDENTITY - ING / CD / PROD
        |
        v
SOURCE BLOCKS
        |
        v
FULL SOURCE-SPECIFIC EVIDENCE
KMX + truth level + category + source + jurisdiction
        |
        +---- non-executable ----> Evidence only
        |
        +---- executable --------> FULL RULE
                                    exact same KMX/category/jurisdiction
        |
        v
OVH MANAGED POSTGRESQL
        |
        v
DBEAVER / API / downstream clinical runtime
```

**One sentence for every agent:**

> Resolve the source item to KMX-ING, KMX-CD or KMX-PROD first; preserve the source as traceable blocks; build a full source-specific Evidence package under the correct KMX + category; and only then compile an executable Rule that inherits that exact identity and category.
