# EXP3_MC feedback audit — diagnostic package v1

## Install and verify first

Copy the entire `exp3_feedback_audit` folder from the package's `FLaskAPIs`
folder into:

`~/Documents/SCOPE-major-revision/FLaskAPIs/`

This adds three Python files. It does not replace `exp3_mc_service.py`,
`ml_optimizer_service.py`, `run_shared.py`, Java files, or past results.
If the destination already exists, stop and compare it instead of overwriting.

Stop the existing EXP3 service before launching another service on port 5003.
From Terminal:

```bash
cd ~/Documents/SCOPE-major-revision/FLaskAPIs
./.venv-revision/bin/python exp3_feedback_audit/test_audit.py
```

Expected: 13 tests, OK. These use synthetic data in temporary folders; they do
not run EdgeCloudSim or change any experiment output.

Verify the preserved full catalogue without starting a server:

```bash
./.venv-revision/bin/python exp3_feedback_audit/run_audit.py --catalogue-experiment revision_results/shared_full_ablation01 --output revision_results/exp3_full_fixed_audit01 --mode fixed --check-only
```

Expected: 2537 shared arms, original order, fixed, effective eta=0.1.
If the source experiment is not found or its checksum/order differs, stop and
share the error. Do not rebuild or silently substitute a different catalogue.

## Why a separate implementation?

The original script remains the historical reference. The new service corrects
feedback bookkeeping and records the distinction explicitly:

| Previous action was | Denominator for its observed feedback |
|---|---|
| Fixed initial configuration | 1 |
| Randomly sampled arm | Probability used for that specific draw |
| Deterministically retained arm after no trigger | 1 |
| Randomly sampled arm happened to equal current arm | Its draw probability, NOT 1 |
| Java reports an unexpected arm | Reject with an error; do not silently attribute feedback |

The update remains score += effective_eta * reward / recorded_probability.
An initial observation is credited once at weight 1 rather than multiplied by K.
Retained-action windows provide no observations of other arms; do NOT claim
full-vector unbiasedness or an adversarial regret guarantee for this reactive
adaptation. This is a declared adapted algorithm, not a verified reproduction
of the original authors' implementation.

The normalization, reward, QoS trigger, candidate selection, response format,
port 5003 and Java policy name EXP3_MC are unchanged. No exploration mixture is
added. Fixed eta can still cause concentration after a genuinely random draw.
The new fields expose that behavior instead of hiding it.

## Two explicitly named modes

1. `fixed`: effective_eta = eta_reference (default 0.1).
2. `scaled_k5`: effective_eta = eta_reference * 5 / actual_number_of_arms.

The scaling mode is a diagnostic sensitivity rule, not a formula taken from the
paper and not a guaranteed optimal learning rate. It preserves the K=5 reference
scale. For reference eta=0.1:

| K | Fixed eta | Scaled eta |
|---:|---:|---:|
| 5 | 0.1 | 0.1 |
| 25 | 0.1 | 0.02 |
| 100 | 0.1 | 0.005 |
| 2537 | 0.1 | approximately 0.000197083 |

The runner explicitly sets eta and mode; the old shared launcher would override
eta and load the old service, so do not use run_shared.py for these new modes.
Each new output folder records the mode, reference/effective eta, source hashes,
health information and a copy of the exact catalogue. Existing output folders
are refused. `--check-only` creates no results.

## Next two diagnostic simulations, after the tests pass

Run ONLY EXP3_MC. Do not repeat SCOPE or its ablations.
Make a COPY of ThreeBrains/scripts/sample_app5/config/shared_catalogue_pilot.properties
named `exp3_feedback_audit.properties`, and set these existing properties:

```properties
simulation_time=60
warm_up_period=3
min_number_of_mobile_devices=1800
max_number_of_mobile_devices=1800
mobile_device_counter_size=100
orchestrator_policies=EXP3_MC
```

Leave all other simulation settings unchanged. Both initial checks use iteration
1 / seed 20260829 solely as diagnostics. They are NOT held-out final evaluation.

### Diagnostic A: corrected bookkeeping, fixed eta

```bash
cd ~/Documents/SCOPE-major-revision/FLaskAPIs
./.venv-revision/bin/python exp3_feedback_audit/run_audit.py --catalogue-experiment revision_results/shared_full_ablation01 --output revision_results/exp3_full_fixed_audit01 --mode fixed
```

Leave this terminal running. SCOPE's Python service is unnecessary for an
EXP3-only run. In NetBeans use the usual main class
`edu.boun.edgecloudsim.applications.sample_app5.VehicularMainApp`.
Working directory: `/Users/nancyboughannam/Documents/SCOPE-major-revision`.
Arguments (one line):

```text
ThreeBrains/scripts/sample_app5/config/exp3_feedback_audit.properties ThreeBrains/scripts/sample_app5/config/edge_devices.xml ThreeBrains/scripts/sample_app5/config/applications.xml ThreeBrains/revision_results/exp3_full_fixed_audit01/ite1 1
```

