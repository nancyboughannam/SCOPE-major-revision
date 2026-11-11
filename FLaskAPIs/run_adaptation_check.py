#!/usr/bin/env python3
"""Run an isolated adaptive/frozen SCOPE pair and package a phase comparison.

Defaults: 1200 vehicles, 60 minutes, 3-minute warm-up, 1.5x arrival rate from
minute 30, lambda .05, R_max .15. Frozen SCOPE stops applying changes at minute
30. Both modes still score/log requests, so this is not an overhead benchmark.
"""
import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import re
import shutil
import socket
import subprocess
import sys
import time
import urllib.request
import zipfile

from scope_objective import CURRENT_TELEMETRY, check_telemetry, manifest_support

BASE = Path(__file__).resolve().parent
ROOT = BASE.parent
THREE = ROOT/'ThreeBrains'
PACKAGE = 'edu/boun/edgecloudsim/applications/sample_app5'


def java_candidates(explicit=None):
    if explicit:
        return [str(Path(explicit).expanduser())]
    candidates = []
    if os.environ.get('JAVA_HOME'):
        candidates.append(str(Path(os.environ['JAVA_HOME'])/'bin/java'))
    if shutil.which('java'):
        candidates.append(shutil.which('java'))
    if sys.platform == 'darwin':
        try:
            found = subprocess.run(['/usr/libexec/java_home'], capture_output=True,
                                   text=True, timeout=10)
            if found.returncode == 0 and found.stdout.strip():
                candidates.append(str(Path(found.stdout.strip())/'bin/java'))
        except (OSError, subprocess.TimeoutExpired):
            pass
        for parent, pattern in (
                (Path('/Library/Java/JavaVirtualMachines'), '*/Contents/Home/bin/java'),
                (Path.home()/'Library/Java/JavaVirtualMachines', '*/Contents/Home/bin/java'),
                (Path('/opt/homebrew/opt'), 'openjdk*/bin/java'),
                (Path('/usr/local/opt'), 'openjdk*/bin/java')):
            candidates.extend(str(path) for path in sorted(parent.glob(pattern)))
    return list(dict.fromkeys(candidates))


def select_java(explicit=None):
    checked = []
    for candidate in java_candidates(explicit):
        try:
            result = subprocess.run(
                [candidate, '-m', 'jdk.compiler/com.sun.tools.javac.Main', '-version'],
                capture_output=True, text=True, timeout=10)
            version = re.search(r'\bjavac\s+(\d+)', result.stdout+'\n'+result.stderr)
            if result.returncode == 0 and version and int(version[1]) >= 21:
                executable = str(Path(shutil.which(candidate) or candidate).resolve())
                return executable, int(version[1])
            checked.append(candidate+(': JDK '+version[1] if version else ': compiler unavailable'))
        except (OSError, subprocess.TimeoutExpired):
            checked.append(candidate+': executable unavailable')
    raise ValueError('This CloudSim dependency requires JDK 21 or newer with a compiler. '
                     'Use --java /path/to/jdk/Contents/Home/bin/java to select one explicitly. '
                     'Checked: '+('; '.join(checked) or 'no Java installations found'))


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write_json(path, data):
    path.write_text(json.dumps(data, indent=2, allow_nan=False))


