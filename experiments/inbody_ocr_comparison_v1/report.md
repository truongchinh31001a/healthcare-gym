# PP-OCRv5/v6 and spatial association comparison

**Synthetic engineering regression only. Real report accuracy is unknown.**

Documents: 16; real documents: 0. Each OCR model ran once per input; rows/layout use the same tokens.

| Pipeline | Field precision | Field recall | Field F1 | Whole document exact | Date exact | Mean seconds |
|---|---:|---:|---:|---:|---:|---:|
| v5_rows | 1.0000 | 0.5071 | 0.6730 | 0.5000 | 1.0000 | 5.567 |
| v5_layout | 1.0000 | 0.8214 | 0.9020 | 0.5000 | 1.0000 | 5.571 |
| v6_rows | 1.0000 | 0.5071 | 0.6730 | 0.5000 | 1.0000 | 20.110 |
| v6_layout | 1.0000 | 0.6714 | 0.8034 | 0.5000 | 1.0000 | 20.113 |

V6 + layout is the configured primary research candidate, not an automatic production promotion.
Field exactness includes missing/extra/wrong values; null/null contributes no field true positive.
Spatial recall is available only for layout variants on new fixtures with annotated value cells.
Per-field unit-specific MAE, language/layout groups, OCR CER/WER and error lists are in metrics.json.

## Limits
- Original synthetic regression fixtures, already inspectable; not an untouched real-world test set
- CER/WER are computed on raw full-page OCR, not canonical field lines
- OCR scores are not calibrated field correctness probabilities
- No human correction-rate study, real InBody report, external layout or phone-capture benchmark
- CPU timings exclude startup and model downloads
