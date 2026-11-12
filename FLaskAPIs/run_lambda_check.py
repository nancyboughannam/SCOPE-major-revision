#!/usr/bin/env python3
"""Separate, resumable lambda calibration using the completed v5 training job.

No collection or retraining. Copies frozen source inputs and models into a NEW
output. All lambda values keep Rmax=0.15. Frozen controls follow SCOPE until the
workload shift and then hold its last configuration. Ctrl+C stops owned children.
"""
from __future__ import annotations
import argparse
import csv
from datetime import datetime,timezone
import fcntl
import json
import math
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import sys
import time
import urllib.request
import zipfile

import run_deadline_pilot as core

BASE=Path(__file__).resolve().parent
REPO=BASE.parent
WORKFLOW='scope_lambda_check_v1'
LAMBDA_VALUES=[0.,.01,.05]
CODE_FILES=['run_lambda_check.py','run_deadline_pilot.py','scope_lambda_service.py']


def protocol(profile):
    return dict(workflow=WORKFLOW,profile=profile,purpose='development calibration; retain all settings and use fresh final-study seeds',
        lambdas=LAMBDA_VALUES,r_max=.15,iterations=[3391] if profile=='smoke' else [3301,3302,3303],
        minutes=10 if profile=='smoke' else 60,warmup_minutes=3,steady_load=1800,burst_load=1200,
        shift_seconds=360 if profile=='smoke' else 1200,recovery_seconds=480 if profile=='smoke' else 2400,
        rate_multiplier=1.5,routing_schema=core.SCHEMA,
        selection_rule='Report paired failures, completed-task service, QoE and configuration movement for every lambda. No automatic winner or lambda-specific objective ranking. Freeze the chosen tradeoff before fresh confirmatory seeds.',
        phase_rule='Outcome-time windows fully inside each phase and after warmup; exclude crossing windows. Not admission cohorts or independent replicates.')


def job_specs(plan):
    jobs=[]
    for iteration in plan['iterations']:
        for value in plan['lambdas']:
            token=format(value,'.2f').replace('.','p')
            for case,variant,load in [('steady','adaptive',plan['steady_load']),('burst','adaptive',plan['burst_load']),('burst','frozen',plan['burst_load'])]:
                jobs.append(dict(key=f'{case}_l{token}_{variant}_i{iteration}_n{load}',
                                 case=case,variant=variant,load=load,iteration=iteration,lambda_value=value))
    return jobs


def check_location(source,out):
    core.require(source!=out and source not in out.parents and out not in source.parents,
                 'Source and output must be separate, non-nested directories')


def load_plan(out):
    plan=core.read(out/'study.json')
    core.require(plan.get('workflow')==WORKFLOW,'This is not a lambda-check output directory')
    core.require((out/'study_checksum.txt').is_file() and (out/'study_checksum.txt').read_text().strip()==core.sha(out/'study.json'),
                 'Registered settings changed; preserve this output and use a new directory')
    return plan


def validate_runtime(out,plan):
    core.require(plan['output']==str(out),'Resume in the original output location')
    core.require(core.versions()==plan['package_versions'],'Python dependency versions changed')
    core.verify(BASE,plan['runner_hashes']);core.verify(out,plan['input_hashes'])


