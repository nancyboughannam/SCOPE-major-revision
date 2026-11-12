# Reversible deadline-aware SCOPE pilot

This branch is an experimental development workflow. It does not establish
SCOPE's superiority or replace the completed v4 study. Do not merge it into
your working revision branch before reviewing the results.

## Install without changing the existing project

Run in a Mac terminal (an IDE terminal also works). The commands use your
existing Python environment explicitly; no environment activation is needed.
Stop any old Flask launcher with Ctrl+C first.

```bash
cd ~/Documents/SCOPE-major-revision &&
git fetch origin &&
git worktree add -b codex/deadline-aware-pilot ../SCOPE-v5-testing origin/codex/deadline-aware-pilot
```

This creates a separate project folder. It leaves the existing branch,
NetBeans configuration, v4 models and v4 results in their original folder.
If the new folder already exists, stop and inspect it; do not delete or replace it.

```bash
cd ~/Documents/SCOPE-v5-testing
../SCOPE-major-revision/FLaskAPIs/.venv-revision/bin/python \
  FLaskAPIs/run_deadline_pilot.py prepare
```

Preparation checks Python packages, selects JDK 21+, copies the inputs and
source into an isolated output, and compiles Java. It does not start simulations.
If Java cannot be found, add `--java /path/to/jdk-21/bin/java` to `prepare`.

## Start the development workflow

```bash
caffeinate -i ../SCOPE-major-revision/FLaskAPIs/.venv-revision/bin/python \
  FLaskAPIs/run_deadline_pilot.py all
```

The runner starts/stops Java and Flask itself. Do not launch Java from NetBeans
or start a separate optimizer service during this workflow. Keep the terminal
open and the Mac powered. `caffeinate -i` prevents idle sleep while the command runs;
it does not promise continued execution with the lid closed or after a power loss.

The default output is:

`ThreeBrains/sim_results/v5_deadline_pilot`

The runner reports each scenario and its log location. This is not a new final
ten-iteration study. The following stages run in order:

1. **collect:** 10 independent iterations, 3001–3010, at 600, 900, 1200, 1500 and
   1800 vehicles (50 scenarios, 60 simulated minutes, 3-minute warm-up). Collection
   uses the shared new routing rule and does not require an optimizer model.
2. **train:** concatenate only completed collection attempts; group-split by
   iteration using the existing seed-42 splitter; train new XGBoost models with
   corrected CPU telemetry and training-only normalization. Old labels and
   models are never copied into the new model directory.
3. **tune-static:** screen a maximum of four candidate configurations per pilot
   load using training observations (including the initial configuration).
   Evaluate every shortlisted configuration on independent calibration iterations
   3201–3202. Freeze one configuration per known load before pilot testing.
   This is a validation-tuned shortlist baseline, **not an exhaustive best-static
   search**. Its finite budget and training screening are recorded.
4. **pilot:** iterations 1904–1906 at 900, 1200 and 1800 vehicles, comparing SCOPE,
   SCOPE_STATIC, PERFORMANCE_ONLY and AI_BASED (36 scenarios).
5. **adaptation:** the same four methods and three development seeds at 1200
   vehicles. Arrival rates increase by 1.5 at 1200 seconds and return to baseline
   at 2400 seconds (12 scenarios). The static configuration is the previously
   calibrated 1200-vehicle configuration and is not retuned on the burst results.

All learned/configuration methods in this pilot use the same deadline check.
AI_BASED retains its existing decision rule and Weka models; only optional
reporting is added. Lambda stays 0.05 and Rmax stays 0.15. SCOPE_STATIC applies
its configuration before the first task and never calls an optimizer.

The model readiness report is a **gate**. If it does not report
`READY_FOR_OPTIMIZER_INTEGRATION_TEST`, the default workflow stops before the
comparison stages. Inspect/send the report and training log before proceeding.
`--allow-unready-models` exists for explicitly labelled diagnostic experiments;
it is recorded per scenario and must not be treated as validation of weak models.
Passing the prediction gate is still not proof of good closed-loop control.

## Abort and resume

Press **Ctrl+C once** in the running terminal. The runner terminates only the
Java/Python process groups it started, waits for cleanup, then exits with status
130. It never kills an unrelated service occupying a port.

Alternatively, from another terminal in the new project folder:

```bash
../SCOPE-major-revision/FLaskAPIs/.venv-revision/bin/python \
  FLaskAPIs/run_deadline_pilot.py stop
```

