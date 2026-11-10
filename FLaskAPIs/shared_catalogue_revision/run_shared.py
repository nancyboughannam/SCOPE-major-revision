"""Shared-catalogue pilot using the existing, unmodified SCOPE services."""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sys

INITIAL = dict(zip(['candidate_alpha'] + [f'candidate_w_load_{i}' for i in range(3)] +
                   [f'candidate_threshold_{i}' for i in range(3)], [.6,.5,.7,.4,85.,80.,90.]))
COLUMNS = list(INITIAL)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load(project, policy):
    filename = 'ml_optimizer_service.py' if policy == 'scope' else 'exp3_mc_service.py'
    path = project / filename
    known = json.loads(Path(__file__).with_name('known_services.json').read_text())
    if sha(path) not in known[filename]:
        raise ValueError(f'{filename} differs from the reviewed versions. Share this file for review; do not overwrite it.')
    spec = importlib.util.spec_from_file_location('shared_pilot_' + policy, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def base_state(row=INITIAL):
    result = {'previous_alpha': row['candidate_alpha']}
    for i in range(3):
        result[f'previous_w_load_{i}'] = row[f'candidate_w_load_{i}']
        result[f'previous_threshold_{i}'] = row[f'candidate_threshold_{i}']
    return result


def members(frame):
    return set(map(tuple, frame[COLUMNS].astype(float).round(10).to_numpy()))


def prepare(project, experiment, count, seed):
    if experiment.exists():
        raise ValueError('Experiment directory already exists. Choose a fresh name.')
    if count < 2:
        raise ValueError('At least two candidates are required')
    dataset = project/'scope_candidate_dataset/candidate_dataset_train.csv'
    os.environ.update(EXP3_MC_CANDIDATE_DATASET=str(dataset), EXP3_MC_ARM_COUNT=str(count),
                      EXP3_MC_ARM_SELECTION_SEED=str(seed))
    service = load(project, 'exp3')
    frame = service._candidate_batch(INITIAL)
    if len(frame) != count:
        raise ValueError(f'Requested {count} choices, but the catalogue provides {len(frame)}')
    experiment.mkdir(parents=True)
    frame.to_csv(experiment/'catalogue.csv', index=False)
    manifest = {'count': count, 'selection_seed': seed, 'initial': INITIAL,
                'catalogue_file_sha256': sha(experiment/'catalogue.csv'),
                'source_dataset_sha256': sha(dataset),
                'selection_method': 'existing exp3_mc_service._candidate_batch',
                'note': 'Separate sizes are not guaranteed nested; K=5 preserves the original selection for this seed.'}
    (experiment/'catalogue_manifest.json').write_text(json.dumps(manifest, indent=2)+'\n')
    print(f'Prepared {count} shared choices in {experiment}')


def start(project, experiment, policy, check_only=False):
    import pandas as pd
    manifest = json.loads((experiment/'catalogue_manifest.json').read_text())
    csv_path = experiment/'catalogue.csv'
    if sha(csv_path) != manifest['catalogue_file_sha256']:
        raise ValueError('Catalogue changed since preparation')
    frame = pd.read_csv(csv_path)[COLUMNS].astype(float).round(10)
    count = manifest['count']
    if len(frame) != count or len(members(frame)) != count:
        raise ValueError('Invalid catalogue count or duplicate choices')
    output = experiment/policy
    os.environ.update(SCOPE_CANDIDATE_DATASET=str(csv_path), EXP3_MC_CANDIDATE_DATASET=str(csv_path),
        EXP3_MC_ARM_COUNT=str(count), EXP3_MC_ARM_SELECTION_SEED=str(manifest['selection_seed']),
        SCOPE_LAMBDA='.20', SCOPE_R_MAX='.15', SCOPE_HARD_STABILITY='1',
        SCOPE_W_FAILURE='.5', SCOPE_W_SERVICE='.5', SCOPE_PORT='5002',
        EXP3_MC_ETA='.10', EXP3_MC_QOS_THRESHOLD='.20', EXP3_MC_PORT='5003',
        EXP3_MC_W_FAILURE='.5', EXP3_MC_W_SERVICE='.5',
        SCOPE_RESULTS_DIR=str(project/'scope_candidate_xgboost_results'),
        SCOPE_ABLATION_RESULTS_DIR=str(output), EXP3_MC_RESULTS_DIR=str(output))
    for key in ['SCOPE_DECISION_LOG', 'EXP3_MC_DECISION_LOG', 'SCOPE_SHARED_CATALOGUE']:
        os.environ.pop(key, None)
    service = load(project, policy)
    actual = service._candidate_batch(base_state() if policy=='scope' else INITIAL)
    if members(actual) != members(frame):
        raise ValueError('Actual service choices differ from the shared catalogue')
    if policy=='scope' and members(service._candidate_batch(base_state(frame.iloc[-1]))) != members(frame):
        raise ValueError('Choices change when the current action changes')
    print(f'VERIFIED: {policy}, {count} identical allowed configurations', flush=True)
    if check_only:
        return service
    output.mkdir(exist_ok=False)
    metadata = dict(manifest, policy=policy, service_source_sha256=sha(service.__file__),
                    python=sys.version, health=service.app.test_client().get('/health').get_json())
    (output/'run_manifest.json').write_text(json.dumps(metadata, indent=2)+'\n')
    service.app.run(host='127.0.0.1', port=5002 if policy=='scope' else 5003, debug=False)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['prepare','check','scope','exp3'])
    parser.add_argument('--project', type=Path, default=Path(__file__).resolve().parent.parent)
    parser.add_argument('--experiment', type=Path, required=True)
    parser.add_argument('--count', type=int, default=5)
    parser.add_argument('--seed', type=int, default=20260828)
    args = parser.parse_args()
    project = args.project.expanduser().resolve()
    experiment = args.experiment.expanduser().resolve()
    if args.command=='prepare':
        prepare(project, experiment, args.count, args.seed)
    elif args.command=='check':
        for policy in ['scope','exp3']:
            start(project, experiment, policy, check_only=True)
    else:
        start(project, experiment, args.command)


if __name__=='__main__':
    main()
