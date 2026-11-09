# InBody oracle smoke result

**Synthetic fixtures only — real InBody accuracy is unknown.**

Documents: 8; split: smoke_test; real documents: 0.
Field F1: 1.0; document success: 1.0.
CER: None; WER: None.

| Field | Unit | Labeled | Paired | MAE | Exact |
| --- | --- | ---: | ---: | ---: | ---: |
| weight_kg | kg | 8 | 8 | 0.0 | 8 |
| height_cm | cm | 8 | 8 | 0.0 | 8 |
| skeletal_muscle_mass_kg | kg | 8 | 8 | 0.0 | 8 |
| body_fat_mass_kg | kg | 8 | 8 | 0.0 | 8 |
| percent_body_fat | % | 8 | 8 | 0.0 | 8 |
| total_body_water_l | L | 7 | 7 | 0.0 | 7 |
| ecw_tbw_ratio | ratio | 8 | 8 | 0.0 | 8 |
| basal_metabolic_rate_kcal | kcal/day | 8 | 8 | 0.0 | 8 |
| bmi | kg/m2 | 8 | 8 | 0.0 | 8 |

## Error analysis


Only simple English rows, one original renderer, clean scans and decimal dot/comma are covered.
No real sheets, phone-photo distortions, Vietnamese OCR or multi-column/segmental layouts tested.
Oracle mode bypasses OCR and must not be reported as OCR accuracy. Bounds are engineering checks, not clinical advice.
