#!/usr/bin/env python3
"""Frozen v5 confirmation: prepare, run, status, stop, package.

Reuses ready pilot models and compatible static calibration. Owns its Java/Flask
children; keeps immutable completed jobs and separate interrupted attempts.
"""
from __future__ import annotations
import argparse
from contextlib import contextmanager
import csv
from datetime import datetime, timezone
import fcntl
import json
import math
import os
from pathlib import Path
import re
import shutil
import signal
import socket
import subprocess
import sys
import time
import urllib.request
import zipfile

import run_deadline_pilot as core
import run_lambda_check as calibration
import confirmatory_reports as reports

BASE=Path(__file__).resolve().parent
REPO=BASE.parent
WORKFLOW='scope_confirmatory_v1'
CODE=['run_confirmatory_study.py','confirmatory_reports.py','run_deadline_pilot.py',
      'run_lambda_check.py','scope_lambda_service.py']
MAIN=['SCOPE','AI_BASED','EXP3_MC','RAIDER_TRAX','RANDOM','SCOPE_STATIC']
ABLATIONS=['HARD_ONLY','SOFTCOST_OPT','PERFORMANCE_ONLY']
ADAPTATION=['SCOPE','SCOPE_FROZEN','SCOPE_STATIC',*ABLATIONS,'AI_BASED']
SCALES=[.9,.8,.8,.8,75.,75.,75.]


def protocol(profile):
    smoke=profile=='smoke'
    return dict(workflow=WORKFLOW,profile=profile,routing_schema=core.SCHEMA,
        purpose='workflow validation only' if smoke else 'independent confirmation after development calibration',
        iterations=[3491] if smoke else list(range(3401,3411)),
        loads=[900,1800] if smoke else [600,900,1200,1500,1800],
        minutes=10 if smoke else 60,warmup_minutes=3,lambda_value=.01,r_max=.15,
        main_policies=MAIN,ablation_policies=ABLATIONS,ablation_load=1800,
        adaptation_policies=ADAPTATION,adaptation_load=900 if smoke else 1200,
        shift_seconds=360 if smoke else 1200,recovery_seconds=480 if smoke else 2400,rate_multiplier=1.5,
        tuning_iterations=[3291] if smoke else [3201,3202],static_shortlist_size=4,
        static_selection='training-ranked shortlist plus initial; mean .5 normalized failure + .5 normalized deadline-relative service on calibration seeds; ties by shortlist index',
        parameter_selection='lambda 0.01 fixed after separate development calibration 3301-3303; Rmax 0.15 unchanged; never tune on confirmation seeds',
        exp3=dict(arm_count=0,qos_threshold=.20,arm_selection_seed=20260828,seed_offset=300007),
        inference=dict(primary_metrics=['failure_pct','service_seconds'],
            intervals='two-sided 95% t intervals across independent simulation seeds; paired intervals for differences',
            families='Holm adjustment separately for main comparisons (SCOPE vs each other policy at every load, both metrics), ablations (three contrasts, both metrics), and adaptation (SCOPE vs matched frozen, both metrics)',
            secondary='QoE, processing/network delay, utilization, movement and phase plots are descriptive/exploratory',
            stopping='Complete every registered seed and retain all outcomes; interruption is resumable and is not a statistical stopping rule'))


def spec(group,label,n,i,**extra):
    policy='SCOPE' if label in ['HARD_ONLY','SCOPE_FROZEN'] else label
    return dict(key=f'{group}_{label}_i{i}_n{n}',group=group,label=label,policy=policy,load=n,iteration=i,**extra)


def evaluation_specs(plan):
    jobs=[]
    for i in plan['iterations']:
        for n in plan['loads']:
            jobs.extend(spec('main',p,n,i) for p in plan['main_policies'])
        jobs.extend(spec('ablation',p,plan['ablation_load'],i) for p in plan['ablation_policies'])
        jobs.extend(spec('adaptation',p,plan['adaptation_load'],i) for p in plan['adaptation_policies'])
    return jobs


def tuning_specs(plan):
    return [dict(spec('calibration','SCOPE_STATIC',n,i,candidate=c),
                 key=f'tune_c{c}_i{i}_n{n}',static=values)
            for n in plan['loads'] for c,values in enumerate(plan['shortlist'][str(n)]) for i in plan['tuning_iterations']]


