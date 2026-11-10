#!/usr/bin/env python3
"""Read completed Java results directly from a ZIP, including non-1-based iterations.

Outputs raw rows, means and sample SD across iterations, and an audit. No
significance claims: vehicle loads within an iteration are not independent seeds.
"""
import argparse
import csv
import hashlib
import io
import json
from pathlib import Path
import re
import zipfile

import pandas as pd

PATTERN = re.compile(r'(?:^|/)ite(\d+)/SIMRESULT_ITS_SCENARIO_(.+)_(\d+)DEVICES_(.+)_GENERIC\.log$')


def analyze(archive, output):
    rows, seeds = [], []
    with zipfile.ZipFile(archive) as zipped:
        names = [n for n in zipped.namelist() if not n.startswith('__MACOSX/')]
        for name in names:
            match = PATTERN.search(name)
            if match:
                iteration, policy, devices, app = match.groups()
                values = [[float(v) for v in line.split(';')[:12]]
                          for line in zipped.read(name).decode().splitlines()
                          if line and not line.startswith('#')]
                total, edge, cloud = values[:3]
                complete, failed, pending = total[:3]
                if complete + failed <= 0:
                    raise ValueError(f'No finalized tasks: {name}')
                if abs(failed - sum(total[i] for i in (3, 9, 10))) > 1e-6:
                    raise ValueError(f'Failure categories do not reconcile: {name}')
                rows.append(dict(iteration=int(iteration), policy=policy, vehicles=int(devices), app=app,
                    completed=complete, failed=failed, pending=pending,
                    failure_pct=100*failed/(complete+failed), service_s=total[4],
                    capacity_failures=total[9], bandwidth_failures=total[3], mobility_failures=total[10],
                    edge_cpu_pct=edge[7],
                    cloud_finalized_share=(cloud[0]+cloud[1])/(complete+failed)))
            if re.search(r'/EDGE_VM_SELECTION_.+\.csv$', name):
                audit = list(csv.DictReader(io.StringIO(zipped.read(name).decode())))
                unique = {r['simulation_seed'] for r in audit}
                if len(unique) != 1:
                    raise ValueError(f'Inconsistent seed: {name}')
                seeds.append(dict(file=name, seed=int(unique.pop()), vms=len(audit),
                                  used_vms=sum(int(r['assignment_selections'])>0 for r in audit)))
    frame = pd.DataFrame(rows).sort_values(['iteration','policy','vehicles','app'])
    if frame.empty or frame.duplicated(['iteration','policy','vehicles','app']).any():
        raise ValueError('Missing data or duplicate run keys')
    all_apps = frame[frame.app=='ALL_APPS']
    iterations = sorted(all_apps.iteration.unique().tolist())
    policies = sorted(all_apps.policy.unique().tolist())
    loads = sorted(all_apps.vehicles.unique().tolist())
    expected = pd.MultiIndex.from_product([iterations,policies,loads], names=['iteration','policy','vehicles'])
    missing = expected.difference(pd.MultiIndex.from_frame(all_apps[['iteration','policy','vehicles']]))
    if len(missing):
        raise ValueError(f'Incomplete all-app run grid: {missing.tolist()}')
    columns = ['failure_pct','service_s','edge_cpu_pct','cloud_finalized_share']
    summary = frame.groupby(['policy','vehicles','app'])[columns].agg(['mean','std','count'])
    summary.columns = ['_'.join(c) for c in summary.columns]
    output.mkdir(parents=True, exist_ok=False)
    frame.to_csv(output/'per_run_metrics.csv', index=False)
    summary.reset_index().to_csv(output/'summary.csv', index=False)
    audit = dict(archive_sha256=hashlib.sha256(archive.read_bytes()).hexdigest(),
                 iterations=iterations, policies=policies, loads=loads,
                 all_app_runs=len(all_apps), all_app_and_class_records=len(frame),
                 java_seed_evidence=seeds,
                 python_decision_files=[n for n in names if 'decision' in n.lower() or n.endswith('.jsonl')],
                 metric_definitions={
                    'failure_pct':'100 * failed / (completed + failed); pending excluded and reported separately',
                    'service_s':'Mean service time among completed tasks only; not all submitted tasks',
                    'summary':'Unweighted mean and sample SD across iterations at each policy/load/app',
                    'cloud_finalized_share':'Cloud completed + cloud failed divided by total completed + total failed',
                    'seed_limit':'VM audit verifies seeds only for policies writing that audit; no AI_BASED seed manifest'},
                 limitations=['No claim of statistical significance or universal dominance.',
                              'No decisions/configuration metadata: cannot attribute cause to lambda, budget, or predictions.'])
    (output/'audit.json').write_text(json.dumps(audit, indent=2))
    print(f'Validated {len(all_apps)} all-app runs across iterations {iterations}; outputs: {output}')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('archive', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    analyze(args.archive, args.output)
