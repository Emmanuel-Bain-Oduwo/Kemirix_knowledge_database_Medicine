# Deterministic Rules

## When Evidence becomes a Rule

A Rule is created only when approved Evidence contains an executable patient-specific decision:

```text
PATIENT TRIGGER
+
CLINICAL DECISION / VERDICT
+
ACTION OR RECOMMENDATION
```

Mechanism-only, classification-only or signal-only data does not independently create prescribing Rules.

## Rule identity inheritance

```text
Rule.target_kmx_id = Evidence.kmx_subject
Rule.target_level  = Evidence.kmx_level
Rule.category      = Evidence.category
Rule.jurisdiction  = Evidence.jurisdiction
```

No second medicine-resolution step is allowed at Rule creation.

## Full Kemirix Rule

1. Target medicine
2. Category
3. Patient trigger
4. Required patient data
5. Verdict
6. Verdict reason
7. Severity
8. Severity reason
9. Immediate action
10. Action reason
11. Recommendation
12. Recommendation reason
13. Alternatives + reason
14. Patient-specific risk factors + why
15. Monitoring: what + why + when
16. Follow-up: what + when + what changes the plan
17. Connected Clinical Evidence

If the connected Evidence does not provide a field, it must remain explicitly not specified rather than being invented.

## Rule sources

Primary Rule sources in this architecture: DailyMed, PPB SmPC, EMA SmPC, MHRA SPC, KNMF when approved for use, Kenya MoH guidance, WHO actionable guidance, KDIGO when explicit/computable, and CPIC/ClinPGx guideline recommendations.

Supporting biomedical sources can support/explain Evidence but do not independently generate high-stakes clinical actions.
