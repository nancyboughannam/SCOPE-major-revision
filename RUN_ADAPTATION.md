# Paired adaptation diagnostic

This is a development experiment, not the final study. It tests whether
continuing to update a SCOPE configuration helps after a workload change.
The fixed control is the configuration SCOPE selected before that change;
it is not a separately tuned best-static baseline.

Stop any existing optimizer launcher with Ctrl+C first. From `FLaskAPIs`, run:

```bash
./.venv-revision/bin/python run_adaptation_check.py \
  --models revision_training_v4/xgboost_results \
  --config ../ThreeBrains/scripts/sample_app5/config/penalty_config.properties \
  --output revision_results/v4_adaptation_ite1004 \
  --iteration 1004
```

The command runs Python and Java itself. Keep the terminal open and do not
start Java or another optimizer separately. A JDK with its compiler module
must be available through `java` on PATH. The existing Python dependencies
and compatible v4 models are required; this experiment does not retrain them.

## Prespecified experiment

Both runs use SCOPE, 1200 vehicles, 60 simulated minutes, 3 minutes of warm-up,
lambda 0.05, hard aggregate change budget 0.15, and the same simulation seed.
At simulation second 1800, each application's active-period arrival rate
becomes 1.5 times its original rate. This changes arrivals, not vehicle count,
task size, deadlines, CPU capacity, or the active/idle period schedule.

* `adaptive`: apply ordinary SCOPE decisions throughout.
* `frozen`: from second 1800, return the last applied configuration. Continue
  scoring and logging requests so the same outcome windows are available.

The two runs receive exactly the same generated task list. All pre-change
optimizer requests and configurations must match. The runner checks both
conditions, complete request logging, successful configuration application,
the hard update bound, and that frozen SCOPE makes no changes after the cutoff.
An unchanged adaptive policy is a valid outcome, not a reason to alter the
workload until an improvement appears.

The optional Java workload properties are `scope.workload.shiftSeconds` and
`scope.workload.rateMultiplier`; both must be provided together. Without
them, the original arrival generator is preserved. The runner supplies them
only to its isolated Java executions. It compiles into the result directory
and never changes the IDE build or the input configuration files.

## Outputs and interpretation

The result directory contains copied input configurations, source/model/JAR
and compiled-class hashes, invocation records, separate Python/Java logs,
full diagnostic requests, and `comparison.json` / `comparison.txt`.
It also creates a sibling ZIP named `v4_adaptation_ite1004.zip`.
Always choose a new output name for another run; existing outputs are refused.

Phase summaries aggregate completed and failed outcomes within fully contained
60-second reporting windows. Warm-up-crossing and shift-crossing windows, and
the unlogged final tail, are excluded. These are not admission-cohort measures:
tasks started earlier can finish later. The per-window performance diagnostic
uses the same class weights and training normalization for measured failure
and mean deadline-normalized service; it excludes the switching term.
Report class-specific deadline misses separately, alongside failure, service,
configuration changes and total change distance. Do not interpret conditional
completed-task service time alone as overall service success.

Both modes still perform inference and diagnostic disk I/O. This experiment
cannot compare controller overhead. Preserve all outcomes and keep development
seeds separate from the final evaluation. A positive result on this one step
does not establish general adaptation or deadline guarantees.
