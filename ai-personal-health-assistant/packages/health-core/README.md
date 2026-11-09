# Research core snapshot

Portable Phase 1 parser/review and Phase 4 progress engine. No PyTorch/Paddle or model checkpoint is imported at API startup. The only code transformations are the package import and field registry resource path. `source-manifest.json` records original and packaged hashes; run `python scripts/check_research_core.py` from the monorepo to audit drift. Update the snapshot explicitly after reviewing research changes. Configs ship as package data so Docker needs no parent research directory.
