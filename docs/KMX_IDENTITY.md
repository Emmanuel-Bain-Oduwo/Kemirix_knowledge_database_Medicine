# KMX Identity

## The only three medication identity levels

### KMX-ING
Ingredient identity. RxNorm Ingredient/RXCUI is the main starting point. External identifiers such as UNII, ChEMBL, ChEBI, MED-RT and CIEL are crosswalks to the existing ingredient identity.

### KMX-CD
Clinical drug identity: ingredient plus clinically meaningful formulation attributes such as strength, dose form, release type, concentration and route where route is clinically identity-defining.

### KMX-PROD
Actual regulated/commercial product identity. It requires a real product identity such as PPB registration, EMA product/authorisation identity or MHRA PL/PLGB identity.

## Resolution rule

```text
source identifier
   ↓
exact external identifier match if available
   ↓
KMX-ING / KMX-CD / KMX-PROD
```

If no exact identifier exists, use controlled normalized medicine name and formulation attributes. If there are zero or multiple plausible identities, stop and send the record to `kmx.mapping_exception`. Do not guess.

## Sources with mixed KMX levels

DailyMed, openFDA Label, PPB Product Register, PPB SmPC, EMA and MHRA can connect to ING, CD and PROD. Resolve the source record mechanically first, then assign the Evidence to the level the clinical statement truly applies to:

- ingredient-wide statement → ING
- formulation-specific statement → CD
- product/excipient/holder-specific statement → PROD

## Parent relationship

```text
KMX-ING
  ↓
KMX-CD
  ↓
KMX-PROD
```

A combination clinical drug can contain more than one ingredient KMX.
