# 27-Source Matrix

| # | Source | Acquisition | KMX | Evidence role | Direct Rules |
|---:|---|---|---|---|---|
| 1 | RxNorm / Athena | bulk/manual export | ING + CD | identity | No |
| 2 | Athena extra vocab / RxNorm Extension | bulk/manual export | ING + CD | identity/classification | No |
| 3 | GSRS / UNII | API / public dump | ING | identity | No |
| 4 | ChEBI / UniChem | bulk DB + API | ING | identity/chemical support | No |
| 5 | MED-RT | bulk ZIP | ING + CD | supporting | No |
| 6 | DailyMed | API | ING + CD + PROD | primary clinical Evidence | Yes |
| 7 | openFDA Label | API | ING + CD + PROD | duplicate structured FDA projection | No independent Rule |
| 8 | PPB Product Register | official web snapshot | ING + CD + PROD | product identity/catalogue | No |
| 9 | PPB SmPC | official PDFs | ING + CD + PROD | primary Kenya regulatory Evidence | Yes |
| 10 | KEML | manual official PDF | ING + CD | catalogue | No |
| 11 | KNMF | manual official document | ING + CD | primary clinical Evidence when cleared | Yes when executable |
| 12 | Kenya MoH guidelines | official PDFs | mainly ING, some CD | primary guideline Evidence | Yes |
| 13 | WHO EML / AWaRe / actionable guidance | data/PDF | ING + CD | catalogue/classification + primary actionable guidance | Actionable guidance only |
| 14 | KDIGO | guideline PDF | mainly ING, some CD | primary renal Evidence | When explicit/computable |
| 15 | CPIC / ClinPGx | API | mainly ING | primary PGx guideline + supporting annotations | Guideline recommendations |
| 16 | NCATS Inxight | bulk TSV | ING | supporting | No |
| 17 | DrugCentral | PostgreSQL dump / TSV | mainly ING | supporting | No |
| 18 | OnSIDES | CSV / SQLite release | ING + CD mapping | supporting adverse effects | No |
| 19 | CIViC | release files / API | ING | supporting oncology/PGx | Not general v1 |
| 20 | ChEMBL | PostgreSQL/SQLite DB | ING | supporting pharmacology/mechanism | No |
| 21 | Guide to Pharmacology | PostgreSQL/CSV | ING | supporting pharmacology | No |
| 22 | DGIdb | TSV/SQL/API | ING | supporting drug-gene | No |
| 23 | Open Targets | bulk Parquet | ING | supporting target/disease | No |
| 24 | DrugMechDB | Git JSON/YAML | ING | supporting mechanism | No |
| 25 | CIEL / OCL | export API ZIP | ING + CD | identity/runtime terminology | No |
| 26 | EMA SmPC | JSON feed + PDFs | ING + CD + PROD | primary EU regulatory Evidence | Yes |
| 27 | MHRA SPC | official web/PDF | ING + CD + PROD | primary UK regulatory Evidence | Yes |

## Early KMX grouping

### Mainly ING
GSRS/UNII, ChEBI/UniChem, CPIC/ClinPGx, Inxight, DrugCentral, CIViC, ChEMBL, Guide to Pharmacology, DGIdb, Open Targets, DrugMechDB.

### ING + CD
RxNorm/Athena, RxNorm Extension, MED-RT, KEML, KNMF, Kenya MoH, WHO, KDIGO where formulation-specific, CIEL/OCL, OnSIDES mappings.

### ING + CD + PROD
DailyMed, openFDA Label, PPB Product Register, PPB SmPC, EMA and MHRA.
