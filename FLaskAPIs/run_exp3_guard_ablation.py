#!/usr/bin/env python3
"""Rerun only EXP3 with the deadline routing guard disabled; preserve its controls.

Consumes a complete confirmatory study. No Java, model, catalogue, EXP3 learning,
QoS, normalization values, SCOPE results or other baseline results are changed.
The source remains read-only. A separate output holds new attempts and reports.
"""
from __future__ import annotations
import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import fcntl
import json
from pathlib import Path
import shutil
import signal
import sys
import zipfile

import run_deadline_pilot as core
import run_confirmatory_study as study
import run_lambda_check as calibration
import confirmatory_reports as reports

BASE = Path(__file__).resolve().parent
REPO = BASE.parent
WORKFLOW = 'exp3_guard_ablation_v1'
CODE = ['run_exp3_guard_ablation.py', 'run_confirmatory_study.py',
        'run_deadline_pilot.py', 'run_lambda_check.py', 'confirmatory_reports.py']


def jobs(plan):
    return [j for j in study.evaluation_specs(plan)
            if j['group'] == 'main' and j['policy'] == 'EXP3_MC']


@contextmanager
def source_lock(source):
    core.require(source.is_dir(), 'Source study not found: ' + str(source))
    with (source / '.runner.lock').open('a+') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_SH | fcntl.LOCK_NB)
        except BlockingIOError:
            raise RuntimeError('Source study is currently running; wait until it finishes')
        yield


def load_plan(out):
    plan = core.read(out / 'study.json')
    core.require(plan.get('workflow') == WORKFLOW, 'Not an EXP3 guard-ablation output')
    core.require((out / 'study_checksum.txt').read_text().strip() == core.sha(out / 'study.json'),
                 'Frozen protocol changed; use a new output')
    return plan


def source_results(source, original):
    completed = []
    for job in study.evaluation_specs(original):
        core.check_stop(source)
        receipt = core.complete(source, job['key'])
        core.require(receipt is not None, 'Source study is incomplete: ' + job['key'])
        folder = source / receipt['attempt']
        core.require(study.inspect_run(folder, original, job) == receipt['result'],
                     'Source evidence and receipt differ: ' + job['key'])
        completed.append((folder, receipt['result']))
    return completed


def validate(out, plan):
    core.require(plan['output'] == str(out), 'Resume in the original output location')
    core.require(core.versions() == plan['package_versions'], 'Python package versions changed')
    core.verify(BASE, plan['runner_hashes'])
    core.verify(out, plan['input_hashes'])
    source = Path(plan['source_study'])
    core.verify(source, plan['source_evidence_hashes'])
    original = study.load_plan(source)
    core.verify(source, original['input_hashes'])