def load_plan(out):
    p=core.read(out/'study.json')
    core.require(p.get('workflow')==WORKFLOW,'This is not a confirmatory-study folder')
    core.require((out/'study_checksum.txt').read_text().strip()==core.sha(out/'study.json'),
                 'Registered protocol changed; preserve it and use a new output')
    return p


def validate(out,plan):
    core.require(plan['output']==str(out),'Resume in the original output location')
    core.require(core.versions()==plan['package_versions'],'Python package versions changed')
    core.verify(BASE,plan['runner_hashes']);core.verify(out,plan['input_hashes'])


def choose_shortlist(out,plan):
    import pandas as pd
    support=core.read(out/'models/model_manifest.json')['normalization']
    frame=pd.read_csv(out/'dataset/candidate_dataset_train.csv')
    frame['screen_score']=.5*((frame.target_failure_rate-support['failure_min'])/(support['failure_max']-support['failure_min'])).clip(0,1)+.5*((frame.target_deadline_norm_service_time-support['dnst_min'])/(support['dnst_max']-support['dnst_min'])).clip(0,1)
    result={}
    for n in plan['loads']:
        ranked=frame[frame.num_devices==n].groupby(core.COLS,sort=True).screen_score.mean().sort_values(kind='stable')
        choices=[core.INITIAL]
        for row in ranked.index:
            values=[round(float(x),12) for x in row]
            if all(distance(values,c)>=.05 for c in choices):choices.append(values)
            if len(choices)==plan['static_shortlist_size']:break
        core.require(len(choices)>=2,'Insufficient training coverage for static calibration at '+str(n))
        result[str(n)]=choices
    return result