def prepare(out,args):
    if (out/'study.json').exists():
        plan=load_plan(out);validate_runtime(out,plan)
        core.require(args.profile is None or args.profile==plan['profile'],'Profile differs from the registered study')
        print('Already prepared: '+str(out),flush=True);return
    core.require(not any(p.name!='.runner.lock' for p in out.iterdir()),
                 'Partial preparation is preserved. Use a new empty --output directory.')
    source=args.source_study.expanduser().resolve();check_location(source,out)
    # Shared lock prevents copying while the original pilot is writing. Nothing
    # is created or overwritten in the source directory, including its lock.
    with (source/'.runner.lock').open('r') as lock:
        try:fcntl.flock(lock,fcntl.LOCK_SH|fcntl.LOCK_NB)
        except BlockingIOError:raise RuntimeError('Stop the source pilot before importing its frozen training job')
        source_plan=core.load_plan(source)
        core.verify(source,source_plan['input_hashes'])
        models,dataset=core.check_models(source,False)
        core.require(core.versions()==source_plan['package_versions'],'Use the Python environment that trained the source models')
        plan=protocol(args.profile or 'pilot')
        used=set(source_plan['collection_iterations']+source_plan['tuning_iterations']+source_plan['pilot_iterations'])
        core.require(not used.intersection(plan['iterations']),'Calibration seeds overlap the source study')
        core.write(out/'preparing.json',dict(workflow=WORKFLOW,source=str(source)))
        runtime=out/'runtime';runtime.mkdir()
        for name in ['src','classes','lib','services']:
            shutil.copytree(source/'runtime'/name,runtime/name,ignore=shutil.ignore_patterns('__pycache__'))
        shutil.copytree(source/'inputs',out/'inputs')
        shutil.copytree(models,out/'models');shutil.copytree(dataset,out/'dataset')
        provenance=out/'source_provenance';provenance.mkdir()
        for name in ['study.json','study_checksum.txt']:
            shutil.copy2(source/name,provenance/name)
        shutil.copy2(source/'jobs/train/complete.json',provenance/'training_receipt.json')
        plan.update(source_study=str(source),source_study_sha=core.sha(source/'study.json'),
                    source_training_receipt_sha=core.sha(source/'jobs/train/complete.json'))
    core.check_stop(out)
    shutil.copy2(BASE/'scope_lambda_service.py',runtime/'services/scope_lambda_service.py')
    (runtime/'runner_sources').mkdir()
    for name in CODE_FILES:shutil.copy2(BASE/name,runtime/'runner_sources'/name)
    shutil.copytree(BASE/'lambda_check_matlab',out/'matlab')
    shutil.copytree(BASE/'lambda_check_matlab',out/'inputs/lambda_check_matlab')
    plan.update(java=core.select_java(args.java),python=sys.executable,package_versions=core.versions(),output=str(out),
                created=datetime.now(timezone.utc).isoformat(),runner_hashes={n:core.sha(BASE/n) for n in CODE_FILES})
    try:plan['commit']=subprocess.check_output(['git','rev-parse','HEAD'],cwd=REPO,text=True).strip()
    except (OSError,subprocess.CalledProcessError):plan['commit']='unknown'
    e=service_env(out,out/'preflight',0.,None)
    core.managed([sys.executable,'-c','import ml_optimizer_service as s; assert len(s.MODELS)==6; print("Six frozen models loaded")'],
                 out/'model_check.log',out,cwd=runtime/'services',environ=e)
    # Every copied file is byte-checked on resume. The original Java classes and
    # optimizer are used directly; no compilation or simulator patch is needed.
    plan['input_hashes']={str(p.relative_to(out)):core.sha(p) for name in ['runtime','inputs','models','dataset','source_provenance']
                          for p in (out/name).rglob('*') if p.is_file() and '__pycache__' not in p.parts}
    core.write(out/'study.json',plan);(out/'study_checksum.txt').write_text(core.sha(out/'study.json')+'\n')
    print(f'PREPARED: {len(job_specs(plan))} scenarios, no retraining. Source models and results retained.\n{out}',flush=True)


def service_env(out,folder,value,freeze):
    e=core.env();e.update(SCOPE_RESULTS_DIR=str(out/'models'),SCOPE_CANDIDATE_DATASET=str(out/'dataset/candidate_dataset_train.csv'),
        SCOPE_DIAGNOSTIC_DIR=str(folder/'diagnostics'),SCOPE_ABLATION_RESULTS_DIR=str(folder/'scope'),SCOPE_HARD_STABILITY='1',
        SCOPE_LAMBDA=str(value),SCOPE_R_MAX='.15',SCOPE_PORT='5002',SCOPE_W_FAILURE='.5',SCOPE_W_SERVICE='.5')
    if freeze is not None:e['SCOPE_FREEZE_AFTER_SECONDS']=str(freeze)
    return e