def prepare(out, args):
    if (out / 'study.json').exists():
        plan = load_plan(out)
        core.require(str(args.source_study.expanduser().resolve()) == plan['source_study'],
                     'Source differs from registered protocol')
        validate(out, plan)
        print('Already prepared: ' + str(out), flush=True)
        return
    core.require(not any(p.name != '.runner.lock' for p in out.iterdir()),
                 'Partial/nonempty output. Preserve it and choose a new --output')
    source = args.source_study.expanduser().resolve()
    with source_lock(source):
        original = study.load_plan(source)
        core.require(original.get('exp3_routing_schema', core.SCHEMA) == core.SCHEMA,
                     'Source EXP3 must be the guard-on comparator')
        status = core.read(source / 'completion.json')
        expected = len(study.evaluation_specs(original))
        core.require(status['complete'] and status['completed'] == status['expected'] == expected,
                     'Complete the source confirmatory study first')
        core.require(core.versions() == original['package_versions'],
                     'Use the same Python environment as the source study')
        core.verify(source, original['input_hashes'])
        # Imports reused for inspection/execution must match the frozen source.
        for name in CODE[2:]:
            core.require(core.sha(BASE / name) == core.sha(source / 'runtime/services' / name),
                         'Supporting runner differs from source: ' + name)
        source_results(source, original)
        for name in ['runtime', 'inputs', 'models', 'dataset']:
            shutil.copytree(source / name, out / name,
                            ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
        for name in CODE:
            shutil.copy2(BASE / name, out / 'runtime/services' / name)
        shutil.copytree(BASE / 'paper_matlab', out / 'matlab')
        provenance = out / 'source_provenance'
        provenance.mkdir()
        source_files = ['study.json', 'study_checksum.txt', 'completion.json', 'pair_checks.json']
        source_files += ['jobs/' + j['key'] + '/complete.json' for j in study.evaluation_specs(original)]
        for name in source_files:
            dest = provenance / name
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source / name, dest)
        manifest = core.read(out / 'models/model_manifest.json')
        # EXP3 uses observed rewards, not XGBoost predictions. This is explicitly
        # normalization-only metadata; the SCOPE model manifest stays intact.
        core.write(out / 'inputs/exp3_edge_first_normalization.json', dict(
            artifact_type='exp3_normalization_only', routing_schema='edge_first_v1',
            normalization=manifest['normalization'],
            normalization_source_routing_schema=manifest['routing_schema'],
            source_manifest_sha256=core.sha(out / 'models/model_manifest.json'),
            note='Same frozen training-derived normalization and catalogue. No model prediction is used by EXP3.'))
        plan = dict(original)
        plan.update(workflow=WORKFLOW, source_study=str(source), output=str(out),
            java=core.select_java(args.java), python=sys.executable,
            created=datetime.now(timezone.utc).isoformat(),
            exp3_routing_schema='edge_first_v1',
            exp3_normalization_manifest='inputs/exp3_edge_first_normalization.json',
            imported_calibration_jobs=[],
            purpose='Post-confirmation routing ablation: disable the EXP3 deadline guard only; keep both variants.',
            runner_hashes={n: core.sha(BASE / n) for n in CODE},
            source_evidence_hashes={n: core.sha(source / n) for n in source_files},
            input_hashes={str(p.relative_to(out)): core.sha(p)
                for d in ['runtime', 'inputs', 'models', 'dataset', 'source_provenance', 'matlab']
                for p in (out / d).rglob('*') if p.is_file()})
        core.write(out / 'study.json', plan)
        (out / 'study_checksum.txt').write_text(core.sha(out / 'study.json') + '\n')
    print(f'PREPARED: {len(jobs(plan))} new EXP3 scenarios; {expected-len(jobs(plan))} unchanged scenarios reused.\n'
          f'Original results preserved. No training or manual Java arguments needed.\n{out}', flush=True)


def export(out, plan):
    source = Path(plan['source_study'])
    original = study.load_plan(source)
    old = source_results(source, original)
    combined = []
    guard_rows = []
    finished = 0
    for folder, result in old:
        job = result['spec']
        if job not in jobs(plan):
            combined.append((folder, result))
            continue
        saved = study.saved_run(out, plan, job)
        if saved is None:
            continue
        new_folder, new = saved
        core.require(study.inspect_run(new_folder, plan, job) == new,
                     'New evidence and receipt differ')
        core.require(new['workload_sha256'] == result['workload_sha256'],
                     'Guard-on/off workloads differ')
        combined.append(saved)
        finished += 1
        for app in core.APPS:
            for metric in ['failure_pct', 'service_seconds']:
                on = result['metrics'][app][metric]
                off = new['metrics'][app][metric]
                guard_rows.append(dict(load=job['load'], iteration=job['iteration'],
                    application=app, metric=metric, guard_on=on, guard_off=off, off_minus_on=off-on))
    pairs = core.read(source / 'pair_checks.json')
    reports.export(out, plan, combined, pairs, len(old))
    reports.write_csv(out / 'exp3_guard_pairs.csv', guard_rows,
        ['load', 'iteration', 'application', 'metric', 'guard_on', 'guard_off', 'off_minus_on'])
    if finished == len(jobs(plan)):
        contrasts = []
        for n in plan['loads']:
            for metric in ['failure_pct', 'service_seconds']:
                values = [r['off_minus_on'] for r in guard_rows
                          if r['load'] == n and r['application'] == 'ALL_APPS' and r['metric'] == metric]
                contrasts.append(dict(family='EXP3_guard_effect', load=n, metric=metric,
                    **reports.paired(values), p_holm=None, family_tests=0,
                    interpretation='guard-off minus guard-on; positive means guard-off worse'))
        reports.write_csv(out / 'exp3_guard_contrasts.csv', reports.holm(contrasts))
    status = core.read(out / 'completion.json')
    status.update(new_exp3_completed=finished, new_exp3_expected=len(jobs(plan)),
        reused_unchanged=len(old)-len(jobs(plan)), exp3_routing_schema='edge_first_v1',
        note='Post-confirmation EXP3 routing ablation, not a new independent confirmation. '
             'Keep the guard-on comparison. Main Holm family recomputed, retaining all comparators.')
    core.write(out / 'completion.json', status)
    print(f'EXP3 guard-off: {finished}/{len(jobs(plan))}; source results remain unchanged.', flush=True)


