#!/usr/bin/env python3
"""Start a matched SCOPE/EXP3 pair with explicit settings and provenance.

Leave this terminal open while running Java. Use a fresh output directory for
each experiment. --diagnostic records full SCOPE requests for diagnosis (extra
disk I/O means these runs must not be used to benchmark controller overhead).
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import socket
import subprocess
import sys
import time
import urllib.request

from scope_objective import CURRENT_TELEMETRY, check_telemetry, manifest_support

BASE = Path(__file__).resolve().parent


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--models', type=Path, required=True)
    parser.add_argument('--catalogue', type=Path,
                        default=BASE/'scope_candidate_dataset/candidate_dataset_train.csv')
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--diagnostic', action='store_true')
    parser.add_argument('--include-rt-opt', action='store_true', help='Also start Optimizer.py on port 5001.')
    args = parser.parse_args()
    model_dir, catalogue, output = args.models.resolve(), args.catalogue.resolve(), args.output.resolve()
    manifest_path = model_dir/'model_manifest.json'
    manifest = json.loads(manifest_path.read_text())
    support, source = manifest_support(manifest)
    if source != 'model_manifest':
        raise ValueError('Revised runs require a manifest with training-only normalization.')
    check_telemetry(manifest, CURRENT_TELEMETRY)
    scripts = [(5002, 'scope_diagnostic_service.py' if args.diagnostic else 'ml_optimizer_service.py'),
               (5003, 'exp3_mc_service.py')]
    if args.include_rt_opt:
        scripts.append((5001, 'Optimizer.py'))
    for port, _ in scripts:
        with socket.socket() as sock:
            sock.bind(('127.0.0.1', port))  # Refuse to reuse an unrelated running service.
    # Clear inherited service overrides, including exact-file log paths and eta.
    env = {k: v for k, v in os.environ.items()
           if not k.startswith(('SCOPE_', 'EXP3_MC_', 'RT_OPT_'))}
    settings = {
        'PYTHONUNBUFFERED': '1', 'SCOPE_RESULTS_DIR': str(model_dir),
        'SCOPE_CANDIDATE_DATASET': str(catalogue),
        'SCOPE_ABLATION_RESULTS_DIR': str(output/'scope'),
        'SCOPE_DIAGNOSTIC_DIR': str(output/'scope_diagnostics'),
        'SCOPE_HARD_STABILITY': '1', 'SCOPE_LAMBDA': '0.20', 'SCOPE_R_MAX': '0.15',
        'SCOPE_PORT': '5002', 'SCOPE_W_FAILURE': '0.50', 'SCOPE_W_SERVICE': '0.50',
        'EXP3_MC_CANDIDATE_DATASET': str(catalogue), 'EXP3_MC_ARM_COUNT': '0',
        'EXP3_MC_NORMALIZATION_MANIFEST': str(manifest_path),
        'EXP3_MC_QOS_THRESHOLD': '0.20', 'EXP3_MC_PORT': '5003',
        'EXP3_MC_RESULTS_DIR': str(output/'exp3'),
        'EXP3_MC_EXPERIMENT_ID': output.name,
        'EXP3_MC_W_FAILURE': '0.50', 'EXP3_MC_W_SERVICE': '0.50',
    }
    env.update(settings)
    inputs = [manifest_path, catalogue, BASE/'scope_objective.py', BASE/'ml_optimizer_service.py',
              BASE/'exp3_mc_service.py', BASE/'Optimizer.py', Path(__file__).resolve()]
    inputs += [model_dir/m['model_file'] for m in manifest['models']]
    java = BASE.parent/'ThreeBrains/src/edu/boun/edgecloudsim/applications/sample_app5'
    inputs += [java/f for f in ('VehicularEdgeOrchestrator.java', 'EdgeVmSelector.java', 'OptimizerReply.java')]
    hashes = {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in inputs}
    output.mkdir(parents=True, exist_ok=False)
    record = {'settings': settings, 'sha256': hashes, 'normalization': support,
              'python': sys.version, 'platform': platform.platform(),
              'diagnostic': args.diagnostic, 'status': 'starting',
              'java_required_vm_option': '-Dscope.optimizer.failFast=true',
              'note': 'Copy the exact Java configuration and invocation into this experiment directory.'}
    metadata = output/'experiment.json'
    metadata.write_text(json.dumps(record, indent=2))
    processes, logs = [], []
    try:
        for port, script in scripts:
            log = (output/f'{port}.log').open('w')
            logs.append(log)
            processes.append(subprocess.Popen([sys.executable, '-u', str(BASE/script)],
                                               env=env, cwd=BASE, stdout=log, stderr=log))
        # Both compared services must advertise exactly the same objective scale.
        deadline = time.monotonic() + 60
        health = {}
        while len(health) < len(scripts):
            if any(p.poll() is not None for p in processes):
                raise RuntimeError(f'A service exited; inspect {output}')
            for port, _ in scripts:
                if port in health:
                    continue
                try:
                    with urllib.request.urlopen(f'http://127.0.0.1:{port}/health', timeout=1) as response:
                        body = json.load(response)
                except (OSError, ValueError):
                    continue
                if port in (5002, 5003) and body.get('normalization') != support:
                    raise RuntimeError(f'Normalization mismatch on port {port}')
                health[port] = body
            if time.monotonic() > deadline:
                raise RuntimeError(f'Services did not become ready; inspect {output}')
            time.sleep(.25)
        record.update(status='ready', health=health)
        metadata.write_text(json.dumps(record, indent=2))
        print(f'SCOPE and EXP3 ready. Logs: {output}', flush=True)
        print('Java VM option: -Dscope.optimizer.failFast=true; stop services with Ctrl+C.', flush=True)
        while all(p.poll() is None for p in processes):
            time.sleep(.5)
        raise RuntimeError(f'A service exited; inspect {output}')
    except KeyboardInterrupt:
        pass
    finally:
        for process in processes:
            if process.poll() is None:
                process.terminate()
        for process in processes:
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
        for log in logs:
            log.close()


if __name__ == '__main__':
    main()