def decision_records(folder):
    rows=[json.loads(s) for p in (folder/'diagnostics').rglob('*.jsonl') for s in p.read_text().splitlines()]
    return sorted(rows,key=lambda r:r['request']['timestamp'])


def validate_decisions(records,plan,spec):
    times=list(range(70,plan['minutes']*60,60))
    core.require([r['request']['timestamp'] for r in records]==times,'Missing, repeated or mistimed decisions')
    freeze=plan['shift_seconds'] if spec['variant']=='frozen' else None
    frozen_vector=None;previous=None
    for r in records:
        q=r['request'];s=r['settings'];current=r['current']['configuration'];selected=r['selected']['configuration']
        core.require(q['policy']=='SCOPE' and q['iteration']==spec['iteration'] and q['num_devices']==spec['load'] and
                     q['routing_schema']==core.SCHEMA and q['telemetry_schema']=='vm_percent_all_vms_v1','Request identity/schema mismatch')
        core.require(s['lambda']==spec['lambda_value'] and s['hard_stability_enabled'] and s['r_max']==plan['r_max'] and
                     s.get('freeze_after_seconds')==freeze,'Objective or control settings mismatch')
        if previous is not None:
            core.require(all(abs(current[k]-previous[k])<=1e-9 for k in core.COLS),'Java did not apply the preceding decision')
        movement=sum(abs(selected[k]-current[k])/scale for k,scale in zip(core.COLS,[.9,.8,.8,.8,75,75,75]))/7
        core.require(abs(movement-r['selected']['reconfiguration_cost'])<=1e-9 and movement<=plan['r_max']+1e-9,'Reconfiguration bound or telemetry mismatch')
        should_freeze=freeze is not None and q['timestamp']>=freeze
        core.require(s.get('selection_mode')==('frozen' if should_freeze else 'adaptive'),'Freeze state mismatch')
        if should_freeze:
            if frozen_vector is None:frozen_vector=current
            core.require(all(abs(selected[k]-frozen_vector[k])<=1e-9 for k in core.COLS),'Frozen configuration moved')
        previous=selected