Completed scenarios have checksummed completion receipts and are retained.
Partial output is retained in its attempt folder and excluded from training
and comparisons. Repeat the **same `all` command** to resume. The interrupted
scenario restarts from its beginning in a new attempt folder; the simulator
does not support restoring a half-finished scenario. Training likewise restarts
as a new attempt if interrupted. Successfully completed jobs are verified and
skipped. There is no need to manually delete logs or datasets.

For an interrupted **preparation**, choose a fresh output directory; preparation
is not resumed from a partially copied/compiled snapshot. Do not use force quit
as the normal stop mechanism: SIGKILL/power loss cannot run process cleanup.

Check progress without interfering with the runner:

```bash
../SCOPE-major-revision/FLaskAPIs/.venv-revision/bin/python \
  FLaskAPIs/run_deadline_pilot.py status
```

If the experiment is not useful, stop it and return to the original project:

```bash
cd ~/Documents/SCOPE-major-revision
```

No reset, rollback script, file replacement or merge is necessary. Keep the
experimental folder/results until you decide whether to retain them.

## Run one stage at a time

Use `collect`, `train`, `tune-static`, `pilot` or `adaptation` in place of `all`.
Stages check their prerequisites. No input, source, registered setting or model
may change within an existing study. Prepare a new `--output` folder if changing
the implementation or protocol; do not edit the checksums to bypass this rule.
If you choose a custom `--output`, repeat that option on every command, including
`stop`, `status` and `package`.

Example:

```bash
../SCOPE-major-revision/FLaskAPIs/.venv-revision/bin/python \
  FLaskAPIs/run_deadline_pilot.py collect
```

## Results and MATLAB

After successful comparisons (or after requesting `package`), the root contains
`pilot_metrics.csv` and `window_metrics.csv`. The latter describes outcome-time
windows, not admission cohorts. Windows crossing warm-up or a workload transition
must be handled explicitly in any phase-level statistical analysis.

In the **MATLAB Command Window**, not the Mac terminal:

```matlab
cd('/Users/nancyboughannam/Documents/SCOPE-v5-testing/ThreeBrains/sim_results/v5_deadline_pilot/matlab')
plot_deadline_pilot
```

This generates development failure, service-time and QoE graphs from the actual
iterations. Intervals are 95% t intervals across seeds when n > 1; smoke runs
have no confidence intervals. Service time is conditional on completed tasks.
MATLAB must be run locally; this package does not claim the figures were rendered
in the Linux validation environment.

To package completed and partial evidence after stopping:

```bash
../SCOPE-major-revision/FLaskAPIs/.venv-revision/bin/python \
  FLaskAPIs/run_deadline_pilot.py package
open ThreeBrains/sim_results
```

Send the new timestamped `v5_deadline_pilot_review_*.zip`. It contains model
reports, settings, Java/Flask logs, metrics and attempt receipts, while excluding
duplicated Java libraries and Weka binaries. Package generation refuses to run
while another runner owns that output directory.

## Implementation boundaries

`-Dscope.deadlineTierGuard=true` enables the new route check for the shared
configuration executor, including collection, SCOPE/RT_OPT_ML, the ablations,
EXP3_MC, RT_OPT and SCOPE_STATIC. It is **false by default**. RAIDER_TRAX and
AI_BASED retain their existing routing rules. No assignment-capacity fallback
from the earlier diagnostic prototype is enabled or included.

Every optimizer request, dataset and newly trained manifest carries a routing
schema. Models without the new schema remain legacy edge-first models; either
direction of a routing/model mismatch fails instead of silently proceeding.
The prototype uses optimistic execution/network estimates and does not provide
a deadline guarantee or reserve future resources. Rmax bounds parameter movement,
not queue stability, actual migration cost, or deadline compliance.

This pilot does not add a new published switching-aware algorithm or settle every
reviewer comment. Its purpose is to decide whether repaired routing, retrained
prediction and adaptive configuration merit a larger final evaluation.

## Short developer smoke check

```bash
python FLaskAPIs/run_deadline_pilot.py prepare --profile smoke --output /fresh/path/smoke
python FLaskAPIs/run_deadline_pilot.py all --profile smoke --output /fresh/path/smoke --allow-unready-models
```

This uses six-minute scenarios, two loads, five collection seeds, one calibration
seed and one pilot seed. Its explicit override is for plumbing tests only.
Do not use smoke results or smoke-trained models in the manuscript or full pilot.