def phase_metrics(rows, normalization):
    totals = []
    for app in range(3):
        stats = [r['request']['app_stats'][str(app)] for r in rows]
        completed = sum(s['completed'] for s in stats)
        failed = sum(s['failures'] for s in stats)
        late = sum(s['deadline_misses'] for s in stats)
        totals.append(dict(app=app, completed=completed, failed=failed, late=late,
                           service_sum=sum(s['completed']*s['mean_service_time'] for s in stats)))
    completed = sum(s['completed'] for s in totals)
    failed = sum(s['failed'] for s in totals)
    if not completed or not completed+failed:
        raise ValueError('Insufficient finalized tasks for phase comparison')
    def clip(v):
        return min(1., max(0., v))
    costs = []
    for r in rows:
        cost = 0.
        for app, weight in enumerate(r['app_weights']):
            s = r['request']['app_stats'][str(app)]
            f = clip((s['failure_rate']-normalization['failure_min']) /
                     (normalization['failure_max']-normalization['failure_min']))
            d = clip((s['deadline_norm_service_time']-normalization['dnst_min']) /
                     (normalization['dnst_max']-normalization['dnst_min']))
            cost += .5*weight*(f+d)
        costs.append(cost)
    return dict(windows=len(rows), completed=completed, failed=failed,
                failure_pct=100*failed/(completed+failed),
                service_s=sum(s['service_sum'] for s in totals)/completed,
                late_pct_completed=100*sum(s['late'] for s in totals)/completed,
                mean_window_performance_cost=sum(costs)/len(costs),
                by_app=totals)