def simulate(out,plan,spec):
    saved=core.complete(out,spec['key'])
    if saved:
        core.require(saved['result']['spec']==spec,'Completed job belongs to different settings')
        return saved
    core.check_stop(out);core.port_available();folder=core.attempt(out,spec['key']);(folder/'java').mkdir()
    settings=dict(simulation_time=plan['minutes'],warm_up_period=plan['warmup_minutes'],
        min_number_of_mobile_devices=spec['load'],max_number_of_mobile_devices=spec['load'],mobile_device_counter_size=1,
        orchestrator_policies='SCOPE',file_log_enabled='true',deep_file_log_enabled='false')
    text=(out/'inputs/base.properties').read_text()
    for k,v in settings.items():
        pattern=r'(?m)^'+re.escape(k)+r'=.*$'
        text=re.sub(pattern,k+'='+str(v),text) if re.search(pattern,text) else text+'\n'+k+'='+str(v)+'\n'
    (folder/'config.properties').write_text(text);(folder/'weka').symlink_to(out/'inputs/weka',target_is_directory=True)
    cmd=[plan['java'],'-Xmx2g','-Dscope.optimizer.failFast=true','-Dscope.deadlineTierGuard=true','-Dscope.auditWorkload=true',
         '-Dscope.logPerformanceWindows=true','-Dscope.trainingData.path='+str(folder/'candidate_windows.csv')]
    if spec['case']=='burst':cmd+=['-Dscope.workload.shiftSeconds='+str(plan['shift_seconds']),
        '-Dscope.workload.recoverySeconds='+str(plan['recovery_seconds']),'-Dscope.workload.rateMultiplier='+str(plan['rate_multiplier'])]
    cmd+=['-cp',core.cp(out),core.MAIN,str(folder/'config.properties'),str(out/'inputs/edge_devices.xml'),
          str(out/'inputs/applications.xml'),str(folder/'java'),str(spec['iteration'])]
    core.write(folder/'command.json',cmd);core.write(folder/'settings.json',spec)
    freeze=plan['shift_seconds'] if spec['variant']=='frozen' else None
    print('RUN '+spec['key']+' | '+str(folder/'java.log'),flush=True)
    server=None
    with (folder/'service.log').open('w') as log:
        try:
            server=subprocess.Popen([sys.executable,'-u',str(out/'runtime/services/scope_lambda_service.py')],
                cwd=out/'runtime/services',env=service_env(out,folder,spec['lambda_value'],freeze),stdout=log,stderr=log,start_new_session=True)
            end=time.monotonic()+60
            while True:
                core.check_stop(out);core.require(server.poll() is None,'Service exited; inspect '+str(folder/'service.log'))
                try:
                    with urllib.request.urlopen('http://127.0.0.1:5002/health',timeout=1) as h:health=json.load(h)
                except (OSError,ValueError):
                    core.require(time.monotonic()<end,'Service readiness timeout');time.sleep(.2);continue
                core.require(health['routing_schema']==core.SCHEMA and health['lambda']==spec['lambda_value'] and health['r_max']==plan['r_max'] and
                             health['hard_stability_enabled'] and health.get('lambda_check_wrapper')==1 and health.get('freeze_after_seconds')==freeze,
                             'Service settings mismatch')
                core.write(folder/'health.json',health);break
            core.managed(cmd,folder/'java.log',out,cwd=out,environ=core.env(),peer=server)
        finally:core.terminate(server)
    text=(folder/'java.log').read_text()
    core.require(text.count('Scenario finished at ')==1 and 'Simulation finished at ' in text,'Incomplete Java scenario')
    core.require(not any(s in text for s in ['Exception','ERROR','unexpected error','Training-data write failed']),'Java reported errors')
    fingerprints=re.findall(r'WORKLOAD_AUDIT .*sha256=([a-f0-9]{64})',text)
    core.require(len(fingerprints)==1 and 'ROUTING_SCHEMA='+core.SCHEMA in text,'Missing workload/routing audit')
    windows=core.parse_windows(text)
    core.require(len(windows)==3*len(range(70,plan['minutes']*60,60)),'Missing reporting windows')
    records=decision_records(folder);validate_decisions(records,plan,spec)
    metrics={a:core.generic(folder/'java'/f"SIMRESULT_ITS_SCENARIO_SCOPE_{spec['load']}DEVICES_{a}_GENERIC.log") for a in core.APPS}
    moves=[r['selected']['reconfiguration_cost'] for r in records]
    result=dict(spec=spec,metrics=metrics,workload_sha256=fingerprints[0],decisions=len(records),
                total_movement=sum(moves),max_step=max(moves,default=0),changes=sum(m>1e-9 for m in moves),
                change_times=[r['request']['timestamp'] for r in records if r['selected']['reconfiguration_cost']>1e-9])
    core.receipt(out,spec['key'],folder,result)
    m=metrics['ALL_APPS'];print(f"DONE {spec['key']}: failures={m['failure_pct']:.4f}%, service={m['service_seconds']:.6f}s, changes={result['changes']}",flush=True)
    return core.complete(out,spec['key'])


def paired_audit(out,plan,spec,active,frozen):
    core.require(active['result']['workload_sha256']==frozen['result']['workload_sha256'],'Paired workloads differ')
    a=decision_records(out/active['attempt']);f=decision_records(out/frozen['attempt'])
    first=next(i for i,r in enumerate(a) if r['request']['timestamp']>=plan['shift_seconds'])
    for i in range(first+1):
        core.require(a[i]['request']==f[i]['request'],'Frozen/adaptive histories differ before the intervention')
        if i<first:core.require(a[i]['returned_configuration']==f[i]['returned_configuration'],'Pre-freeze decisions differ')
    cutoff=a[first]['request']['timestamp']
    aw=core.parse_windows((out/active['attempt']/'java.log').read_text())
    fw=core.parse_windows((out/frozen['attempt']/'java.log').read_text())
    core.require([r for r in aw if r['window_end']<=cutoff]==[r for r in fw if r['window_end']<=cutoff],
                 'Pre-intervention reporting windows differ')
    return dict(lambda_value=spec['lambda_value'],iteration=spec['iteration'],load=spec['load'],
                workload_match=True,identical_history_through=cutoff,pre_intervention_requests=first+1,
                frozen_configuration=f[first]['current']['configuration'])


