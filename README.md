# SCOPE — reproducible simulation study

SCOPE selects seven configuration parameters using learned performance predictors,
a soft penalty on parameter movement, and a hard bound on each configuration step.
The simulator is the modified EdgeCloudSim vehicular application in `ThreeBrains/`.
Python services communicate with Java over localhost HTTP. MATLAB generates figures.

This branch is the **clean publication candidate**. It contains the same Java,
optimizer services and training code as the v5 study, plus the isolated EXP3 routing
ablation. It does not certify a performance ranking or that every reviewer comment
has been resolved. Final outcome tables must be archived after the rerun is checked.

## Existing completed v5 study

To rerun only EXP3 with its deadline guard disabled, follow
[RUN_EXP3_GUARD_ABLATION.md](RUN_EXP3_GUARD_ABLATION.md).
That adds 50 simulations and reuses the 350 unaffected observations with provenance.
Do not change a running checkout to this cleanup branch. Use a separate checkout.

## Reproduce from a fresh checkout

Supported workflow: macOS or Linux, Python 3.11/3.12, JDK 21+, and MATLAB R2020a+
for figure export. Java and Python run headlessly; NetBeans is not required.
The runners use POSIX process groups and file locks; native Windows is not supported.

```bash
python3.11 -m venv .venv
.venv/bin/python -m pip install -r FLaskAPIs/requirements.txt
java -version
.venv/bin/python -c "import flask,numpy,pandas,xgboost,sklearn,scipy,matplotlib; print('Dependencies OK')"
```

Use a JDK, not a Java runtime alone. The launcher checks for a compiler. If needed,
pass `--java /absolute/path/to/bin/java` during preparation. Keep the same Python
environment, inputs and source code through all stages; resume checks reject changes.

Run these stages **in order from the repository root**. Each command must succeed
before starting the next. The first three regenerate the training observations and
models. Existing models/results in other directories are not overwritten.

```bash
.venv/bin/python FLaskAPIs/run_deadline_pilot.py prepare
.venv/bin/python FLaskAPIs/run_deadline_pilot.py collect
.venv/bin/python FLaskAPIs/run_deadline_pilot.py train
.venv/bin/python FLaskAPIs/run_confirmatory_study.py prepare
.venv/bin/python FLaskAPIs/run_confirmatory_study.py run
.venv/bin/python FLaskAPIs/run_exp3_guard_ablation.py prepare
.venv/bin/python FLaskAPIs/run_exp3_guard_ablation.py run
```

The first prepare uses the full collection profile named `pilot`: 10 development
iterations at five loads. `--profile smoke` is only a workflow test, never final data.
The confirmatory preparation requires the models to pass their recorded readiness
checks. Do not use a diagnostic override for publication data. Static calibration
is performed automatically on separate seeds before confirmation begins.

The runners start/stop Flask as needed and provide all Java arguments. Leave ports
5002 and 5003 free and do not launch services manually. On a Mac, `caffeinate -i`
may prefix a long-running Python command. Keep the Mac powered with its lid open.
Ctrl+C terminates only the runner's own children; repeat the interrupted stage to
resume. Completed attempts are checked and skipped. Preserve partial attempts.

The dependency versions are pinned to the recorded v5 environment. Rebuilding on
another platform is a replication, not a promise of byte-identical trained models
or wall-clock timings. Every run records its inputs, versions, model hashes and logs.
The supplied AI-based Weka models are kept unchanged; SCOPE models are generated
from the training workflow rather than confused with the obsolete models in history.

## What is run

| Study component | Loads | Policies | Evaluation cases |
|---|---|---|---:|
| Main | 600, 900, 1200, 1500, 1800 | SCOPE, AI-based, EXP3-MC-adapted, RAIDER/TRAX, RANDOM, calibrated static | 300 |
| SCOPE ablations | 1800 | Hard only, soft only, performance only | 30 |
| Load increase/recovery | 1200 | SCOPE, frozen SCOPE, static, three ablations, AI-based | 70 |
| EXP3 routing ablation | All five loads | EXP3 guard off, paired with the existing guard-on cases | 50 new |

Each final scenario lasts 60 simulated minutes with three minutes of warm-up.
Final iterations are 3401–3410. SCOPE uses lambda **0.01**, step bound **0.15**,
and a 60-second controller period. Lambda is a frozen development choice, not an
optimum selected from these final results. EXP3 uses the full training catalogue,
QoS 0.20 and its existing `0.1 * min(1, 5/K)` learning-rate rule.

`run_confirmatory_study.py` reproduces the guard-on experiment. The subsequent
EXP3 ablation disables only EXP3's routing guard, retains both variants, and
recalculates the main comparison family. It does not retrain models or alter any
other policy. See [the protocol](reproducibility/PROTOCOL.md) for information access,
calibration, inference and limitations. This is an adapted EXP3 baseline, not a
claim of exact reproduction of the original authors' implementation.

## Figures

After all 50 guard-off cases finish, use the **MATLAB Command Window**:

```matlab
cd('ThreeBrains/sim_results/v5_exp3_guard_off_3401_3410/matlab')
plot_scope_paper_results
```

The working directory before `cd` should be the repository root, or use an absolute
path. Main curves retain the original 11 x 11 cm format, Times New Roman, colours,
markers and line widths. Static controls, SCOPE ablations, adaptation and EXP3
routing comparisons have separate folders. RANDOM and all registered comparators
remain in supplementary figures/statistical families. See
[FIGURE_GUIDE.md](FLaskAPIs/paper_matlab/FIGURE_GUIDE.md).

## Verification and layout

```bash
python3 reproducibility/verify_files.py
.venv/bin/python -m unittest discover -s FLaskAPIs -p 'test_*.py'
```

| Path | Purpose |
|---|---|
| `ThreeBrains/src`, `ThreeBrains/lib` | Frozen Java source and required libraries |
| `ThreeBrains/scripts/sample_app5/config/weka` | Six unchanged AI-based model files |
| `FLaskAPIs/deadline_pilot` | Simulation properties, XML and development plotting input |
| `FLaskAPIs/*.py` | Active services, training, resumable runners and tests |
| `FLaskAPIs/paper_matlab` | Publication plots with separate controls/ablations |
| `reproducibility` | Protocol, provenance, exact file hashes and verification |
| `ThreeBrains/sim_results` (generated, ignored) | Training data, models, attempts and reports |

Validation details are in [reproducibility/VALIDATION.md](reproducibility/VALIDATION.md).

Historical results, obsolete models and diagnostic launchers remain accessible at
commit `709bbf19b466c8e3a0b90e3f6ec1ea5cb10e13de` and the historical branches. This
cleanup does not rewrite Git history or delete Nancy's saved experiment directories.
Use a shallow single-branch clone for the small publication checkout; a full clone
still downloads historical objects. See `reproducibility/CLEANUP.md`.

Existing license files are retained: [LICENSE](LICENSE), [ThreeBrains/LICENSE](ThreeBrains/LICENSE)
and [NOTICE.md](NOTICE.md). Bundled dependencies retain their own license notices.