def summarize(output, args, normalization):
    reports, records, fingerprints = {}, {}, {}
    expected_times = list(range(70, int(args.minutes*60), 60))
    for mode in ('adaptive', 'frozen'):
        folder = output/mode
        paths = list((folder/'diagnostics').rglob('*.jsonl'))
        if len(paths) != 1:
            raise ValueError(f'Expected one diagnostic stream for {mode}; got {len(paths)}')
        rows = [json.loads(line) for line in paths[0].read_text().splitlines()]
        if [r['request']['timestamp'] for r in rows] != expected_times:
            raise ValueError(f'Missing optimizer windows for {mode}')
        for r in rows:
            request = r['request']
            assert request['simulation_seed'] == 20260828+args.iteration
            assert request['num_devices'] == args.vehicles
            assert r['selected']['reconfiguration_cost'] <= .15+1e-9
            assert r['settings']['control_mode'] == mode
            if mode == 'frozen' and request['timestamp'] >= args.shift_seconds:
                assert r['settings']['control_frozen']
                assert r['selected']['reconfiguration_cost'] <= 1e-9
        for prev, cur in zip(rows, rows[1:]):
            assert prev['selected']['configuration'] == cur['current']['configuration']
        console = (folder/'java.log').read_text()
        fingerprint = re.findall(r'WORKLOAD_AUDIT .*sha256=([0-9a-f]{64})', console)
        if len(fingerprint) != 1 or 'Scenario finished' not in console:
            raise ValueError(f'Missing completed workload audit for {mode}')
        fingerprints[mode] = fingerprint[0]
        records[mode] = rows
        changes = [{'time': r['request']['timestamp'],
                    'distance': r['selected']['reconfiguration_cost'],
                    'configuration': r['selected']['configuration']} for r in rows
                   if r['selected']['reconfiguration_cost'] > 1e-9]
        pre = [r for r in rows if r['request']['timestamp']-60 >= args.warmup_minutes*60
               and r['request']['timestamp'] <= args.shift_seconds]
        post = [r for r in rows if r['request']['timestamp']-60 >= args.shift_seconds]
        generic = list((folder/'java').glob('*ALL_APPS_GENERIC.log'))
        assert len(generic) == 1
        values = [float(v) for v in generic[0].read_text().splitlines()[1].split(';')]
        reports[mode] = dict(
            before=phase_metrics(pre, normalization), after=phase_metrics(post, normalization),
            changes=changes, changes_after_shift=sum(c['time'] >= args.shift_seconds for c in changes),
            total_churn=sum(c['distance'] for c in changes),
            full_run=dict(completed=values[0], failed=values[1], pending=values[2],
                          failure_pct=100*values[1]/(values[0]+values[1]), service_s=values[4]))
    assert fingerprints['adaptive'] == fingerprints['frozen'], 'Paired workloads differ'
    for a, b in zip(records['adaptive'], records['frozen']):
        if a['request']['timestamp'] < args.shift_seconds:
            assert a['request'] == b['request'], 'Before-change observations differ'
            assert a['selected']['configuration'] == b['selected']['configuration']
    a, b = [reports[m]['full_run'] for m in ('adaptive', 'frozen')]
    assert sum(a[k] for k in ('completed','failed','pending')) == sum(b[k] for k in ('completed','failed','pending'))
    report = dict(status='complete', paired_workload_sha256=fingerprints['adaptive'],
                  before_change_requests_identical=True, results=reports,
                  note='Outcome reporting windows, not admission cohorts. Windows crossing warm-up or the rate step and the unlogged tail are excluded from phase summaries. Performance cost excludes switching cost. Frozen SCOPE is not a tuned best-static baseline.')
    write_json(output/'comparison.json', report)
    lines = ['Paired adaptation check completed.',
             'mode     phase    failure_pct service_seconds late_pct_completed changes_after_shift']
    for mode in ('adaptive','frozen'):
        for phase in ('before','after'):
            m = reports[mode][phase]
            lines.append(f"{mode:8} {phase:8} {m['failure_pct']:11.6f} {m['service_s']:15.6f} {m['late_pct_completed']:18.6f} {reports[mode]['changes_after_shift']}")
    lines += ['', report['note'], 'This is development evidence; report unfavorable and unchanged outcomes too.']
    (output/'comparison.txt').write_text('\n'.join(lines)+'\n')
    print('\n'.join(lines), flush=True)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--models', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--config', type=Path, default=THREE/'scripts/sample_app5/config/default_config.properties')
    p.add_argument('--catalogue', type=Path, default=BASE/'scope_candidate_dataset/candidate_dataset_train.csv')
    p.add_argument('--java', type=Path, help='Explicit JDK 21+ java executable; otherwise discover an installed JDK.')
    p.add_argument('--iteration', type=int, default=1004)
    p.add_argument('--vehicles', type=int, default=1200)
    p.add_argument('--minutes', type=float, default=60)
    p.add_argument('--warmup-minutes', type=float, default=3)
    p.add_argument('--shift-seconds', type=float, default=1800)
    rate = p.add_mutually_exclusive_group()
    rate.add_argument('--rate-multiplier', type=float,
                      help='Common post-change arrival multiplier (default: 1.5).')
    rate.add_argument('--app-rate-multipliers', type=float, nargs=3,
                      metavar=('TRAFFIC', 'DANGER', 'INFOTAINMENT'),
                      help='Post-change arrival multipliers in applications.xml order; replaces the common multiplier.')
    p.add_argument('--lambda', dest='penalty', type=float, default=.05)
    args = p.parse_args()
    if args.rate_multiplier is None and args.app_rate_multipliers is None:
        args.rate_multiplier = 1.5
    rates = args.app_rate_multipliers or [args.rate_multiplier]
    if not all(math.isfinite(x) for x in (args.minutes,args.warmup_minutes,args.shift_seconds,args.penalty,*rates)):
        p.error('Experiment parameters must be finite')
    if not (args.vehicles > 0 and args.iteration >= 0 and 0 <= args.penalty <= 1 and all(x > 0 for x in rates)
            and 0 <= args.warmup_minutes*60 < args.shift_seconds < args.minutes*60):
        p.error('Invalid load, iteration, penalty, or phase boundaries')
    if min(args.shift_seconds-args.warmup_minutes*60, args.minutes*60-args.shift_seconds) < 180:
        p.error('Keep at least 180 seconds in each measured phase')
    output = args.output.resolve()
    if output.exists() or output.with_suffix('.zip').exists():
        p.error('Use a fresh output directory and ZIP name')
    try:
        java, java_major = select_java(args.java)
    except ValueError as error:
        p.error(str(error))
    print(f'Using JDK {java_major}: {java}', flush=True)
    compiler = [java, '-m', 'jdk.compiler/com.sun.tools.javac.Main']
    libraries = sorted((THREE/'lib').glob('*.jar'))
    if not libraries:
        p.error('No Java dependencies found in ThreeBrains/lib')
    library_path = os.pathsep.join(str(f) for f in libraries)
    models, catalogue, config = args.models.resolve(), args.catalogue.resolve(), args.config.resolve()
    manifest = json.loads((models/'model_manifest.json').read_text())
    normalization, source = manifest_support(manifest)
    if source != 'model_manifest':
        raise ValueError('Training normalization is required')
    check_telemetry(manifest, CURRENT_TELEMETRY)
    with socket.socket() as sock:
        # Match Flask's address reuse: a closed prior run may leave TIME_WAIT
        # connections, while a live listener must still fail this availability check.
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind(('127.0.0.1', 5002))
    output.mkdir(parents=True)
    inputs, classes = output/'inputs', output/'classes'
    inputs.mkdir(); classes.mkdir()
    shutil.copy2(config, inputs/'original.properties')
    for name in ('edge_devices.xml','applications.xml'):
        shutil.copy2(config.parent/name, inputs/name)
    shutil.copytree(config.parent/'weka', inputs/'weka')
    overrides = dict(simulation_time=str(args.minutes),warm_up_period=str(args.warmup_minutes),
                     min_number_of_mobile_devices=str(args.vehicles),max_number_of_mobile_devices=str(args.vehicles),
                     mobile_device_counter_size='1',orchestrator_policies='SCOPE',file_log_enabled='true',deep_file_log_enabled='false')
    lines, seen = [], set()
    for line in config.read_text().splitlines():
        key = line.split('=',1)[0].strip()
        if '=' in line and not line.lstrip().startswith('#') and key in overrides:
            if key in seen: raise ValueError('Duplicate configuration property: '+key)
            line = key+'='+overrides[key]; seen.add(key)
        lines.append(line)
    lines += [k+'='+v for k,v in overrides.items() if k not in seen]
    (inputs/'experiment.properties').write_text('\n'.join(lines)+'\n')
    sources = list((THREE/'src').rglob('*.java'))+list((THREE/'lib').glob('*.jar'))
    sources += [BASE/name for name in ('ml_optimizer_service.py','scope_objective.py','scope_diagnostic_service.py','scope_adaptation_service.py','run_adaptation_check.py')]
    sources += [catalogue, models/'model_manifest.json']+[models/m['model_file'] for m in manifest['models']]
    sources += [f for f in inputs.rglob('*') if f.is_file()]
    hashes = {str(f):sha256(f) for f in sources}
    plan = dict(status='starting', iteration=args.iteration, seed=20260828+args.iteration,
                vehicles=args.vehicles, minutes=args.minutes, warmup_minutes=args.warmup_minutes,
                shift_seconds=args.shift_seconds, rate_multiplier=args.rate_multiplier,
                app_rate_multipliers=args.app_rate_multipliers,
                freeze_seconds=args.shift_seconds, penalty=args.penalty, r_max=.15,
                modes=['adaptive','frozen'], normalization=normalization, input_sha256=hashes,
                interpretation='Development paired control; no best-static or overhead claim',
                python=sys.executable, java_executable=java, java_major=java_major)
    write_json(output/'experiment.json', plan)
    print('Compiling an isolated Java build...', flush=True)
    with (output/'compile.log').open('w') as log:
        subprocess.run(compiler+['-classpath',library_path,'-sourcepath',str(THREE/'src'),
                                 '-d',str(classes),str(THREE/'src'/PACKAGE/'VehicularMainApp.java')],
                       stdout=log, stderr=log, check=True)
    plan['class_sha256'] = {str(f.relative_to(classes)):sha256(f) for f in classes.rglob('*.class')}
    write_json(output/'experiment.json', plan)
    for mode in ('adaptive','frozen'):
        folder = output/mode; folder.mkdir()
        java_output = folder/'java'
        java_output.mkdir()  # SimUtils.cleanOutputFolder requires an existing directory.
        env = {k:v for k,v in os.environ.items() if not k.startswith(('SCOPE_','EXP3_MC_','RT_OPT_'))}
        settings = dict(PYTHONUNBUFFERED='1',SCOPE_RESULTS_DIR=str(models),SCOPE_CANDIDATE_DATASET=str(catalogue),
                        SCOPE_DIAGNOSTIC_DIR=str(folder/'diagnostics'), SCOPE_ABLATION_RESULTS_DIR=str(folder/'scope'),
                        SCOPE_HARD_STABILITY='1',SCOPE_LAMBDA=str(args.penalty),SCOPE_R_MAX='.15',SCOPE_PORT='5002',
                        SCOPE_W_FAILURE='.5',SCOPE_W_SERVICE='.5',SCOPE_ADAPTATION_MODE=mode,
                        SCOPE_ADAPTATION_FREEZE_SECONDS=str(args.shift_seconds))
        env.update(settings)
        write_json(folder/'settings.json', settings)
        rate_option = (f'-Dscope.workload.rateMultiplier={args.rate_multiplier}'
                       if args.app_rate_multipliers is None else
                       '-Dscope.workload.appRateMultipliers='+','.join(map(str, args.app_rate_multipliers)))
        command = [java,'-Xmx2g','-Dscope.optimizer.failFast=true',
                   f'-Dscope.workload.shiftSeconds={args.shift_seconds}',
                   rate_option,
                   '-cp',str(classes)+os.pathsep+library_path,
                   'edu.boun.edgecloudsim.applications.sample_app5.VehicularMainApp',
                   str(inputs/'experiment.properties'),str(inputs/'edge_devices.xml'),
                   str(inputs/'applications.xml'),str(java_output),str(args.iteration)]
        write_json(folder/'java_command.json', command)
        print(f'Running {mode}: {args.vehicles} vehicles, iteration {args.iteration}. Logs: {folder}', flush=True)
        with (folder/'service.log').open('w') as log:
            process = subprocess.Popen([sys.executable,'-u',str(BASE/'scope_adaptation_service.py')],
                                       env=env,cwd=BASE,stdout=log,stderr=log)
            try:
                deadline = time.monotonic()+60
                while True:
                    if process.poll() is not None:
                        raise RuntimeError('Service exited; inspect '+str(folder/'service.log'))
                    try:
                        with urllib.request.urlopen('http://127.0.0.1:5002/health',timeout=1) as response:
                            health = json.load(response)
                    except OSError:
                        if time.monotonic() >= deadline: raise TimeoutError('Service startup')
                        time.sleep(.25)
                        continue
                    assert health['control_mode'] == mode and health['freeze_after_seconds'] == args.shift_seconds
                    assert health['normalization'] == normalization and health['lambda'] == args.penalty
                    assert health['hard_stability_enabled'] and health['r_max'] == .15
                    write_json(folder/'health.json',health)
                    break
                with (folder/'java.log').open('w') as simlog:
                    subprocess.run(command,cwd=ROOT,stdout=simlog,stderr=simlog,check=True)
            finally:
                process.terminate()
                try: process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill(); process.wait()
        for name in ('service.log','java.log'):
            text = (folder/name).read_text()
            if any(token in text for token in ('Traceback','Exception','ERROR','unexpected error','" 500 ')):
                raise RuntimeError('Run reported an error; inspect '+str(folder/name))
        print(f'{mode} finished.', flush=True)
    assert all(sha256(f) == digest for f,digest in hashes.items()), 'An input changed during the experiment'
    summarize(output,args,normalization)
    plan['status'] = 'complete'
    write_json(output/'experiment.json',plan)
    archive = output.with_suffix('.zip')
    with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED) as z:
        for f in output.rglob('*'):
            if f.is_file() and classes not in f.parents:
                z.write(f,Path(output.name)/f.relative_to(output))
    print('Results ZIP: '+str(archive), flush=True)


if __name__ == '__main__':
    main()