def prepare(out,args):
    if (out/'study.json').exists():
        plan=load_plan(out);validate(out,plan)
        core.require(args.profile is None or args.profile==plan['profile'],'Profile mismatch')
        print('Already prepared: '+str(out));return
    core.require(not any(p.name!='.runner.lock' for p in out.iterdir()),'Partial preparation retained; use a new --output')
    source=args.source_study.expanduser().resolve();calibration.check_location(source,out)
    with (source/'.runner.lock').open('r') as lock:
        try:fcntl.flock(lock,fcntl.LOCK_SH|fcntl.LOCK_NB)
        except BlockingIOError:raise RuntimeError('Stop the source pilot before importing it')
        old=core.load_plan(source);core.verify(source,old['input_hashes'])
        models,dataset=core.check_models(source,False)
        core.require(core.versions()==old['package_versions'],'Use the Python environment that trained these models')
        plan=protocol(args.profile or 'full')
        used=set(old['collection_iterations']+old['tuning_iterations']+old['pilot_iterations']+[3301,3302,3303,3391]+list(range(2001,2011)))
        core.require(not set(plan['iterations']) & used,'Confirmation iterations overlap development')
        core.require(not set(plan['iterations']) & set(plan['tuning_iterations']),'Calibration/confirmation overlap')
        core.write(out/'preparing.json',dict(source=str(source),workflow=WORKFLOW))
        for name in ['src','classes','lib','services']:
            shutil.copytree(source/'runtime'/name,out/'runtime'/name,ignore=shutil.ignore_patterns('__pycache__'))
        shutil.copytree(source/'inputs',out/'inputs')
        shutil.copytree(models,out/'models');shutil.copytree(dataset,out/'dataset')
        provenance=out/'source_provenance';provenance.mkdir()
        for name in ['study.json','study_checksum.txt']:shutil.copy2(source/name,provenance/name)
        shutil.copy2(source/'jobs/train/complete.json',provenance/'training_receipt.json')
        plan['shortlist']=choose_shortlist(out,plan)
        imported=[]
        if plan['profile']=='full' and (source/'static_shortlist.json').exists():
            core.require(old['minutes']==plan['minutes'] and old['warmup_minutes']==plan['warmup_minutes']
                         and old['tuning_iterations']==plan['tuning_iterations'],'Source calibration protocol differs')
            core.require((source/'static_shortlist_checksum.txt').read_text().strip()==core.sha(source/'static_shortlist.json'),
                         'Source static shortlist was changed')
            prior=core.read(source/'static_shortlist.json')
            for n,choices in prior.items():
                if n in plan['shortlist']:core.require(choices==plan['shortlist'][n],'Training shortlist differs at '+n)
            for job in tuning_specs(plan):
                if str(job['load']) not in prior:continue
                receipt=core.complete(source,job['key'])
                if receipt is None:continue
                folder=source/receipt['attempt']
                old_result=receipt['result']
                core.require(old_result['policy']=='SCOPE_STATIC' and old_result['load']==job['load'] and
                             old_result['iteration']==job['iteration'] and not old_result['burst'],'Invalid source calibration identity')
                verify_static(folder/'static.txt',job['static'])
                target=provenance/'calibration'
                shutil.copytree(folder,target/receipt['attempt'],ignore=shutil.ignore_patterns('weka','__pycache__'))
                dest=target/'jobs'/job['key'];shutil.copy2(source/'jobs'/job['key']/'complete.json',dest/'complete.json')
                core.complete(target,job['key']);imported.append(job['key'])
        plan.update(source_study=str(source),source_study_sha=core.sha(source/'study.json'),
                    source_training_receipt_sha=core.sha(source/'jobs/train/complete.json'),imported_calibration_jobs=imported)
    for name in CODE:shutil.copy2(BASE/name,out/'runtime/services'/name)
    shutil.copytree(BASE/'confirmatory_matlab',out/'matlab')
    shutil.copytree(BASE/'confirmatory_matlab',out/'inputs/confirmatory_matlab')
    plan.update(java=core.select_java(args.java),python=sys.executable,package_versions=core.versions(),
                output=str(out),created=datetime.now(timezone.utc).isoformat(),runner_hashes={n:core.sha(BASE/n) for n in CODE})
    try:plan['git_head']=subprocess.check_output(['git','rev-parse','HEAD'],cwd=REPO,text=True).strip()
    except (OSError,subprocess.CalledProcessError):plan['git_head']='unknown'
    e=service_environment(out,out/'preflight',plan,spec('main','SCOPE',plan['loads'][0],plan['iterations'][0]))
    core.managed([sys.executable,'-c','import ml_optimizer_service as s; import exp3_mc_service as e; assert len(s.MODELS)==6; assert s.NORMALIZATION==e.NORMALIZATION; print("Ready models and matched EXP3 normalization verified")'],
                 out/'preflight.log',out,cwd=out/'runtime/services',environ=e)
    for port in [5002,5003]:free_port(port)
    plan['input_hashes']={str(p.relative_to(out)):core.sha(p) for d in ['runtime','inputs','models','dataset','source_provenance']
                          for p in (out/d).rglob('*') if p.is_file() and '__pycache__' not in p.parts}
    core.write(out/'study.json',plan);(out/'study_checksum.txt').write_text(core.sha(out/'study.json')+'\n')
    print(f"PREPARED: {len(evaluation_specs(plan))} evaluation scenarios; no retraining.\n"
          f"Static calibration: {len(imported)}/{len(tuning_specs(plan))} reused; {len(tuning_specs(plan))-len(imported)} remain.\n{out}",flush=True)


def distance(a,b):return sum(abs(x-y)/s for x,y,s in zip(a,b,SCALES))/7


def verify_static(path,expected):
    parts=path.read_text().strip().split('|')
    observed=[float(parts[0].split(':')[1])]+[float(p.split(':')[1]) for p in parts[1:]]+[float(p.split(':')[3]) for p in parts[1:]]
    core.require(len(observed)==7 and all(abs(a-b)<=1e-12 for a,b in zip(observed,expected)),'Static configuration differs')


def service_environment(out,folder,plan,job):
    lam=0. if job['label']=='HARD_ONLY' else plan['lambda_value']
    freeze=plan['shift_seconds'] if job['label']=='SCOPE_FROZEN' else None
    e=calibration.service_env(out,folder,lam,freeze)
    e.update(EXP3_MC_CANDIDATE_DATASET=str(out/'dataset/candidate_dataset_train.csv'),
        EXP3_MC_NORMALIZATION_MANIFEST=str(out/'models/model_manifest.json'),EXP3_MC_RESULTS_DIR=str(folder/'exp3'),
        EXP3_MC_EXPERIMENT_ID=job['key'],EXP3_MC_PORT='5003',EXP3_MC_ARM_COUNT=str(plan['exp3']['arm_count']),
        EXP3_MC_QOS_THRESHOLD=str(plan['exp3']['qos_threshold']),EXP3_MC_W_FAILURE='.5',EXP3_MC_W_SERVICE='.5',
        EXP3_MC_ARM_SELECTION_SEED=str(plan['exp3']['arm_selection_seed']),EXP3_MC_SEED_OFFSET=str(plan['exp3']['seed_offset']))
    return e


