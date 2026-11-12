# Protocol and interpretation

This document describes the frozen v5 code and the subsequent isolated EXP3
routing ablation. Code provenance is in `SOURCE_PROVENANCE.json`; exact published
file hashes are in `FILES.sha256.json`. Future result archives must identify the
actual commit, `study.json`, model manifest and package versions used.

## Separation of data and decisions

- Development collection: iterations 3001–3010 at 600, 900, 1200, 1500, 1800 vehicles.
- The data preparation splits complete runs with seed 42. The recorded full v5
  split used train 3002/3003/3004/3005/3009/3010, validation 3001/3008 and held-out
  predictor test 3006/3007. Inspect the generated split manifest, not row-wise guesses.
- Static: four distinct configurations per load, including the initial configuration,
  shortlisted using training outcomes, then chosen on calibration iterations 3201/3202.
  It is a calibrated control with a finite tuning budget, not a globally optimal static.
- Lambda development: `run_lambda_check.py` compares 0, 0.01 and 0.05 using
  3301–3303. The final runner freezes 0.01; Rmax remains 0.15. The old 0.20 choice
  belongs to an earlier system and is not the setting executed in the v5 final study.
- Confirmation: 3401–3410, disjoint from these development iterations.
- EXP3 guard-off analysis reuses these confirmation seeds after their outcomes
  were observed. Report it as a post-confirmation routing ablation, not fresh
  independent confirmation or evidence of pre-registration before observation.

The optional lambda workflow can be reproduced after collection/training:
`FLaskAPIs/run_lambda_check.py prepare`, then `FLaskAPIs/run_lambda_check.py run`.
Invoke those through the same Python environment from the repository root. It does not select a new
lambda automatically or alter the confirmation runner.

## Policies and information access

SCOPE uses per-application XGBoost predictions over a training-derived configuration
catalogue; the observed performance targets define its normalization. The step
constraint and soft penalty act on normalized distances in the seven configuration
parameters. They are not proofs of queue stability, migration overhead or deadlines.

The deadline routing guard can redirect a task when an edge processing lower bound
exceeds its deadline and a cloud route is estimated feasible. It uses current
task/network information, not realized future outcomes. The routing/schema checks
prevent guard-on SCOPE models from silently receiving edge-first requests.

EXP3-MC-adapted learns from finalized admission-cohort feedback, with a reactive
QoS trigger. It uses the same training-derived normalization and full configuration
catalogue, but no XGBoost predictions. Thus equal catalogue membership does not mean
equal prior information. The original full v5 catalogue contains 1409 arms including
the initial configuration. Verify the actual count in each service's health/logs.
The automatic learning rule is `eta = 0.1 * min(1, 5/K)`; QoS is 0.20. Removing the
five-arm subset does not prove insensitivity to arm count.

The guard-off runner uses a normalization-only manifest declaring `edge_first_v1`.
Its numeric support is copied unchanged from the guard-on training manifest, whose
hash is recorded. This separates EXP3's reward normalization from SCOPE's predictor
schema. No XGBoost model is relabelled or used under the wrong routing schema.

AI-based, RAIDER/TRAX and RANDOM keep their existing implementations. Their source
and the six AI Weka model files are unchanged by this release. The existing
AI-based implementation does not gain SCOPE's deadline guard. Both EXP3 routing
variants are retained to reveal the effect of this shared routing component.

## Controls and plots

Calibrated static is required to test whether online reconfiguration improves on
a suitably chosen fixed configuration (Reviewer 2 comment 4). It must not be
removed because it matches or outperforms SCOPE. Main figures can show external
baselines; static and component ablations can occupy separate compact panels.

Hard-only removes lambda; soft-only removes the hard step bound; performance-only
removes both. These extra cases exist at 1800 vehicles only. The SCOPE and static
controls at that load reuse the same main observations without increasing sample size.

The adaptation case multiplies arrivals by 1.5 at 1200 seconds and restores them at
2400. Frozen SCOPE follows SCOPE until the increase, then holds the configuration in
force before the first later update. Pre-intervention histories and task hashes
must match. Phase means use outcome windows fully inside each phase after warm-up;
they do not measure response-time-to-recovery. A nonsignificant paired adaptation
contrast cannot support a claim that adapting outperforms remaining fixed.

## Statistics and evidence

Failures use completed + failed as denominator; pending tasks remain separate.
Service time describes completed tasks only. Report both metrics together.
Ten simulation seeds are the independent replicates; tasks and windows are not.
Curves show mean and pointwise 95% Student-t intervals. Paired differences use the
same seeds. Holm correction covers 50 main tests, six SCOPE-ablation tests and two
matched adaptation tests as separate families. Moving a curve to the supplement
does not remove its test from the original family.

After EXP3's rerun, the combined main family is recalculated. The additional
guard-effect family contains ten tests (five loads, two aggregate metrics).
Secondary outcomes and per-application guard effects are descriptive. Do not claim
an adaptation benefit, overhead advantage, noise robustness or external-validity
result that these experiments do not measure. Complete every registered case and
retain unfavorable results.
