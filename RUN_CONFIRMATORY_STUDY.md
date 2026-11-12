# V5 confirmation: ten fresh iterations

This workflow freezes lambda at **0.01**, Rmax at **0.15**, the trained v5
models, the input XML/properties and the comparison plan. Iterations
**3401–3410** are separate from training, static calibration, the v5 development
pilot, the lambda check and the old v4 study. It does not collect data or retrain.

Use the existing `SCOPE-v5-testing` worktree. Keep the original
`SCOPE-major-revision` worktree and all prior results. No PR merge, downloaded
setup ZIP, manual file replacement or NetBeans configuration is required.

## 1. Update the code in the Mac terminal

Stop any existing simulator/service launcher with Ctrl+C first. Then:

```bash
cd ~/Documents/SCOPE-v5-testing &&
git pull --ff-only
```

The branch should be `codex/deadline-aware-pilot`. The explicit Python path
below uses the established environment even if the terminal prompt says `(base)`.

## 2. Prepare and validate inputs

```bash
../SCOPE-major-revision/FLaskAPIs/.venv-revision/bin/python \
  FLaskAPIs/run_confirmatory_study.py prepare
```

Expected: `PREPARED: 400 evaluation scenarios; no retraining.` This command does
not run a simulation. It checks the model-readiness gate, package versions,
matching SCOPE/EXP3 normalization, JDK 21+, available service ports and the frozen
source hashes. It copies the source runtime and models into a new study folder.
No fresh Java compilation is needed: it uses the verified compiled v5 runtime.

Source: `ThreeBrains/sim_results/v5_deadline_pilot`.

New output: `ThreeBrains/sim_results/v5_final_3401_3410`.

Static calibration uses the same training-only shortlist rule and calibration
iterations 3201–3202 as the pilot. Compatible completed calibration jobs are
verified and copied. A completed full pilot normally provides 24 of 40 cases;
the 16 remaining cases cover 600 and 1500 vehicles. If the pilot stopped earlier,
the launcher reuses every verified completed case and runs the remaining cases
automatically. It never reruns model training. The static control is selected
before any confirmation scenario starts; no confirmation outcomes choose it.

## 3. Start the full study

```bash
caffeinate -i ../SCOPE-major-revision/FLaskAPIs/.venv-revision/bin/python \
  FLaskAPIs/run_confirmatory_study.py run
```

Keep this terminal open, the Mac powered and its lid open. Allow the registered
batch to finish regardless of which policy wins early iterations. The launcher
first finishes missing static calibration, then runs all 400 evaluation cases
sequentially. It prints the active job, its log path and its completed metrics.

It starts SCOPE's service on 5002 or EXP3's service on 5003 only when needed,
stops it after that scenario, and supplies the Java arguments itself. Do not
start `ml_optimizer_service.py`, `exp3_mc_service.py`, `Optimizer.py` or NetBeans
runs alongside it. RT_OPT is not included, so port 5001 is not required.

Expected final line: `Completed 400/400 evaluation scenarios; verified 10 frozen pairs.`

## Fixed comparison plan

Every scenario lasts 60 simulated minutes, with a three-minute warm-up.
Each of the ten independent iterations has 40 evaluation scenarios:

| Component | Vehicles | Policies | Scenarios across 10 iterations |
| --- | --- | --- | ---: |
| Main | 600, 900, 1200, 1500, 1800 | SCOPE, AI_BASED, EXP3_MC, RAIDER_TRAX, RANDOM, calibrated SCOPE_STATIC | 300 |
| Additional ablations | 1800 | HARD_ONLY, SOFTCOST_OPT, PERFORMANCE_ONLY | 30 |
| Increase/recovery | 1200 | SCOPE, matched frozen SCOPE, calibrated static, hard-only, soft-only, performance-only, AI_BASED | 70 |

The ablation figures reuse the existing main SCOPE and static results at 1800;
they do not simulate or count those observations twice.

| Controller | Switching penalty | Hard movement limit |
| --- | ---: | --- |
| SCOPE | 0.01 | 0.15 |
| HARD_ONLY | 0 | 0.15 |
| SOFTCOST_OPT | 0.01 | Disabled |
| PERFORMANCE_ONLY | 0 | Disabled |
| Calibrated static | No online updates | Not applicable |

HARD_ONLY is a reporting label: Java uses policy SCOPE with lambda zero. Both
SCOPE and the frozen variant use the unchanged v5 routing and scoring code.
The new launcher changes no simulator or optimizer algorithm.

EXP3 retains the full training catalogue, QoS threshold 0.20, its recorded
automatic learning-rate rule, admission-cohort feedback and the same
training-only normalization as SCOPE. Each scenario has a fresh service process.
AI_BASED, RAIDER_TRAX and RANDOM retain their existing routing implementations.

