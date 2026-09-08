# 27-Source Matrix

Frozen registry (DOMAIN-CONTRACT-001, owner-approved SKILL v5.0 section 7/7B.1).
`lane_id` (S01-S27) is the permanent architecture lane; `source_id` is the stable
implementation slug used by configs, code, database and object keys.

| Lane | source_id | Source | Acquisition | KMX | Evidence role | Direct Rules |
|---|---|---|---|---|---|---|
| S01 | rxnorm_athena | RxNorm / Athena baseline | bulk/manual export | ING + CD | identity only | No |
| S02 | athena_extension | Athena extension / RxNorm Extension | bulk/manual export | ING + CD | identity/classification | No |
| S03 | gsrs_unii | GSRS / UNII | API / public dump | ING | identity | No |
| S04 | chebi_unichem | ChEBI / UniChem | bulk DB + API | ING | identity/chemical support | No |
| S05 | medrt | MED-RT | bulk ZIP | ING + CD | supporting | No |
| S06 | dailymed | DailyMed | API | ING + CD + PROD | primary US regulatory Evidence | Yes |
| S07 | openfda_label | openFDA Drug Label | API | ING + CD + PROD | duplicate structured FDA projection | No independent Rule |
| S08 | ppb_register | Kenya PPB Product Register | official web snapshot | ING + CD + PROD | product identity/catalogue | No |
| S09 | ppb_smpc | Kenya PPB SmPC | official PDFs | ING + CD + PROD | primary Kenya regulatory Evidence | Yes |
| S10 | keml | Kenya Essential Medicines List | manual official PDF | ING + CD | catalogue | No |
| S11 | knmf | Kenya National Medicines Formulary | manual official document | ING + CD | primary clinical Evidence when cleared | Yes when executable |
| S12 | kenya_moh | Kenya Ministry of Health guidelines | official PDFs | mainly ING, some CD | primary guideline Evidence | Yes |
| S13 | who | WHO EML / AWaRe / guidance | data/PDF | ING + CD | catalogue/classification + primary actionable guidance | Actionable guidance only |
| S14 | kdigo | KDIGO | guideline PDF | mainly ING, some CD | primary renal Evidence | When explicit/computable |
| S15 | cpic_clinpgx | CPIC / ClinPGx | API | mainly ING | primary PGx guideline + supporting annotations | Guideline recommendations |
| S16 | inxight | NCATS Inxight FRDB | bulk TSV | ING | supporting (supplier/vendor sourcing excluded) | No |
| S17 | drugcentral | DrugCentral | PostgreSQL dump / TSV | mainly ING | supporting | No |
| S18 | onsides | OnSIDES | CSV / SQLite release | ING + CD mapping | supporting adverse effects | No |
| S19 | civic | CIViC | release files / API | ING | supporting oncology/PGx | Not general v1 |
| S20 | chembl | ChEMBL | PostgreSQL/SQLite DB | ING | supporting pharmacology/mechanism (current release resolved dynamically) | No |
| S21 | gtopdb | IUPHAR/BPS Guide to Pharmacology | PostgreSQL/CSV | ING | supporting pharmacology | No |
| S22 | dgidb | DGIdb | TSV/SQL/API | ING | supporting drug-gene | No |
| S23 | open_targets | Open Targets | bulk Parquet | ING | supporting target/disease | No |
| S24 | drugmechdb | DrugMechDB | Git JSON/YAML | ING | supporting mechanism | No |
| S25 | ciel_ocl | CIEL / OCL | export API ZIP | ING + CD | identity/runtime terminology | No |
| S26 | ema | EMA product information | JSON feed + PDFs | ING + CD + PROD | primary EU regulatory Evidence | Yes when executable |
| S27 | mhra | UK MHRA product information | official web/PDF | ING + CD + PROD | primary UK regulatory Evidence | Yes when executable |

## Authority invariants

- S01 creates/reuses KMX-ING and KMX-CD; S08/S26/S27 create/reuse KMX-PROD
  only after ING/CD resolution; all other lanes resolve to existing KMX.
- S07 is a structured projection of duplicate upstream label content and is
  never an independent clinical vote.
- S11 remains authority-gated until an approved official copy and rights
  status are pinned.
- S16 excludes supplier/vendor sourcing data.
- S20 resolves the current approved ChEMBL release dynamically.
- S16-S24 supporting lanes never independently create prescribing authority.
- S26/S27 are regulatory primary lanes when their Evidence is executable.

## Early KMX grouping

### Mainly ING
GSRS/UNII, ChEBI/UniChem, CPIC/ClinPGx, Inxight, DrugCentral, CIViC, ChEMBL, Guide to Pharmacology, DGIdb, Open Targets, DrugMechDB.

### ING + CD
RxNorm/Athena, RxNorm Extension, MED-RT, KEML, KNMF, Kenya MoH, WHO, KDIGO where formulation-specific, CIEL/OCL, OnSIDES mappings.

### ING + CD + PROD
DailyMed, openFDA Label, PPB Product Register, PPB SmPC, EMA and MHRA.
