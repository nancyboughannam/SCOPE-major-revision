# Lambda-check implementation validation

Validation uses Linux, JDK 21 and the same recorded Python package versions as
the source training run. Java classes, optimizer source, candidate catalogue and
all six ready XGBoost models are copied from the verified frozen v5 source. No
model-readiness override, retraining, routing change or simulator patch is used.

- 38 Python tests passed: 13 new control/protocol tests plus the existing 25
  deadline-pilot and static-wire repair checks.
- The nine-scenario ten-minute smoke workflow completed with three verified
  adaptive/frozen pairs. Workload fingerprints match across every lambda; each
  pair has identical requests, decisions and reported outcomes before freezing.
- A live smoke run was stopped using the stop command after six completed jobs.
  Resume preserved all six receipt hashes and used a new attempt for the partial
  job before finishing all nine scenarios.
- SIGINT during a full-duration run returned exit code 130, terminated both owned
  Java and Flask processes, released port 5002, and retained the incomplete attempt
  without a completion receipt. Resume restarted in `attempt_002`.
- A concurrent second runner was rejected by the output lock.
- The complete 60-minute calibration finished all 27 scenarios on iterations
  3301, 3302 and 3303, with nine verified adaptive/frozen pairs. All 1,593
  optimizer decisions respected the 0.15 movement limit. Every pair matched
  requests and reporting windows through its first intervention at 1210 seconds.
- Repeating the completed calibration skipped all 27 jobs: completion receipts
  and attempt directories stayed unchanged. All 159 original frozen source files
  and 188 copied experiment input files passed their checksum verification.
- The old pilot runner, its static-wire repair, optimizer and Java orchestrator
  remain byte-identical to the previously published branch version.

Every simulation checks the actual returned actions, their application by Java,
the hard movement bound, the frozen-control cutoff and the recorded lambda.
Before a frozen comparison is accepted, its pre-intervention request history and
reporting windows must exactly match its adaptive partner. Outcome phase metrics
exclude warm-up and crossing windows; uncertainty is across seeds, not windows.

MATLAB plotting code is supplied for local rendering. MATLAB has not been run
in this environment. Diagnostic logging and frozen counterfactual scoring mean
these runs are not suitable for claiming production runtime overhead.
