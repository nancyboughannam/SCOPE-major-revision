# Validation of the publication checkout

Validation environment: Linux, JDK 21, Python 3.12 and the pinned v5 dependencies.

## Checks performed

- 76 unit/integration tests passed using `unittest discover -s FLaskAPIs`.
- The cleaned checkout compiled an isolated simulator build with the retained JARs.
- All 56 Java sources, nine libraries and six AI-based Weka model files matched
  the frozen v5 Git objects. Ten active optimizer/training/support Python files
  were also unchanged; hashes are in `SOURCE_PROVENANCE.json`.
- Ten six-minute collection scenarios (iterations 3001–3005, 900/1800 vehicles)
  ran from the cleaned checkout, producing raw candidate-window data and verified
  completion receipts. This is smoke data, not publication evidence.
- The separate EXP3 routing runner completed two ten-minute Java/Flask smoke
  scenarios with the guard off and retained 20 unchanged source-study scenarios.
  Their non-EXP3 metric rows were identical. See `VALIDATION_EXP3_GUARD_ABLATION.md`.
- Interruption, service cleanup, resuming without repeating completed jobs,
  unchanged source receipts, routing-schema checks and review-ZIP creation passed.
- Local Markdown links were checked. The published-file hash verifier excludes
  generated experiment output and checks all listed source/input/library bytes.

## Limits

The full 50-scenario guard-off rerun is to be executed by Nancy. This cleanup did
not rerun the complete 60-minute training/confirmation study. Training and model
code are unchanged, but reproduction on a new platform still needs its own logs,
readiness checks and model/version provenance. No performance ranking is certified.

MATLAB is unavailable in this environment. The plotting source and data contracts
were checked, but final rendering must be verified in MATLAB with Times New Roman.
After the full rerun, archive the exact outputs, source commit and model manifests
before describing the branch as the final publication release.
