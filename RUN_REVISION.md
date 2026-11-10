# Running the telemetry-consistent revision

For the automatic paired workload-change diagnostic, see
[RUN_ADAPTATION.md](RUN_ADAPTATION.md). It manages the Python service and both
Java executions, so stop the launcher described below before using it.

This branch corrects CPU telemetry units and coverage, stores objective
normalization in the model manifest, and validates optimizer responses before
applying them. It does not change the tier-routing hierarchy.

## Model compatibility

Old CPU-dependent models expect the old telemetry semantics. Do not combine
those models with corrected telemetry. Either collect fresh candidate data
using this simulator and train with
`--telemetry-schema vm_percent_all_vms_v1`, or train from legacy candidate data
with `--exclude-cpu-telemetry`. The latter excludes the two CPU inputs; it
cannot recover readings that were previously clipped.

From `FLaskAPIs`, using fresh output directories:

```bash
python prepare_candidate_dataset.py --input /path/to/candidate_windows.csv --output-dir revision_training_v4/dataset --seed 42
python train_candidate_xgboost.py --data-dir revision_training_v4/dataset --output-dir revision_training_v4/xgboost_results --exclude-cpu-telemetry
```

Training writes target support from the training split into
`model_manifest.json`. Both services must use that same normalization.
Legacy manifests retain the historical reference bounds with a warning for
reproduction; the revised launcher requires explicit manifest bounds.

## Matched services

Use the existing Python environment with Flask, NumPy, pandas and XGBoost.
RT_OPT additionally requires OR-Tools. Stop separately running services first.
Keep this terminal open while Java runs:

```bash
python run_revision_services.py --models revision_training_v4/xgboost_results --output revision_results/new_experiment --diagnostic --include-rt-opt
```

The launcher defaults to lambda 0.20 and explicitly uses R_max 0.15, full-catalogue EXP3,
equal failure/service weights and the existing common candidate catalogue.
It records settings and model/source hashes, verifies service readiness and
normalization, and refuses existing output directories or occupied ports.
`--catalogue /path/to/catalogue.csv` overrides the shared candidate source.
Omit `--include-rt-opt` when the simulation does not use RT_OPT.
Omit `--diagnostic` for overhead measurements: full request diagnostics add I/O.

For a declared development sensitivity study, add `--lambda 0.05` (or another
value in [0,1]). This overrides the SCOPE switching penalty only; the hard
budget remains 0.15 and EXP3's objective is unchanged. Every experiment must
use a new output directory. The selected value is recorded in `experiment.json`.
Keep calibration runs separate from the final evaluation and report the
performance/churn tradeoff across all tested settings.

Rebuild Java from this branch. Add this **VM option**, separately from the
five program arguments:

```text
-Dscope.optimizer.failFast=true
```

Keep the existing program argument format: properties file, edge-device XML,
application XML, fresh results directory, iteration number. Preserve the exact
input configurations and invocation beside the Python and Java outputs.
All comparisons affected by the telemetry correction need fresh runs.

## Checks and analysis

```bash
python FLaskAPIs/test_scope_objective.py
python FLaskAPIs/test_exp3_revision.py
python FLaskAPIs/test_edge_vm_fix.py
python FLaskAPIs/analyze_revision_zip.py /path/to/results.zip --output /path/to/fresh-analysis
```

The Java test runner needs a JDK with `java` and `javac` on PATH. It compiles
the simulator, checks selection/capacity, scheduler units, all-VM telemetry,
complete response validation and normalized distance, then runs isolated smoke
scenarios. These are correctness checks, not evidence of policy superiority.

The ZIP analyzer accepts arbitrary iteration IDs. It reports per-run metrics,
means, sample standard deviations and seed evidence. Its service-time metric
is conditional on completed tasks; pending tasks remain separately visible.
It does not infer statistical significance or policy causality.

Java churn logs now use the same seven-coordinate, range-normalized mean as
Python. Do not compare these values directly to old Java churn logs. The hard
budget is per update over that aggregate distance; it is not a queue-stability,
deadline or per-coordinate guarantee.
