# Figure selection for the manuscript

The main folder contains failures and completed-task service time for SCOPE,
AI-based, EXP3-MC-adapted and RAIDER/TRAX, in the original MATLAB style:
11 x 11 cm panels, Times New Roman, original policy colours/markers and line widths.
Each point is the mean of ten seeds with a pointwise 95% Student-t interval.
No smoothing, outcome filtering or interval clipping is applied.

Keep the aggregate failure and service plots together when interpreting results:
service time includes completed tasks only. Per-application panels are available.

- `static_control`: SCOPE versus independently calibrated static at every load.
  Reviewer 2 comment 4 requests this control. Similar results are informative;
  they do not justify deleting the control. This can be a separate compact pair
  of panels rather than another curve beside external baselines.
- `ablations`: hard bound only, soft penalty only, performance only, full SCOPE
  and calibrated static, at 1800 vehicles. Failure, service and normalized
  parameter movement expose the performance/stability trade-off. Movement is
  not measured migration overhead. There is no ablation load sweep to plot.
- `adaptation`: SCOPE, frozen SCOPE and static before/during/after the load shift.
  Phase means do not establish time-to-recovery or a significant adaptation benefit.
- `exp3_routing_ablation`: guard off versus guard on with identical seeds and
  catalogue. Keep this comparison in the supplement or rebuttal, even if only
  guard-off EXP3 appears in the main figure. This is post-confirmation analysis.
- `supplementary`: all original comparators, including RANDOM, and secondary metrics.

Do not put every exported figure into the manuscript. Main failures/service,
a compact control/ablation figure, and (if retaining an adaptation claim) the
matched adaptation comparison have distinct purposes. Extra per-application,
QoE, network/utilization and EXP3 routing figures may go in the supplement.

For the guard-off rerun, disclose: EXP3 uses edge-first routing; SCOPE uses its
proposed deadline guard. The full 1409-arm catalogue, training-derived reward
normalization, QoS 0.20 and learning rule are fixed. This is not the original
unmodified EXP3-MC paper algorithm, and it is not the old five-arm experiment.
The main Holm family is recalculated after replacing EXP3 observations; static,
RANDOM and all originally registered comparisons remain in that family.