In the increase/recovery case, arrivals multiply by 1.5 at 1200 seconds and
return to baseline at 2400 seconds. Frozen SCOPE follows ordinary SCOPE before
the increase, then holds the configuration already in force at the first later
request (1210 seconds). It remains frozen through recovery. Its task stream,
pre-intervention requests and reporting windows must match the adaptive run.

## Stop, resume and inspect progress

Press Ctrl+C once and wait for `STOPPED safely`. The runner terminates its own
Java/Flask children. Completed jobs have verified receipts; partial attempts
are retained but excluded from the results. Repeat the step-3 command to resume.

From another Mac terminal:

```bash
cd ~/Documents/SCOPE-v5-testing
../SCOPE-major-revision/FLaskAPIs/.venv-revision/bin/python \
  FLaskAPIs/run_confirmatory_study.py status
```

Use `stop` instead of `status` to request a graceful stop. Do not change code,
models, package versions or registered inputs during the batch. Changed inputs
are rejected on resume. An interrupted preparation needs a fresh `--output`;
an interrupted simulation resumes in the existing output with a new attempt.

For a technical check of one full iteration, `run --iteration 3401` is available.
It still completes static calibration first. Repeating `run` without that option
then skips the verified iteration and completes the rest. Do not use the first
iteration's ranking to change the protocol or decide whether to keep the others.

An optional `--output /new/path` is supported; repeat it in every later command.
The source and output must be separate, non-nested directories. `package` and
`run` reject a concurrent writer. `status` reads the receipt count without taking
the run lock; it is a progress indicator, not a replacement for final verification.

## 4. Generate figures in MATLAB

After all 400 scenarios complete, use the **MATLAB Command Window**:

```matlab
cd('/Users/nancyboughannam/Documents/SCOPE-v5-testing/ThreeBrains/sim_results/v5_final_3401_3410/matlab')
plot_confirmatory_results
```

Figures are saved as vector PDF, 300-dpi PNG and editable FIG in separate
`figures/main`, `figures/ablations` and `figures/adaptation` folders. Main plots
cover failed tasks, service/processing/network time, QoE and edge/cloud VM
utilization. Application-specific failure, service and QoE plots are included.
The script refuses incomplete cells or an unfinished study. MATLAB rendering
must be performed locally; the runner only prepares its plotting inputs.

## 5. Package the evidence

After MATLAB finishes, or after stopping a run for troubleshooting:

```bash
../SCOPE-major-revision/FLaskAPIs/.venv-revision/bin/python \
  FLaskAPIs/run_confirmatory_study.py package &&
open ThreeBrains/sim_results
```

Send `v5_final_3401_3410_review_*.zip`. It includes logs, model reports, copied
calibration evidence, every policy outcome, movement traces, pairing checks,
MATLAB figures if generated, and the executed service/runner source snapshots.
Large duplicate runtime libraries and Weka binaries are excluded, so this is a
review package rather than a complete movable/resumable execution directory.

## Interpretation fixed before confirmation

- Failures use completed + failed as the denominator. Unfinished tasks are
  retained separately. Service time is conditional on completion; it cannot
  establish better performance without considering failures alongside it.
- Mean/95% t intervals use the ten independent seeds. Tasks, applications and
  reporting windows are not additional independent replications.
- `paired_comparisons.csv` reports SCOPE-minus-comparator differences on the
  same seeds. Negative values favor SCOPE for the two primary metrics.
  Unadjusted paired t intervals and raw p-values are provided. Holm correction
  is applied separately to the 50 main tests (five comparators, five loads, two
  metrics), six additional-ablation tests and two matched-frozen adaptation
  tests. State these families when reporting tests. QoE/utilization and phase
  summaries are descriptive/exploratory.
- Phase metrics use outcome-time windows fully inside each phase and after
  warm-up. Boundary-crossing windows are excluded; these are not finalized
  admission cohorts. Response times and absent responses remain visible in
  `adaptation_responses.csv` and `decision_metrics.csv`.
- Movement/change counts include online updates during warm-up. The calibrated
  static controller starts from its selected configuration and makes no online
  changes. Its parameter-movement total is zero. Task-level baselines have this
  metric marked not applicable rather than artificially assigned zero.
- Parameter movement is not measured migration cost. Rmax does not establish
  queue stability or a deadline guarantee. The existing diagnostics add disk
  overhead; these runs do not support production runtime-overhead claims.
- Lambda was chosen using separate development data. Keep every confirmation
  outcome, including unfavorable ones. If an implementation defect forces a
  behavior change, retain the old output and register a new study; do not splice
  different algorithm versions into one final comparison.

Developer smoke profile: use `prepare --profile smoke --output /fresh/path` and
then `run --output /fresh/path`. It uses ten-minute scenarios, new test seeds,
eight static calibration cases and 22 evaluations covering every execution path.
Its models must pass the same readiness gate; there is no override. These smoke
results verify the workflow and must not be mixed with the ten-seed study.
