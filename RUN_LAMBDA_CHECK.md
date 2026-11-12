# SCOPE lambda calibration and matched frozen controls

This separate experiment reuses the completed v5 training job. It does not
collect data, retrain models, modify Java, or overwrite the original pilot.
The source is `ThreeBrains/sim_results/v5_deadline_pilot`. New results go to
`ThreeBrains/sim_results/v5_lambda_check`.

## Run on Nancy's Mac

Use the Mac terminal. Stop any other Java/Flask launcher first. The explicit
Python path uses the existing environment, even when the prompt says `(base)`.

```bash
cd ~/Documents/SCOPE-v5-testing &&
git pull --ff-only &&
../SCOPE-major-revision/FLaskAPIs/.venv-revision/bin/python \
  FLaskAPIs/run_lambda_check.py prepare
```

Wait for `PREPARED: 27 scenarios, no retraining.` Preparation verifies the
original frozen inputs and training receipt, checks the model-readiness gate,
copies the models and runtime, and loads all six models. Nothing runs yet.
The original source study must be stopped while its snapshot is imported.

```bash
caffeinate -i ../SCOPE-major-revision/FLaskAPIs/.venv-revision/bin/python \
  FLaskAPIs/run_lambda_check.py run
```

Keep the terminal open and the Mac powered with its lid open. The launcher
starts and stops Flask and Java. No NetBeans arguments, separate service
terminals, manual environment variables, or PR merge are needed.

At the end expect `Completed 27/27; verified 9 adaptive/frozen pairs.`
The program exports the data but does not choose a lambda automatically.

## Exactly what is compared

| Setting | Value |
| --- | --- |
| Lambda | 0, 0.01, 0.05 |
| Hard movement limit | Rmax = 0.15 for all settings |
| New calibration iterations | 3301, 3302, 3303 |
| Constant-workload scenario | 1800 vehicles |
| Increase/recovery scenario | 1200 vehicles; arrivals multiplied by 1.5 at 1200 seconds, return to baseline at 2400 seconds |
| Duration and warm-up | 60 minutes and 3 minutes |
| Variants | Adaptive SCOPE in both scenarios; matched frozen SCOPE in the increase/recovery scenario |

The constant case has 3 lambdas x 3 iterations = 9 simulations. The changing
case has 3 lambdas x 3 iterations x 2 variants = 18 simulations. Total: 27.
These calibration seeds differ from collection, original static calibration,
original v5 pilot and the earlier v4 final-study iterations.

**Lambda 0 still has the hard bound.** It is not PERFORMANCE_ONLY, which also
removes the hard bound. This experiment isolates the additional effect of the
soft switching penalty while holding the movement limit fixed.

The frozen variant starts from the same initial configuration and executes
ordinary SCOPE before the increase. At the first optimizer request at or after
1200 seconds it holds the configuration already in force. Requests occur at
70, 130, ... seconds, so the first frozen response is at 1210 seconds. It makes
no new configuration choice from the changed workload. It stays frozen through
recovery. Counterfactual model scores are logged but not applied after freezing.

The service wrapper preserves the original candidate scorer before freezing.
Both variants retain the same Java policy (`SCOPE`), deadline routing, task
stream, reporting events, models, training catalogue and normalization. The
runner verifies identical requests and reporting windows through the first
intervention and identical responses before it. It also checks that every
post-freeze action stays fixed, Java applies preceding responses, and every
actual movement respects Rmax.

## Stop and resume

Press **Ctrl+C once**, then wait for `STOPPED safely`. The launcher terminates
only the Java/Flask process groups it created. Completed jobs are kept with
checksummed receipts. Partial attempts are retained and excluded from results.

To resume, repeat the same `run` command. Verified completed jobs are skipped;
the interrupted job restarts in `attempt_002` (or the next unused attempt).

From another terminal you can also request a stop:

```bash
cd ~/Documents/SCOPE-v5-testing
../SCOPE-major-revision/FLaskAPIs/.venv-revision/bin/python \
  FLaskAPIs/run_lambda_check.py stop
```

To check the count without disturbing a running job, use `status` instead of
`stop`. Do not edit the registered study, snapshots, code or dependency versions
while resuming. A different implementation/protocol needs a separate output.
For an interrupted preparation, retain that folder and use a fresh `--output`.
If using a custom output, repeat `--output` for every command.

The old pilot launcher and its static-wire repair remain unchanged. Returning
to `~/Documents/SCOPE-major-revision` restores the original working context.

## Package the results

After the runner finishes or stops:

```bash
../SCOPE-major-revision/FLaskAPIs/.venv-revision/bin/python \
  FLaskAPIs/run_lambda_check.py package &&
open ThreeBrains/sim_results
```

Send the new `v5_lambda_check_review_*.zip`. It includes settings, model reports,
per-run and per-window outcomes, control traces, pairing checks, partial attempts,
and runner/optimizer sources. Duplicate Java libraries and Weka binaries are
excluded. Packaging checks completed receipts and refuses a concurrent writer.

## MATLAB figures

After all 27 scenarios finish, enter this in the **MATLAB Command Window**:

```matlab
cd('/Users/nancyboughannam/Documents/SCOPE-v5-testing/ThreeBrains/sim_results/v5_lambda_check/matlab')
plot_lambda_check
```

This exports PDF, PNG and FIG plots for failures, completed-task service time,
QoE, total parameter movement and adaptation phases. Error bars use independent
simulation seeds, not tasks or reporting windows. The phase summaries include
only outcome windows fully inside each phase and after warm-up; crossing windows
are excluded. They are not finalized admission cohorts.

Failure percentages use completed + failed as the denominator; pending tasks
are retained separately. Service time describes completed tasks. Total movement
and change counts include all optimizer updates, including warm-up. The
timestamped `decision_metrics.csv` supports separate post-increase/recovery
counts. Parameter movement is not measured migration cost or queue stability.

All lambda settings are retained. Compare performance and movement together;
do not rank lambdas using their differently weighted optimization objectives.
Use the calibration to choose and disclose a tradeoff, then freeze it before
running new confirmatory iterations. Do not treat these three development seeds
as a final superiority result or repeatedly tune against the final-study data.

## Developer validation commands

```bash
python -m unittest discover -s FLaskAPIs -p 'test_lambda_check.py'
python FLaskAPIs/run_lambda_check.py prepare --profile smoke --source-study /path/to/v5_deadline_pilot --output /fresh/path/lambda_smoke
python FLaskAPIs/run_lambda_check.py run --output /fresh/path/lambda_smoke
```

Smoke uses ten-minute simulations, iteration 3391, and nine jobs. It still
requires the ready v5 models; there is no model-readiness override. For a single
registered diagnostic job, use `run --job <exact-job-key>`. Other jobs remain
pending; the completion report and MATLAB guard prevent treating a partial set
as a completed calibration.
