# Deadline-pilot validation — 12 November 2026

These checks establish implementation behavior and workflow safety, not research
superiority. Validation used Linux, JDK 21 and Python 3.12. The launcher also
selects the user's macOS JDK 21 path and uses their existing Python environment;
the complete macOS workflow and MATLAB rendering still need local execution.

- Java compiled successfully with the isolated runtime build.
- 20 deadline/VM-capacity checks and 10 workload-step/recovery checks passed.
- 14 Python workflow/schema tests passed, including process termination,
  existing-port protection, immutable completion receipts, preserved partial
  attempts, protocol-edit rejection, EXP3 manifest loading, routing mismatches,
  and progress-prefixed performance-window parsing.
- Six existing objective tests and 17 existing EXP3 revision tests passed.
- Both SCOPE and EXP3 HTTP endpoints rejected routing/model mismatches in both
  directions before request parsing/scoring, using actual legacy and freshly
  trained smoke manifests.
- A native legacy-SCOPE comparison with the routing flag off matched 52 numeric
  metrics across all four application reports exactly. An AI_BASED comparison
  with the guard flag and reporting enabled likewise matched 52 metrics. Only
  measured wall-clock overhead was excluded from these equivalence checks.
- The short end-to-end workflow completed 30 scenarios: ten collection, eight
  static calibration, eight policy comparisons and four burst/recovery runs.
  It produced 32 completed jobs including training and static selection, 120
  application metric rows, and 450 parsed application-window rows. Paired
  policy comparisons and static calibration used matching workload fingerprints.
- A live collection run was stopped through the stop command. The Java process
  exited with the runner returning 130; completed receipts were unchanged and
  the interrupted scenario resumed in attempt_002.
- A live SCOPE run was interrupted with SIGINT (Ctrl+C). Its Java and Flask
  processes exited, port 5002 stopped listening, and 20 completed jobs remained
  unchanged. Resume completed the workflow in a new attempt. Repeating a fully
  completed workflow skipped every scenario and regenerated only summaries.
- The deliberately tiny smoke-training dataset failed the prediction-readiness
  criteria. The normal pilot command correctly refused to proceed. An explicit,
  recorded diagnostic override was used to exercise the remaining smoke stages.
  No smoke model or performance result is presented as a validated research model.
- All SCOPE optimizer decisions checked in the smoke runs respected Rmax 0.15.
  Static controls made no optimizer calls. Exported ZIP integrity passed.
- The MATLAB t-interval formula was checked against SciPy for n=2,3,10; figures
  have not been rendered in MATLAB here.

The runner's progress-window parser was additionally checked against every raw
window in the completed native runs. SimLogger can place progress dots/numbers
before a reporting message; those prefixes must not cause rows to be discarded.

The full 60-minute development profile, its newly collected model quality, and
the scientific comparison are intentionally left to the user's local test run.

## Static-wire repair validation — 12 November 2026

The first full-profile local run exposed a static-configuration serialization
bug: the complement of `0.9` was sent as `0.09999999999999998`. The Java bounds
check rejected it before the simulation started. The repaired launcher clamps
the redundant complement to the already validated weight range. No Java,
routing, model, candidate-selection or experimental-protocol change is included.

- Reproduced the exact Java exception using the failed configuration and the
  supplied frozen Java runtime. With only the corrected serialization, the same
  60-minute, 900-vehicle, iteration-3201 static scenario completed successfully
  and yielded all 177 application reporting windows. This is a bug reproduction
  and repair check, not evidence of adaptive-policy superiority.
- The actual Java reply parser accepted 649 generated configurations covering
  weight/alpha/threshold boundaries and the failing candidate, with exactly
  unchanged alpha, load weights and thresholds. Genuinely invalid candidates,
  including floats immediately outside the weight bounds, remain rejected.
- The original 14 workflow/schema tests and 11 new interoperability/repair tests
  passed. Repair tests cover preserved evidence, a new retry attempt, idempotence,
  interruption before the atomic audit record, changed input/result/shortlist
  rejection, unknown runner rejection, and rejection of later runner changes.
- Verified all 159 frozen-input hashes and 835 files in the 55 completed-job
  receipts from the supplied full-profile archive. The recorded model readiness
  is `READY_FOR_OPTIMIZER_INTEGRATION_TEST`; no quality-gate override is needed.
- Replayed registration on a separate copy of that archive: all 1,065 original
  extracted regular files remained byte-identical. The 50 collection jobs,
  training job and four completed calibration jobs were skipped; the failed
  calibration received a new `attempt_002` directory. The original study and
  checksum remain unchanged; a separate audited runner repair permits resume.

The remaining calibration, pilot comparisons and adaptation scenarios still
need to finish on the user's Mac. Their outcomes have not been inferred from
the collection metrics or the successful serialization repair.
