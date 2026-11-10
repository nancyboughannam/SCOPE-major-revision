"""Run only the audited EXP3_MC against a preserved shared catalogue."""
import argparse
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import shutil
import sys
from datetime import datetime, timezone


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def prepare(catalogue_experiment, output, mode, eta_reference, port=5003):
    import pandas as pd
    if mode not in {'fixed','scaled_k5'} or not math.isfinite(eta_reference) or eta_reference<=0:
        raise ValueError('Choose fixed/scaled_k5 and a finite positive reference eta')
    if output.exists():
        raise ValueError('Output already exists. Use a fresh folder; do not delete previous results.')
    csv_path=catalogue_experiment/'catalogue.csv'
    manifest=json.loads((catalogue_experiment/'catalogue_manifest.json').read_text())
    if sha(csv_path)!=manifest['catalogue_file_sha256']:
        raise ValueError('Source catalogue checksum does not match its manifest')
    # Override relevant ambient settings explicitly; preserve unrelated settings.
    os.environ.update(EXP3_MC_CANDIDATE_DATASET=str(csv_path),
        EXP3_MC_ARM_COUNT=str(manifest['count']),
        EXP3_MC_ARM_SELECTION_SEED=str(manifest['selection_seed']),
        EXP3_MC_ETA=str(eta_reference),EXP3_MC_ETA_MODE=mode,
        EXP3_MC_QOS_THRESHOLD='.20',EXP3_MC_W_FAILURE='.5',EXP3_MC_W_SERVICE='.5',
        EXP3_MC_SEED_OFFSET='300007',EXP3_MC_PORT=str(port),
        EXP3_MC_RESULTS_DIR=str(output/'exp3'))
    os.environ.pop('EXP3_MC_DECISION_LOG',None)
    service_file=Path(__file__).with_name('service.py')
    spec=importlib.util.spec_from_file_location('exp3_feedback_audit_service',service_file)
    module=importlib.util.module_from_spec(spec);sys.modules[spec.name]=module;spec.loader.exec_module(module)
    frame=pd.read_csv(csv_path)[module.CANDIDATE_COLUMNS].astype(float).round(10)
    actual=module._candidate_batch(manifest['initial'])
    # Check row order as well as membership: seeded EXP3 selection depends on it.
    if len(frame)!=manifest['count'] or not actual.equals(frame.reset_index(drop=True)):
        raise ValueError('Loaded arms/order differ from the recorded shared catalogue')
    if len(frame.drop_duplicates())!=len(frame):
        raise ValueError('Duplicated configurations in catalogue')
    effective_eta=eta_reference if mode=='fixed' else eta_reference*5/len(frame)
    metadata=dict(manifest,algorithm_version=module.ALGORITHM_VERSION,
        eta_mode=mode,eta_reference=eta_reference,effective_eta=effective_eta,
        service_source_sha256=sha(service_file),launcher_source_sha256=sha(__file__),
        source_experiment=str(catalogue_experiment),python=sys.version,
        created_at_utc=datetime.now(timezone.utc).isoformat(),
        role='diagnostic_not_final_evaluation',
        health=module.app.test_client().get('/health').get_json())
    return module,metadata


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--catalogue-experiment',required=True,type=Path)
    p.add_argument('--output',required=True,type=Path)
    p.add_argument('--mode',choices=['fixed','scaled_k5'],required=True)
    p.add_argument('--eta-reference',type=float,default=.1)
    p.add_argument('--port',type=int,default=5003)
    p.add_argument('--check-only',action='store_true')
    args=p.parse_args()
    source=args.catalogue_experiment.expanduser().resolve();output=args.output.expanduser().resolve()
    service,metadata=prepare(source,output,args.mode,args.eta_reference,args.port)
    print(f"VERIFIED: {metadata['count']} shared arms, original order; "
          f"mode={args.mode}, effective eta={metadata['effective_eta']:.12g}",flush=True)
    if args.check_only: return
    # Refuse reuse; make a self-contained copy before serving any requests.
    output.mkdir(parents=True,exist_ok=False)
    (output/'exp3').mkdir()
    shutil.copy2(source/'catalogue.csv',output/'catalogue.csv')
    shutil.copy2(source/'catalogue_manifest.json',output/'catalogue_manifest.json')
    (output/'run_manifest.json').write_text(json.dumps(metadata,indent=2)+'\n')
    service.app.run(host='127.0.0.1',port=args.port,debug=False)

if __name__=='__main__': main()