def free_port(port):
    with socket.socket() as s:
        s.setsockopt(socket.SOL_SOCKET,socket.SO_REUSEADDR,1)
        try:s.bind(('127.0.0.1',port))
        except OSError as e:raise RuntimeError(f'Port {port} is occupied. Stop the old service; it will not be killed.') from e


@contextmanager
def service(out,folder,plan,job):
    policy=job['policy'];server=None
    if policy not in ['SCOPE','SOFTCOST_OPT','PERFORMANCE_ONLY','EXP3_MC']:
        yield None;return
    port=5003 if policy=='EXP3_MC' else 5002;free_port(port)
    script='exp3_mc_service.py' if port==5003 else ('scope_lambda_service.py' if policy=='SCOPE' else 'scope_diagnostic_service.py')
    with (folder/'service.log').open('w') as log:
        try:
            server=subprocess.Popen([sys.executable,'-u',str(out/'runtime/services'/script)],cwd=out/'runtime/services',
                env=service_environment(out,folder,plan,job),stdout=log,stderr=log,start_new_session=True)
            end=time.monotonic()+60
            while True:
                core.check_stop(out);core.require(server.poll() is None,'Service exited: '+str(folder/'service.log'))
                try:
                    with urllib.request.urlopen(f'http://127.0.0.1:{port}/health',timeout=1) as response:h=json.load(response)
                except (OSError,ValueError):
                    core.require(time.monotonic()<end,'Service readiness timeout');time.sleep(.2);continue
                support=core.read(out/'models/model_manifest.json')['normalization']
                core.require(h['routing_schema']==core.SCHEMA and h['normalization']==support,'Service schema/normalization differs')
                if port==5002:
                    lam=0. if job['label']=='HARD_ONLY' else plan['lambda_value']
                    core.require(h['lambda']==lam and h['r_max']==plan['r_max'] and h['hard_stability_enabled'],'Scope service settings differ')
                    if policy=='SCOPE':core.require(h.get('lambda_check_wrapper')==1 and h.get('freeze_after_seconds')==(plan['shift_seconds'] if job['label']=='SCOPE_FROZEN' else None),'Freeze service differs')
                else:
                    core.require(h['arm_count']==0 and h['qos_threshold']==.2 and h['eta_override'] is None and
                                 h['arm_selection_seed']==plan['exp3']['arm_selection_seed'],'EXP3 settings differ')
                core.write(folder/'health.json',h);break
            yield server
        finally:core.terminate(server)


def read_metrics(path):
    m=core.generic(path);lines=path.read_text().splitlines()
    for index,tier in [(2,'edge'),(3,'cloud')]:
        value=float(lines[index].split(';')[7]);core.require(math.isfinite(value) and value>=0,'Invalid VM utilization')
        m[tier+'_utilization_pct']=value
    return m


