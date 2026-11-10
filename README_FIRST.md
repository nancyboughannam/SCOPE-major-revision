# Edge VM selection correction — diagnostic release

## Install
Back up your current VehicularEdgeOrchestrator.java before replacing it. Copy the
ThreeBrains and FLaskAPIs contents into the corresponding project directories.
This package is based on the EXP3 revision replacement orchestrator already installed
in this conversation. It preserves admission-cohort feedback. Exp3FeedbackTracker.java
from that earlier revision must remain installed. If you made additional local Java
changes, merge the included diff instead of blindly replacing your file.

Runtime files:
- REPLACE ThreeBrains/src/edu/boun/edgecloudsim/applications/sample_app5/VehicularEdgeOrchestrator.java
- ADD ThreeBrains/src/edu/boun/edgecloudsim/applications/sample_app5/EdgeVmSelector.java

Test files:
- ADD FLaskAPIs/EdgeVmSelectorTest.java
- ADD FLaskAPIs/test_edge_vm_fix.py

No Python service or XML file is replaced. NetBeans must rebuild the Java sources.

## Behavior
All hosts and all edge VMs are eligible for the common SCOPE, EXP3, RAIDER_TRAX and
SCOPE-ablation/training fast path. The existing weighted load/distance score and
0.1 random scoring term remain. Cloud fallback alpha is unchanged.

A task remembers the edge VM chosen at routing. At VM assignment after WLAN upload,
the saved VM is retained if its current load is below the CURRENT task-class
threshold; otherwise all VMs are searched again with that threshold. If none is
eligible, null is returned and the existing device manager records a capacity
rejection. There is no unconditional first-VM fallback. Plans are removed on
assignment, failure or completion. This is not a reservation: later load changes
and other tasks can still cause the simulator's final capacity check to reject work.

The inventory is captured lazily at the first task, after CloudSim VM allocation.
This assumes the existing static infrastructure (no online VM creation/destruction).
AI_BASED and other existing selectors are unchanged.

## Test first
From FLaskAPIs on your Mac:

```bash
export JAVA_HOME=$(/usr/libexec/java_home -v 21)
export PATH="$JAVA_HOME/bin:$PATH"
python test_edge_vm_fix.py
```

The test compiles the Java code, runs seven selector assertions, and runs two
isolated six-minute RAIDER_TRAX simulations (100 and 1800 devices). This exercises
the shared selector without requiring Flask. It uses your existing XML files and
models; copies the properties into a fresh diagnostic folder; leaves your normal
configuration files untouched. It checks the XML inventory count and confirms
non-first VMs are selected. Results are written under:
ThreeBrains/revision_results/edge_vm_smoke_<timestamp>/

## SCOPE/EXP3/AI diagnostic next
Use fresh Java and Flask result directories such as edge_vm_diagnostic_01, keeping
all files from earlier experiments separate. Start SCOPE and EXP3 services as before
(full catalogue, QoS .20; SCOPE lambda .20, Rmax .15). In a COPY of your current
properties file beside the original (so config/weka resolves), use:

```
orchestrator_policies=RT_OPT_ML,EXP3_MC,AI_BASED
```

Keep the same physical configuration, workload and paired iteration seed. Rebuild
and run iteration 1 before a multi-iteration production batch. The existing
run_exp3_smoke.py --arms 0 also remains useful for the EXP3 feedback integration check.
It requires port 5003 to be free because it launches its own service.

Graph inputs remain SIMRESULT_*.log in the Java output directory. Added selector
CSV files appear beside them:
EDGE_VM_SELECTION_<policy>_<N>DEVICES.csv
Columns identify VM, host, index on host, and assignment selections (not completed
tasks). Index 1 means the second VM on a host. Rows include zero-use VMs. These
counters cover the whole simulation including warm-up, so do not directly divide
them by warm-up-filtered MATLAB task totals. Existing MATLAB scripts should keep
matching SIMRESULT filenames, not generic CSV wildcards.

Console EDGE_VM_SELECTION gives plans, retained, reselected, no_eligible_at_assignment,
distinct_vms_selected, selectable_vms. Pending tasks may explain why plans exceeds
the sum of assignment outcomes. Upload failures can also prevent assignment.
Flask decision CSV paths are still controlled by their environment variables.

## Validation and interpretation
Local Java 21 compile passed; seven selector checks passed. Two six-minute simulator
checks selected all 80 configured VMs, including all 40 second VMs. See validation/.
At 1800 devices the shared RAIDER_TRAX fast path reported 25,487 no-eligible-at-assignment
rejections. This is a diagnostic finding, not a claim of SCOPE performance or proof
that the patch improves failures. Enforcing eligibility after upload can reject
work the old implementation assigned despite its configured threshold.

Do not claim final performance using the old SCOPE predictors without checking their
accuracy under the changed fast path. Training data must be regenerated and models
retrained if the changed execution semantics make existing predictions unreliable;
for final results, train and validate on the corrected implementation. EXP3 learns
online but its tuning and final results must also be rerun. Keep this correction
separate from subsequent policy changes and never tune using final test seeds.

Potential next improvements to evaluate after these logs: admission-aware selection,
network-aware cloud fallback, and validation-set tuning of lambda/Rmax. These are
not implemented here and cannot be promised to match AI_BASED.
