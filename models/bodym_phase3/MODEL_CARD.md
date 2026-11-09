# Model card — BodyM Phase 3 research fusion

## Identity / intended use

Research-only checkpoint `models/bodym_phase3/fusion/model.pt`; trained from scratch on BodyM silhouettes.
Does not replace the selected default `models/bodym_cnn/model.pt`. For reproducible adult body-circumference research, non-commercial use pending license clarification.
Inputs: ordered front/side binary silhouettes, provided height (cm), weight (kg), gender encoded by dataset male/female labels. Outputs: chest/waist/hip (cm).
Does not infer gender, fat percentage, muscle mass, visceral fat or InBody values. Not validated for RGB phone photos, diagnosis, children, pregnancy or clinical planning.

## Dataset / training

Seed 42; proper fit 1291, epoch tuning 404, calibration 323, final refit 1695 subjects.
Calibration subjects excluded from all new fitting, target/metadata normalization, BatchNorm and epoch selection. Split list/hashes/configs saved with experiment.
Labels computed from registered 3D-scan meshes. Multiple photos per person; subject-balanced training/metrics. testA/testB share one subject, reported separately.
Existing architecture/hyperparameters and test sets were explored earlier; the new protocol cannot undo historical adaptive reuse.

## Calibration / uncertainty

Fixed 90% nominal subject-max split conformal. Each calibration subject contributes one maximum residual per target across all their photos; joint score also maximizes across targets.
Theoretical coverage needs exchangeability of subject bundles and an independently fixed predictor. Different photo counts, capture domains and historical selection limit that interpretation here.
Empirical coverage/widths are research metrics, not per-person certainty or clinical tolerance. Calibration is cryptographically bound to its checkpoint; never attach it to the all-train default model.

## Evaluation

Checkpoint SHA256: `b4f22b0152aff8401f19a1a2aa2a583a2a36bb6db2eece3d5c89932cfd62750a`.
Parameters: 141443; selected epoch: 58.

- testA: mean MAE 2.127 cm; joint all-photo subject coverage 88.5%; joint full width 14.864 cm.
- testB: mean MAE 2.636 cm; joint all-photo subject coverage 81.0%; joint full width 14.864 cm.

Full per-target MAE/RMSE/bias, subgroup errors, interval widths and novelty-flag strata: `experiments/bodym_phase3/metrics.json`.
The fusion intervals did not reach the nominal 90% joint coverage on these tests. The uncertainty deployment gate is not met. No radius was retuned on test outcomes.

## Limitations / deployment gate

One seed, no independent RGB/OOD benchmark, no age/ethnicity/device subgroup labels, binary gender labels inherited from source, no validated acceptable-error threshold.
Novelty score is a training-derived heuristic, not a safety classifier. Mask quality flags cannot certify anatomical completeness/pose. Do not suppress flags or treat predictions as observed measurements.
Silhouette/image research needs protected storage and separate processing/research consent before collecting user data. No production authentication, retention or medical safety screening is supplied by this research pipeline.
Requires new consented paired-data evaluation, uncertainty/domain validation and application review flow before user-facing release.

Sources: [BodyM](https://registry.opendata.aws/bodym/), [measurement provenance](https://adversarialbodysim.github.io/), [conformal reference](https://arxiv.org/abs/2107.07511).