def validate_decisions(folder,plan,job):
    records=calibration.decision_records(folder);times=list(range(70,plan['minutes']*60,60));policy=job['policy']
    rows=[];previous=None;held=None
    if policy in ['SCOPE','SOFTCOST_OPT','PERFORMANCE_ONLY']:
        core.require([r['request']['timestamp'] for r in records]==times,'Missing or mistimed optimizer decisions')
        hard=policy=='SCOPE';lam=0. if job['label'] in ['HARD_ONLY','PERFORMANCE_ONLY'] else plan['lambda_value']
        for r in records:
            q=r['request'];settings=r['settings'];a=[r['current']['configuration'][k] for k in core.COLS];b=[r['selected']['configuration'][k] for k in core.COLS]
            core.require(q['iteration']==job['iteration'] and q['num_devices']==job['load'] and q['policy']==policy and
                         q['routing_schema']==core.SCHEMA and q['telemetry_schema']=='vm_percent_all_vms_v1','Decision identity differs')
            core.require(settings['lambda']==lam and settings['hard_stability_enabled']==hard and settings['r_max']==plan['r_max'],'Ablation settings differ')
            if previous is not None:core.require(all(abs(x-y)<=1e-9 for x,y in zip(a,previous)),'Java did not apply preceding action')
            move=distance(a,b);core.require(abs(move-r['selected']['reconfiguration_cost'])<=1e-9,'Movement log differs')
            if hard:core.require(move<=plan['r_max']+1e-9,'Hard movement bound violated')
            if job['label']=='SCOPE_FROZEN':
                frozen=q['timestamp']>=plan['shift_seconds']
                core.require(settings.get('selection_mode')==('frozen' if frozen else 'adaptive'),'Wrong freeze state')
                if frozen:
                    if held is None:held=a
                    core.require(all(abs(x-y)<=1e-9 for x,y in zip(b,held)),'Frozen configuration moved')
            rows.append(dict(timestamp=q['timestamp'],movement=move,**dict(zip(core.COLS,b))));previous=b
    elif policy=='EXP3_MC':
        core.require(not records,'Unexpected SCOPE diagnostics for EXP3')
        files=list((folder/'exp3').glob('*.csv'));core.require(len(files)==1,'Missing/ambiguous EXP3 decisions')
        with files[0].open() as f:exp=list(csv.DictReader(f))
        core.require([float(r['timestamp']) for r in exp]==times,'Missing/mistimed EXP3 decisions')
        previous=core.INITIAL
        for r in exp:
            core.require(int(r['num_devices'])==job['load'] and r['experiment_id']==job['key'] and
                         r['feedback_protocol']=='admission_cohort_v1' and float(r['qos_threshold'])==.2,'EXP3 identity/feedback differs')
            b=[float(r['selected_'+k.removeprefix('candidate_')]) for k in core.COLS];move=distance(previous,b)
            core.require(abs(move-float(r['step_churn']))<=1e-9,'EXP3 applied-state/movement differs')
            rows.append(dict(timestamp=float(r['timestamp']),movement=move,**dict(zip(core.COLS,b))));previous=b
        core.require('Recovering current arm' not in (folder/'service.log').read_text(),'EXP3 current arm was not applied')
    else:core.require(not records,'Unexpected optimizer decisions for fixed/baseline policy')
    return rows


def inspect_run(folder,plan,job):
    log=(folder/'java.log').read_text();policy=job['policy']
    core.require(log.count('Scenario finished at ')==1 and 'Simulation finished at ' in log,'Incomplete Java scenario')
    core.require(not any(t in log for t in ['Exception','ERROR','unexpected error','Training-data write failed']),'Java error reported')
    if policy not in ['AI_BASED','RAIDER_TRAX','RANDOM']:core.require('ROUTING_SCHEMA='+core.SCHEMA in log,'Routing schema not applied')
    fingerprints=re.findall(r'WORKLOAD_AUDIT .*sha256=([a-f0-9]{64})',log)
    core.require(len(fingerprints)==1,'Missing workload audit')
    expected=0 if policy in ['RAIDER_TRAX','RANDOM'] else 3*len(range(70,plan['minutes']*60,60))
    core.require(len(core.parse_windows(log))==expected,'Reporting windows incomplete')
    metrics={a:read_metrics(folder/'java'/f'SIMRESULT_ITS_SCENARIO_{policy}_{job["load"]}DEVICES_{a}_GENERIC.log') for a in core.APPS}
    records=validate_decisions(folder,plan,job);moves=[r['movement'] for r in records]
    # Task-level baseline policies do not have this seven-parameter controller.
    applicable=policy not in ['AI_BASED','RAIDER_TRAX','RANDOM']
    return dict(spec=job,metrics=metrics,workload_sha256=fingerprints[0],decisions=records,
        total_movement=sum(moves) if applicable else None,max_step=max(moves,default=0) if applicable else None,
        changes=sum(m>1e-9 for m in moves) if applicable else None)


def saved_run(out,plan,job):
    r=core.complete(out,job['key'])
    if r:
        core.require(r['result']['spec']==job,'Completed job belongs to different settings');return out/r['attempt'],r['result']
    if job['key'] in plan['imported_calibration_jobs']:
        source=out/'source_provenance/calibration';r=core.complete(source,job['key'])
        core.require(r is not None,'Imported calibration receipt missing')
        folder=source/r['attempt'];verify_static(folder/'static.txt',job['static'])
        return folder,inspect_run(folder,plan,job)
    return None