def write_csv(path,rows):
    if not rows:return
    with path.open('w',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)


def summarize(out,plan):
    rows=[];windows=[];decisions=[];pairs=[];saved={};fingerprints={}
    for spec in job_specs(plan):
        receipt=core.complete(out,spec['key'])
        if receipt is None:continue
        saved[spec['key']]=receipt;r=receipt['result'];core.require(r['spec']==spec,'Job identity changed')
        key=(spec['case'],spec['iteration'],spec['load']);fingerprint=fingerprints.setdefault(key,r['workload_sha256'])
        core.require(fingerprint==r['workload_sha256'],'Workloads differ across lambda settings')
        meta=dict(job=spec['key'],case=spec['case'],variant=spec['variant'],lambda_value=spec['lambda_value'],iteration=spec['iteration'],load=spec['load'])
        for app,m in r['metrics'].items():rows.append(dict(**meta,application=app,**m,total_movement=r['total_movement'],max_step=r['max_step'],changes=r['changes']))
        folder=out/receipt['attempt'];records=decision_records(folder);validate_decisions(records,plan,spec)
        for w in core.parse_windows((folder/'java.log').read_text()):windows.append(dict(**meta,**w))
        for d in records:
            decisions.append(dict(**meta,timestamp=d['request']['timestamp'],selection_mode=d['settings']['selection_mode'],
                movement=d['selected']['reconfiguration_cost'],feasible_candidates=d['feasible_candidate_count'],candidate_count=d['candidate_count'],
                **d['selected']['configuration']))
        if spec['variant']=='frozen':
            active_key=spec['key'].replace('_frozen_','_adaptive_')
            core.require(active_key in saved,'Frozen result requires its completed adaptive pair')
            pairs.append(paired_audit(out,plan,spec,saved[active_key],receipt))
    write_csv(out/'lambda_metrics.csv',rows);write_csv(out/'window_metrics.csv',windows);write_csv(out/'decision_metrics.csv',decisions)
    core.write(out/'pair_checks.json',pairs)
    # Aggregate within each seed first. Windows/apps are not independent runs.
    phases={}
    for r in windows:
        start,end=r['window_start'],r['window_end']
        phase=None
        if start>=plan['warmup_minutes']*60:
            if r['case']=='steady':phase='steady'
            elif end<=plan['shift_seconds']:phase='before'
            elif start>=plan['shift_seconds'] and end<=plan['recovery_seconds']:phase='burst'
            elif start>=plan['recovery_seconds']:phase='recovery'
        if phase is None:continue
        key=(r['job'],phase)
        if key not in phases:
            phases[key]={k:r[k] for k in ['job','case','variant','lambda_value','iteration','load']}
            phases[key].update(phase=phase,completed=0,failed=0,service_sum=0.,app_windows=0)
        a=phases[key];a['completed']+=r['Completed'];a['failed']+=r['Failed'];a['service_sum']+=r['Completed']*r['MeanService'];a['app_windows']+=1
    phase_rows=[]
    for a in phases.values():
        core.require(a['completed']>0 and a['completed']+a['failed']>0,'Empty finalized phase')
        a['failure_pct']=100*a['failed']/(a['completed']+a['failed']);a['service_seconds']=a.pop('service_sum')/a['completed'];phase_rows.append(a)
    write_csv(out/'phase_metrics.csv',phase_rows)
    core.write(out/'completion.json',dict(completed=len(saved),expected=len(job_specs(plan)),matched_pairs=len(pairs),
        complete=len(saved)==len(job_specs(plan)),note='Calibration only. No setting automatically chosen. Freeze selection before final-study seeds.'))
    print(f'Completed {len(saved)}/{len(job_specs(plan))}; verified {len(pairs)} adaptive/frozen pairs. Metrics: {out}',flush=True)


