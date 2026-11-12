# Confirmatory launcher validation — 12 November 2026

Validation used Linux, JDK 21, the recorded Python package versions and the
verified ready v5 model/Java snapshot. No model-readiness override was used.
No confirmation iterations 3401–3410 were run during this validation.

- Eleven focused tests passed. They cover the fixed 400-scenario design, all
  retained baselines and factorial ablations, separate calibration/test seeds,
  inherited environment cleanup, static-wire identity, incorrect receipt
  rejection, seed-based t intervals, paired zero/single-seed behavior, Holm
  family sizes and boundary-safe phase aggregation.
- The ten-minute smoke workflow completed eight static calibration scenarios
  and all 22 evaluation scenarios, exercising every main, ablation and
  adaptation policy. It used the real ready models and original frozen Java
  classes. SCOPE, EXP3, AI_BASED, RAIDER_TRAX, RANDOM and the static controller
  completed successfully. All paired workload fingerprints matched.
- The matched frozen run passed exact pre-intervention request/window checks.
  All SCOPE, hard-only and frozen decisions respected Rmax=0.15. Dynamic
  configuration responses were checked against subsequent observed state;
  EXP3's logged movement was checked against its selected configurations.
- The stop command interrupted a live smoke scenario with exit code 130.
  A subsequent SIGINT test observed active owned Java and Flask children; both
  exited, port 5002 was released and all 29 earlier receipts remained unchanged.
  Resume completed the interrupted scenario in attempt_003 and finished the
  study. Partial attempts remain separate and are excluded from summaries.
- A concurrent runner was rejected by the output lock. Repeating the completed
  study started no jobs and preserved all 31 receipts (eight calibration, one
  static selection and 22 evaluations) and all attempt directories.
- Full-profile preparation registered exactly 400 evaluation jobs, all five
  vehicle counts and ten fresh iterations. It imported and revalidated four
  compatible completed calibration cases from the available source checkpoint.
  The remaining cases are scheduled, not silently assumed complete. All 159
  original source-input checksums remained intact; no full evaluation started.
- Exports contained 88 application metric rows, complete seed-level means and
  one verified frozen pair for the smoke profile. Main SCOPE/static results
  were reused in the ablation view without increasing the replicate count.
  Movement is missing/not applicable for task-level baselines rather than zero.
- The review ZIP passed CRC/integrity checks and contained the raw evidence,
  CSV summaries, pairing checks, source snapshots and MATLAB plotting script.
  Large duplicate Java/Weka runtime files were excluded as documented.
- Python syntax and whitespace checks passed. The MATLAB script uses the
  exported seed-level statistics and refuses incomplete study/cell counts.
  MATLAB rendering has not been executed in this environment.

These checks establish execution behavior, evidence preservation and report
construction. The short-run values are not final research results. Complete the
registered ten-seed study on the user's Mac before drawing scientific conclusions.
The controller and Java algorithms are unchanged by these new launcher/report
files; earlier model, routing and static-wire validation is documented separately.