def simulate(out,plan,job,fixed):
    saved=saved_run(out,plan,job)
    if saved:return saved
    core.check_stop(out);folder=core.attempt(out,job['key']);(folder/'java').mkdir()
    text=(out/'inputs/base.properties').read_text()
    values=dict(simulation_time=plan['minutes'],warm_up_period=plan['warmup_minutes'],min_number_of_mobile_devices=job['load'],
        max_number_of_mobile_devices=job['load'],mobile_device_counter_size=1,orchestrator_policies=job['policy'],file_log_enabled='true',deep_file_log_enabled='false')
    for k,v in values.items():
        pattern=r'(?m)^'+re.escape(k)+r'=.*$';text=re.sub(pattern,k+'='+str(v),text) if re.search(pattern,text) else text+'\n'+k+'='+str(v)+'\n'
    (folder/'config.properties').write_text(text);(folder/'weka').symlink_to(out/'inputs/weka',target_is_directory=True)
    cmd=[plan['java'],'-Xmx2g','-Dscope.optimizer.failFast=true','-Dscope.deadlineTierGuard=true','-Dscope.auditWorkload=true',
         '-Dscope.logPerformanceWindows=true','-Dscope.trainingData.path='+str(folder/'candidate_windows.csv')]
    if job['policy']=='SCOPE_STATIC':
        chosen=job['static'] if job['group']=='calibration' else fixed[str(job['load'])]
        (folder/'static.txt').write_text(core.wire(chosen));cmd+=['-Dscope.staticConfig='+str(folder/'static.txt')]
    if job['group']=='adaptation':cmd+=['-Dscope.workload.shiftSeconds='+str(plan['shift_seconds']),
        '-Dscope.workload.recoverySeconds='+str(plan['recovery_seconds']),'-Dscope.workload.rateMultiplier='+str(plan['rate_multiplier'])]
    cmd+=['-cp',core.cp(out),core.MAIN,str(folder/'config.properties'),str(out/'inputs/edge_devices.xml'),
          str(out/'inputs/applications.xml'),str(folder/'java'),str(job['iteration'])]
    core.write(folder/'command.json',cmd);core.write(folder/'settings.json',job)
    print('RUN '+job['key']+' | '+str(folder/'java.log'),flush=True)
    with service(out,folder,plan,job) as server:core.managed(cmd,folder/'java.log',out,cwd=out,environ=core.env(),peer=server)
    result=inspect_run(folder,plan,job);core.receipt(out,job['key'],folder,result)
    m=result['metrics']['ALL_APPS'];print(f"DONE {job['key']}: failures={m['failure_pct']:.4f}%, service={m['service_seconds']:.6f}s",flush=True)
    return folder,result


def select_static(out,plan):
    saved=core.complete(out,'select_static')
    if saved:return saved['result']['configurations']
    support=core.read(out/'models/model_manifest.json')['normalization'];deadlines=core.deadlines(out)
    scores=[];fingerprints={};chosen={}
    for n in plan['loads']:
        ranked=[]
        for c,values in enumerate(plan['shortlist'][str(n)]):
            results=[]
            for job in tuning_specs(plan):
                if job['load']!=n or job['candidate']!=c:continue
                _,r=simulate(out,plan,job,{})
                key=(n,job['iteration']);expected=fingerprints.setdefault(key,r['workload_sha256'])
                core.require(expected==r['workload_sha256'],'Calibration task streams differ')
                results.append(core.objective(r['metrics'],support,deadlines))
            score=sum(results)/len(results);ranked.append((score,c));scores.append(dict(load=n,candidate=c,score=score,values=values))
        chosen[str(n)]=plan['shortlist'][str(n)][min(ranked)[1]]
    folder=core.attempt(out,'select_static');core.write(folder/'selection.json',dict(configurations=chosen,scores=scores,criterion=plan['static_selection']))
    core.receipt(out,'select_static',folder,dict(configurations=chosen))
    print('Static controls frozen before confirmation.',flush=True);return chosen


