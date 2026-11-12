# EXP3 routing-ablation validation

Validated on Linux with Java 21 and the recorded v5 Python package versions.

- 32 existing/new unit tests passed: confirmatory statistics/protocol, EXP3
  feedback and the routing-ablation boundary.
- A completed 22-case smoke study was verified and copied as the source.
- Two real ten-minute EXP3 simulations (900 and 1800 vehicles, seed 3491)
  completed with `scope.deadlineTierGuard=false` and `edge_first_v1` service health.
- All 20 other smoke scenarios were reused; their parsed metric rows are identical.
- Frozen Java source, compiled classes, JARs and both optimizer service sources
  were byte-identical to the source study. SCOPE's model manifest was unchanged.
- SIGINT returned 130, cleaned up the owned service, and retained the partial
  attempt. Resume completed the interrupted case in a new attempt.
- Repeating the completed run created no additional attempts or simulations.
- Original source protocol and all 22 original completion receipts were unchanged.
- Full-plan tests require exactly 50 new EXP3 cases and preserve all 400 study
  cases/comparisons, including calibrated static and RANDOM.
- MATLAB code preserves the previous paper-plot style and adds separate paired
  guard-on/off plots. MATLAB is unavailable in the validation environment, so its
  rendering has not been executed here.

These are implementation checks, not final scientific results. Nancy's full
50-case rerun has not been executed here. Both EXP3 variants must be disclosed;
the rerun uses already observed evaluation seeds and is post-confirmation analysis.
