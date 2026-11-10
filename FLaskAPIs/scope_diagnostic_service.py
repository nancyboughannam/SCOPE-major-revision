#!/usr/bin/env python3
"""Run the existing SCOPE service with extra diagnostics and unchanged decisions.

Put this file beside ml_optimizer_service.py and run it INSTEAD of that file,
using the same interpreter and model/catalogue/objective environment variables.
Only the output-log locations are overridden, to protect the full-study logs.
"""
from __future__ import annotations

import hashlib
import json
import os
import platform
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
SESSION = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ') + '_' + uuid.uuid4().hex[:8]
ROOT = Path(os.environ.get('SCOPE_DIAGNOSTIC_DIR', str(BASE_DIR / 'revision_results' / 'scope_diagnostic')))
SESSION_DIR = ROOT / SESSION
SESSION_DIR.mkdir(parents=True, exist_ok=False)

# Isolate all diagnostics, including the service's usual CSVs. No scoring or
# model environment variable is changed here.
ORIGINAL_LOG_SETTINGS = {k: os.environ.get(k) for k in ['SCOPE_ABLATION_RESULTS_DIR', 'SCOPE_DECISION_LOG']}
os.environ['SCOPE_ABLATION_RESULTS_DIR'] = str(SESSION_DIR / 'ordinary_logs')
os.environ.pop('SCOPE_DECISION_LOG', None)

import numpy as np
import ml_optimizer_service as service

LOCK = threading.Lock()
ORIGINAL_WRITE = service._write_decision_log


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write_metadata():
    support = {
        'failure_min': service.TRAIN_FAILURE_MIN,
        'failure_max': service.TRAIN_FAILURE_MAX,
        'dnst_min': service.TRAIN_DNST_MIN,
        'dnst_max': service.TRAIN_DNST_MAX,
    }
    value = {
        'diagnostic_version': 1,
        'purpose': 'diagnostic run only; no scoring or policy changes',
        'session': SESSION,
        'python_version': platform.python_version(),
        'xgboost_version': service.xgb.__version__,
        'service_file': str(Path(service.__file__).resolve()),
        'service_sha256': sha256(service.__file__),
        'model_manifest_path': str(service.MANIFEST_PATH),
        'model_manifest_sha256': sha256(service.MANIFEST_PATH),
        'catalogue_path': str(service.CANDIDATE_DATASET_PATH),
        'catalogue_sha256': sha256(service.CANDIDATE_DATASET_PATH),
        'catalogue_count': len(service.CANDIDATE_CATALOGUE),
        'models': [{'app_id': key[0], 'target': key[1], 'path': str(spec['path']),
                    'sha256': sha256(spec['path']), 'features': spec['features'],
                    'best_iteration': spec['best_iteration']}
                   for key, spec in sorted(service.MODELS.items())],
        'objective': {'lambda': service.LAMBDA, 'r_max': service.R_MAX,
                      'w_failure': service.W_FAILURE, 'w_service': service.W_SERVICE,
                      'hard_stability_environment': service.HARD_STABILITY_ENABLED},
        'normalization': support,
        'original_log_settings': ORIGINAL_LOG_SETTINGS,
        'measurement_note': ('Input app/path statistics are the Java reporting-window '
            'measurements, not finalized admission-cohort targets. Near a configuration '
            'change they may mix outcomes from earlier admissions. Diagnostic disk I/O '
            'adds wall-clock overhead; do not use this run to benchmark runtime.'),
    }
    (SESSION_DIR / 'metadata.json').write_text(json.dumps(value, indent=2), encoding='utf-8')


def _record(data, base, app_weights, candidates, scores, settings, optimizer_time_ms):
    churn = scores['reconfiguration_cost']
    perf = scores['performance_cost']
    joint = scores['joint_cost']
    feasible = churn <= float(settings['r_max']) + 1e-12 if settings['hard_stability_enabled'] else np.ones(len(candidates), dtype=bool)
    allowed = np.flatnonzero(feasible)
    current_vector = np.array([service._current_candidate(base)[c] for c in service.CANDIDATE_COLUMNS])
    match = np.flatnonzero(np.all(np.isclose(candidates[service.CANDIDATE_COLUMNS].to_numpy(), current_vector, rtol=0, atol=1e-9), axis=1))
    if len(match) != 1:
        raise ValueError('Could not identify exactly one current configuration')

    def detail(index):
        index = int(index)
        f = scores['failure_predictions'][index]
        d = scores['dnst_predictions'][index]
        return {
            'index': index,
            'configuration': {c: float(candidates.iloc[index][c]) for c in service.CANDIDATE_COLUMNS},
            'feasible': bool(feasible[index]),
            'performance_cost': float(perf[index]),
            'reconfiguration_cost': float(churn[index]),
            'joint_cost': float(joint[index]),
            'failure_predictions': [float(v) for v in f],
            'dnst_predictions': [float(v) for v in d],
            'weighted_failure': float(scores['weighted_failure'][index]),
            'weighted_dnst': float(scores['weighted_dnst'][index]),
            'failure_clipped_upper': [bool(v > service.TRAIN_FAILURE_MAX) for v in f],
            'dnst_clipped_upper': [bool(v > service.TRAIN_DNST_MAX) for v in d],
            'dnst_clipped_lower': [bool(v < service.TRAIN_DNST_MIN) for v in d],
        }

    feasible_joint_order = allowed[np.lexsort((churn[allowed], perf[allowed], joint[allowed]))]
    feasible_perf_order = allowed[np.lexsort((churn[allowed], perf[allowed]))]
    all_perf_order = np.lexsort((churn, perf))
    value = {
        'session': SESSION,
        'request': data,
        'constructed_state_features': {k: float(v) for k, v in base.items()},
        'app_weights': [float(v) for v in app_weights],
        'settings': settings,
        'candidate_count': len(candidates),
        'feasible_candidate_count': int(len(allowed)),
        'constraint_active': bool(scores['constraint_active']),
        'optimizer_time_ms_excluding_diagnostics': float(optimizer_time_ms),
        'current': detail(match[0]),
        'selected': detail(scores['best_index']),
        'unconstrained_joint_best': detail(scores['unconstrained_best_index']),
        'feasible_performance_best': detail(feasible_perf_order[0]),
        'unconstrained_performance_best': detail(all_perf_order[0]),
        'top10_feasible_joint': [detail(i) for i in feasible_joint_order[:10]],
        'top10_feasible_performance': [detail(i) for i in feasible_perf_order[:10]],
        'returned_configuration': service._response_string(candidates.iloc[scores['best_index']]),
    }
    # Use the original naming function inside this unique session directory.
    name = service._decision_log_path(data, settings['variant']).with_suffix('.jsonl').name
    line = json.dumps(value, allow_nan=False, separators=(',', ':'))
    with LOCK:
        with (SESSION_DIR / name).open('a', encoding='utf-8') as stream:
            stream.write(line + '\n')


def diagnostic_write(*args, **kwargs):
    ORIGINAL_WRITE(*args, **kwargs)
    try:
        _record(*args, **kwargs)
    except Exception:
        # An additional diagnostic failure must not change the original response.
        service.logger.exception('Extra diagnostic write failed; original decision preserved')


service._write_decision_log = diagnostic_write
write_metadata()
service.logger.info('DIAGNOSTIC OUTPUT: %s', SESSION_DIR)

if __name__ == '__main__':
    service.app.run(host='0.0.0.0', port=service.PORT)