def summarize(out,plan):
    completed=[];fingerprints={};pairs=[]
    for job in evaluation_specs(plan):
        saved=saved_run(out,plan,job)
        if saved is None:continue
        folder,result=saved
        # Re-parse complete evidence; the receipt already verified all file bytes.
        core.require(inspect_run(folder,plan,job)==result,'Completed evidence and result differ')
        case='burst' if job['group']=='adaptation' else 'steady';key=(case,job['iteration'],job['load'])
        expected=fingerprints.setdefault(key,result['workload_sha256'])
        core.require(expected==result['workload_sha256'],'Policy task streams differ')
        completed.append((folder,result))
        if job['label']=='SCOPE_FROZEN':
            active=spec('adaptation','SCOPE',job['load'],job['iteration']);a=core.complete(out,active['key']);f=core.complete(out,job['key'])
            core.require(a is not None,'Frozen control requires adaptive partner')
            proxy=dict(lambda_value=plan['lambda_value'],iteration=job['iteration'],load=job['load'])
            # Shared pair audit expects the old receipt result shape.
            ar=dict(a,result=dict(a['result'],workload_sha256=a['result']['workload_sha256']))
            pairs.append(calibration.paired_audit(out,plan,proxy,ar,f))
    reports.export(out,plan,completed,pairs,len(evaluation_specs(plan)))


def package(out,plan):
    summarize(out,plan)
    stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ');target=out.parent/(out.name+'_review_'+stamp+'.zip')
    with zipfile.ZipFile(target,'x',zipfile.ZIP_DEFLATED) as z:
        for p in sorted(out.rglob('*')):
            rel=p.relative_to(out)
            if not p.is_file() or p.is_symlink() or any(x in rel.parts for x in ['runtime','weka','__pycache__']) or p.name=='.runner.lock':continue
            z.write(p,Path(out.name)/rel)
        for name in CODE+['ml_optimizer_service.py','exp3_mc_service.py','scope_diagnostic_service.py','scope_objective.py']:
            z.write(out/'runtime/services'/name,Path(out.name)/'code'/name)
    print('Review ZIP: '+str(target),flush=True)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('stage',choices=['prepare','run','status','stop','package'])
    p.add_argument('--source-study',type=Path,default=REPO/'ThreeBrains/sim_results/v5_deadline_pilot')
    p.add_argument('--output',type=Path,default=REPO/'ThreeBrains/sim_results/v5_final_3401_3410')
    p.add_argument('--profile',choices=['full','smoke']);p.add_argument('--java')
    p.add_argument('--iteration',type=int,help='Run one registered iteration; full run later skips it. Never selects settings.')
    args=p.parse_args();out=args.output.expanduser().resolve()
    if args.stage in ['stop','status']:
        plan=load_plan(out)
        if args.stage=='stop':(out/'STOP_REQUESTED').touch();print('Stop requested. Wait for cleanup before resuming.')
        else:print(f"Evaluation receipts: {sum((out/'jobs'/j['key']/'complete.json').exists() for j in evaluation_specs(plan))}/{len(evaluation_specs(plan))}\n{out}")
        return
    core.require(args.iteration is None or args.stage=='run','--iteration is only valid for run')
    if args.stage=='prepare':calibration.check_location(args.source_study.expanduser().resolve(),out);out.mkdir(parents=True,exist_ok=True)
    core.require(out.is_dir(),'Run prepare first')
    signal.signal(signal.SIGINT,core.signal_stop);signal.signal(signal.SIGTERM,core.signal_stop)
    with (out/'.runner.lock').open('a+') as lock:
        try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:raise RuntimeError('Another runner owns this output')
        (out/'STOP_REQUESTED').unlink(missing_ok=True)
        try:
            if args.stage=='prepare':prepare(out,args);return
            plan=load_plan(out);validate(out,plan)
            core.require(args.profile is None or args.profile==plan['profile'],'Profile mismatch')
            if args.stage=='package':package(out,plan);return
            core.require(args.iteration is None or args.iteration in plan['iterations'],'Iteration not in registered protocol')
            fixed=select_static(out,plan);jobs=evaluation_specs(plan)
            for job in jobs:
                if args.iteration is not None and job['iteration']!=args.iteration:continue
                core.check_stop(out)
                if job['label']=='SCOPE_FROZEN':core.require(core.complete(out,spec('adaptation','SCOPE',job['load'],job['iteration'])['key']) is not None,'Adaptive partner missing')
                simulate(out,plan,job,fixed)
            summarize(out,plan)
        except core.Stopped:
            print('STOPPED safely. Completed jobs retained; repeat run to resume.',flush=True);raise SystemExit(130)


if __name__=='__main__':main()
