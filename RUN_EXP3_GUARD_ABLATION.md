# Rerun EXP3 with edge-first routing

This is a **post-confirmation routing ablation**. It disables the deadline guard
for EXP3-MC-adapted only, using the existing Java switch. It does not change Java
source, any model, EXP3's update rule, the full catalogue, reward normalization,
QoS threshold, learning rate rule, or the other policies. It is not a return to
the older five-arm experiment. Both routing variants remain available.

## Nancy's existing completed study: tonight's run

Stop any manually launched Flask or NetBeans simulations first. Use Mac Terminal.

```bash
cd ~/Documents/SCOPE-v5-testing
git fetch origin
git switch codex/exp3-routing-ablation
```

If Git reports conflicting local edits, do not reset or discard them. The run
commands below do not require moving or replacing your existing results.

Prepare and start, using the same Python environment as your completed study:

```bash
cd ~/Documents/SCOPE-v5-testing &&
../SCOPE-major-revision/FLaskAPIs/.venv-revision/bin/python \
  FLaskAPIs/run_exp3_guard_ablation.py prepare &&
caffeinate -i ../SCOPE-major-revision/FLaskAPIs/.venv-revision/bin/python \
  FLaskAPIs/run_exp3_guard_ablation.py run
```

Keep the terminal open, the Mac powered and its lid open. The runner starts and
stops EXP3's Flask service on port 5003 and supplies all Java arguments. Do not
start the services or a Java simulation yourself. SCOPE does not need to run again.

- Source, read-only: `ThreeBrains/sim_results/v5_final_3401_3410`.
- New output: `ThreeBrains/sim_results/v5_exp3_guard_off_3401_3410`.
- New simulations: **50** (600, 900, 1200, 1500, 1800 vehicles; seeds 3401–3410).
- Reused unchanged: **350** SCOPE, other baseline, static and adaptation cases.
- Models are not retrained. Lambda stays **0.01** and Rmax stays **0.15** for the
  reused SCOPE results. EXP3's QoS remains 0.20 and its catalogue is the same.

Preparation verifies all frozen source inputs and completed evidence. Any mismatch
stops the command. Do not edit the hashes to bypass an error.

Expected last line: `EXP3 guard-off: 50/50; source results remain unchanged.`
Check `completion.json`: `complete` must be true and `new_exp3_completed` must be 50.
Do not substitute smoke-profile or partly completed results into the manuscript.

## Stop and resume

Ctrl+C once stops the runner's Java and Flask children. Wait for `STOPPED safely`.
Completed receipts remain intact; an interrupted attempt is retained and a fresh
attempt is used on resume. To resume, repeat only the `caffeinate ... run` command.

From a second terminal:

```bash
cd ~/Documents/SCOPE-v5-testing
../SCOPE-major-revision/FLaskAPIs/.venv-revision/bin/python \
  FLaskAPIs/run_exp3_guard_ablation.py status
```

Use `stop` in place of `status` for a graceful stop request. No unrelated process
is killed. Do not pull code, upgrade packages or modify inputs during this run.
An interrupted preparation needs a fresh output folder; interrupted simulations
resume in the existing folder. `--output /new/path` must be repeated at every stage.
`--source-study /path/to/completed/study` supports a different source location.

## MATLAB figures, after completion

Run this in the **MATLAB Command Window**, not Mac Terminal:

```matlab
cd('/Users/nancyboughannam/Documents/SCOPE-v5-testing/ThreeBrains/sim_results/v5_exp3_guard_off_3401_3410/matlab')
plot_scope_paper_results
```

The original 11 x 11 cm style, fonts, colours and markers are retained. Figures
are separated into `main`, `static_control`, `ablations`, `adaptation`,
`exp3_routing_ablation` and `supplementary`. See `FLaskAPIs/paper_matlab/FIGURE_GUIDE.md`.
Calibrated static is a reviewer-requested control; keep it in a separate panel.
The script exports PDF, PNG and editable FIG; it requires Times New Roman.

## Send the new evidence

After the run (and optional MATLAB plotting), use Mac Terminal:

```bash
cd ~/Documents/SCOPE-v5-testing &&
../SCOPE-major-revision/FLaskAPIs/.venv-revision/bin/python \
  FLaskAPIs/run_exp3_guard_ablation.py package &&
open ThreeBrains/sim_results
```

Send `v5_exp3_guard_off_3401_3410_review_*.zip`. It includes new raw logs, old
receipt provenance, the combined tables, paired guard-on/off comparisons and
figures if generated. The original complete study must also be retained; this
review ZIP omits duplicate runtime binaries and does not replace that archive.

## Interpretation

Only the EXP3 main observations are replaced in the combined tables. All other
observations are byte-for-byte-equivalent parsed metrics from their original
receipts. The complete main Holm family is recalculated, retaining RANDOM and
static even when those curves are moved to the supplement. Separate paired
guard-effect tests use all ten seeds and both primary outcomes at every load.

Disclose that SCOPE uses its proposed deadline guard and the main EXP3 variant
uses edge-first routing. Keep the guard-on EXP3 comparison in the supplement or
rebuttal. Do not choose which variant to disclose based on which favors SCOPE.
These reused evaluation seeds do not constitute a new independent confirmation.
Low service time describes completed tasks and must be considered with failures.

No result is promised: this change isolates routing and does not establish that
SCOPE adapts better than calibrated static. The matched frozen comparison remains
the evidence for adaptation. Parameter movement is not a migration-cost measure.