def package(out,plan):
    summarize(out,plan);stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    target=out.parent/(out.name+'_review_'+stamp+'.zip')
    with zipfile.ZipFile(target,'x',zipfile.ZIP_DEFLATED) as z:
        for p in sorted(out.rglob('*')):
            rel=p.relative_to(out)
            if not p.is_file() or p.is_symlink() or any(x in rel.parts for x in ['runtime','weka','__pycache__']) or p.name=='.runner.lock':continue
            z.write(p,Path(out.name)/rel)
        for name in CODE_FILES:z.write(out/'runtime/runner_sources'/name,Path(out.name)/'code/runner'/name)
        for name in ['ml_optimizer_service.py','scope_diagnostic_service.py','scope_objective.py']:
            z.write(out/'runtime/services'/name,Path(out.name)/'code/frozen_services'/name)
    print('Review ZIP: '+str(target),flush=True)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('stage',choices=['prepare','run','status','stop','package'])
    parser.add_argument('--source-study',type=Path,default=REPO/'ThreeBrains/sim_results/v5_deadline_pilot')
    parser.add_argument('--output',type=Path,default=REPO/'ThreeBrains/sim_results/v5_lambda_check')
    parser.add_argument('--profile',choices=['pilot','smoke']);parser.add_argument('--java')
    parser.add_argument('--job',help='Run exactly one registered job for diagnostics; other jobs remain pending.')
    args=parser.parse_args();out=args.output.expanduser().resolve()
    if args.stage=='stop':
        load_plan(out);(out/'STOP_REQUESTED').touch();print('Stop requested; wait for the owning runner to finish cleanup.');return
    if args.stage=='status':
        plan=load_plan(out);done=sum((out/'jobs'/s['key']/'complete.json').exists() for s in job_specs(plan))
        print(f'{done}/{len(job_specs(plan))} jobs have completion receipts. '+str(out));return
    core.require(args.job is None or args.stage=='run','--job is only valid for run')
    if args.stage=='prepare':
        check_location(args.source_study.expanduser().resolve(),out);out.mkdir(parents=True,exist_ok=True)
    core.require(out.is_dir(),'Run prepare first')
    signal.signal(signal.SIGINT,core.signal_stop);signal.signal(signal.SIGTERM,core.signal_stop)
    with (out/'.runner.lock').open('a+') as lock:
        try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:raise RuntimeError('Another runner owns this output')
        (out/'STOP_REQUESTED').unlink(missing_ok=True)
        try:
            if args.stage=='prepare':prepare(out,args);return
            plan=load_plan(out);validate_runtime(out,plan)
            core.require(args.profile is None or args.profile==plan['profile'],'Profile mismatch')
            if args.stage=='package':package(out,plan);return
            specs=job_specs(plan)
            if args.job:
                specs=[s for s in specs if s['key']==args.job];core.require(len(specs)==1,'Unknown job; use a key from the registered protocol')
            for spec in specs:
                core.check_stop(out)
                if spec['variant']=='frozen':
                    core.require(core.complete(out,spec['key'].replace('_frozen_','_adaptive_')) is not None,'Run the adaptive pair first')
                result=simulate(out,plan,spec)
                if spec['variant']=='frozen':
                    paired_audit(out,plan,spec,core.complete(out,spec['key'].replace('_frozen_','_adaptive_')),result)
            summarize(out,plan)
        except core.Stopped:
            print('STOPPED safely. Completed jobs retained. Repeat run to resume; the interrupted job gets a new attempt.',flush=True)
            raise SystemExit(130)


if __name__=='__main__':main()