def package(out, plan):
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    target = out.parent / (out.name + '_review_' + stamp + '.zip')
    with zipfile.ZipFile(target, 'x', zipfile.ZIP_DEFLATED) as z:
        for p in sorted(out.rglob('*')):
            rel = p.relative_to(out)
            if not p.is_file() or p.is_symlink() or any(x in rel.parts for x in
                    ['runtime', 'weka', '__pycache__']) or p.name == '.runner.lock':
                continue
            z.write(p, Path(out.name) / rel)
        for name in CODE + ['exp3_mc_service.py', 'scope_objective.py']:
            z.write(out / 'runtime/services' / name, Path(out.name) / 'code' / name)
    print('Review ZIP: ' + str(target), flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('stage', choices=['prepare', 'run', 'status', 'stop', 'package'])
    parser.add_argument('--source-study', type=Path, default=REPO / 'ThreeBrains/sim_results/v5_final_3401_3410')
    parser.add_argument('--output', type=Path, default=REPO / 'ThreeBrains/sim_results/v5_exp3_guard_off_3401_3410')
    parser.add_argument('--java')
    parser.add_argument('--iteration', type=int, help='Run one registered seed; full run later resumes all seeds')
    args = parser.parse_args()
    out = args.output.expanduser().resolve()
    core.require(args.iteration is None or args.stage == 'run', '--iteration requires run')
    if args.stage in ['status', 'stop']:
        plan = load_plan(out)
        if args.stage == 'stop':
            (out / 'STOP_REQUESTED').touch()
            print('Stop requested. Wait for process cleanup; repeat run to resume.')
        else:
            print(f"EXP3 receipts: {sum((out/'jobs'/j['key']/'complete.json').exists() for j in jobs(plan))}/{len(jobs(plan))}\n{out}")
        return
    if args.stage == 'prepare':
        calibration.check_location(args.source_study.expanduser().resolve(), out)
        out.mkdir(parents=True, exist_ok=True)
    core.require(out.is_dir(), 'Run prepare first')
    signal.signal(signal.SIGINT, core.signal_stop)
    signal.signal(signal.SIGTERM, core.signal_stop)
    with (out / '.runner.lock').open('a+') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise RuntimeError('Another runner owns this output')
        (out / 'STOP_REQUESTED').unlink(missing_ok=True)
        try:
            if args.stage == 'prepare':
                prepare(out, args)
                return
            plan = load_plan(out)
            with source_lock(Path(plan['source_study'])):
                validate(out, plan)
                if args.stage == 'run':
                    core.require(args.iteration is None or args.iteration in plan['iterations'],
                                 'Iteration is not in the frozen protocol')
                    for job in jobs(plan):
                        if args.iteration is None or args.iteration == job['iteration']:
                            study.simulate(out, plan, job, {})
                export(out, plan)
                if args.stage == 'package':
                    package(out, plan)
        except core.Stopped:
            print('STOPPED safely. Completed jobs retained; repeat run to resume.', flush=True)
            raise SystemExit(130)


if __name__ == '__main__':
    main()