Wait for BUILD SUCCESSFUL, save/copy the Output text, then stop the Python service
with Ctrl+C. Capture any optimizer error even if Java reports BUILD SUCCESSFUL;
Java may continue after an HTTP error. Do not interpret that as a valid run.

### Diagnostic B: corrected bookkeeping, scaled eta

```bash
./.venv-revision/bin/python exp3_feedback_audit/run_audit.py --catalogue-experiment revision_results/shared_full_ablation01 --output revision_results/exp3_full_scaled_audit01 --mode scaled_k5
```

NetBeans arguments (same seed/configuration, different output directory):

```text
ThreeBrains/scripts/sample_app5/config/exp3_feedback_audit.properties ThreeBrains/scripts/sample_app5/config/edge_devices.xml ThreeBrains/scripts/sample_app5/config/applications.xml ThreeBrains/revision_results/exp3_full_scaled_audit01/ite1 1
```

Save the Output text again. Upload Python and Java result folders for both modes.
Do not choose a final learning rate from whichever wins this single diagnostic.

## What to inspect in new logs

- First feedback_origin=initial_fixed and feedback_probability=1.
- Later sampled feedback_probability equals the preceding row's
  next_behavior_probability. For retained feedback it equals 1.
- mode, eta_reference and eta identify the variant without relying on a folder name.
- max_selection_probability, selection_entropy and effective_arm_count diagnose
  concentration (effective_arm_count here is exp(entropy), not catalogue size).
- Reward, score_increment, selected arm, triggering, switching and churn remain logged.
- Compare realized Java failures/service time, not predictions alone.
- Equal catalogue membership does not equalize information: SCOPE has pretrained
  predictors whereas this baseline receives only observed-arm feedback.
- 59 windows cannot explore 2537 arms comprehensively. Report that limitation.

## Separate tuning plan (after the two diagnostics are reviewed)

Predeclare a small grid: reference eta in {0.05, 0.1, 0.2}, mode in
{fixed, scaled_k5}; QoS threshold remains 0.20 for this isolated study.
Use separate development runs, for example iterations 1001–1003 if unused
(verify the printed SIMULATION_SEED; the inspected Java convention is
20260828 + iteration). Use loads 900 and 1800, the same catalogue and paired
seeds for each setting. Record the same tuning budget for every K being studied.

Choose based on a predeclared realized performance objective matching the
failure/deadline-normalized service cost, using the SAME normalization and
application weights; raw service time alone is not that objective. Retain both
component metrics and churn. Inspect whether the existing statistics scripts
already calculate that objective before adding a new aggregator.

Freeze settings before the final 100–1800 sweep. Reserve evaluation seeds not
used to select parameters, report uncertainty, and document that the original
eta=0.1 reference and the revised adaptation are different experiments.
Neither the grid nor scaled_k5 is an assertion that the baseline must beat SCOPE.

## Provenance of the completed full-catalogue diagnostic

Received Python archive: shared_full_ablation01.zip
SHA256: 9b1045efd39485a814a5f15c98a64f90eee53f81d55edddc7cfcea91bb89a918
Received Java archive: shared_k25_ablation01(2).zip
SHA256: 3854e4c521fce227b33bd03321a10d949b12fa5e8b1d2ceef8d2ca9f772f30f5
Catalogue SHA256: 39ee000d61f300aaad81e7c24c4cc17a83687133e3ef877736a9f5ab55fb0ff3

The Java archive's internal directory retains the old k25 name. The supplied
console run (06 November 2026, 08:52:53–08:55:31) matches all four Java result
counts, service times and finish times. Python log timestamps and behavior align.
This is strong evidence of the matching full-catalogue experiment. The console
excerpt does not print the literal output path; do not claim that pathname was
independently confirmed. Preserve the original archive and record the naming
mistake instead of overwriting it. No repeat is necessary solely for its name.

Original EXP3 source SHA256, verified against the run manifest:
f803275240b44f24d5338d02d800706d5e297ce3211fafe71e34431bd1f071ed

## Validation and limitations

13 synthetic unit/integration tests pass locally: startup, saved probabilities,
retention, random same-arm draws, unexpected application, state reset/isolation,
actual-K scaling, configuration validation, Flask API/logging, negative fixed-eta
control, scaled example and runner checksum/reuse checks.
No new EdgeCloudSim experiment has been executed by the assistant. Local tests
verify implementation behavior, not comparative performance or paper fidelity.

Paper audited: Donassolo et al., Online Reconfiguration of IoT Applications in
the Fog: The Information-Coordination Trade-Off, TPDS 33(5), 2022.
https://polaris.imag.fr/panayotis.mertikopoulos/files/FogIoT.pdf
DOI: 10.1109/TPDS.2021.3097281

The paper supports a five-host experiment, eta=.1, softmax importance updates,
and a reactive trigger. The deterministic initialization/retention semantics
here are our explicit adaptation; full fidelity to author code is not verified.
