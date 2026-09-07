# Clinical Evidence

## Core rule

Every clinical source block is connected to the correct KMX subject and one shared Kemirix category.

```text
SOURCE DOCUMENT/RESPONSE
  ↓
SOURCE BLOCK
  ↓
KMX SUBJECT
  ↓
CATEGORY
  ↓
FULL SOURCE-SPECIFIC EVIDENCE PACKAGE
```

## 24 categories

1. indication
2. contraindication
3. drug_disease
4. drug_drug
5. drug_food_substance
6. allergy_hypersensitivity
7. dosing
8. renal
9. hepatic
10. paediatric
11. geriatric
12. pregnancy
13. lactation
14. laboratory
15. vital_signs
16. monitoring
17. adverse_effects
18. duplication
19. polypharmacy
20. administration
21. high_alert_safety
22. pharmacogenomic
23. treatment_appropriateness
24. counselling

## Evidence identity

Every Evidence package must answer:

- Which KMX medicine?
- Which KMX level: ING/CD/PROD?
- Which category?
- Which source?
- Which jurisdiction?
- Which original source block(s) support the package?
- What is the complete clinical content from that source?

## Regulatory heading mapping

Typical regulatory sections map as follows:

- Indications → `indication`
- Dosage/Posology → `dosing`
- Method of administration → `administration`
- Contraindications → `contraindication` and, when appropriate, `allergy_hypersensitivity`
- Warnings/Precautions → relevant `drug_disease`, `renal`, `hepatic`, `monitoring`, `laboratory`, `high_alert_safety` etc.
- Interactions → `drug_drug` / `drug_food_substance`
- Pregnancy → `pregnancy`
- Lactation → `lactation`
- Paediatric → `paediatric`
- Geriatric → `geriatric`
- Adverse reactions → `adverse_effects`
- Patient advice → `counselling`

A source heading is not itself the category when the content clearly belongs to a more specific clinical category.

## Source separation

DailyMed Evidence remains DailyMed Evidence. EMA Evidence remains EMA Evidence. KDIGO Evidence remains KDIGO Evidence. Different source packages are not silently merged into one package.
