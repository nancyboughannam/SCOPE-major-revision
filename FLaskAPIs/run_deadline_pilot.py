#!/usr/bin/env python3
"""Reversible v5 development workflow. Owns Java/Flask processes; Ctrl+C stops both.

Stages: prepare -> collect -> train -> tune-static -> pilot -> adaptation.
Every job has immutable attempts and a completion receipt. Repeating a stage
verifies/skips complete jobs and retries interrupted jobs in NEW directories.
This is a development pilot, not a final publication-study launcher.
"""
from __future__ import annotations
import argparse
import csv
from datetime import datetime, timezone
import fcntl
import hashlib
import importlib.metadata
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

BASE = Path(__file__).resolve().parent
REPO = BASE.parent
SCHEMA = 'deadline_guard_v1'
MAIN = 'edu.boun.edgecloudsim.applications.sample_app5.VehicularMainApp'
APPS = ['ALL_APPS','TRAFFIC_MANAGEMENT','DANGER_ASSESSMENT','INFOTAINMENT']
POLICIES = ['SCOPE','SCOPE_STATIC','PERFORMANCE_ONLY','AI_BASED']
COLS = ['candidate_alpha']+[f'candidate_w_load_{i}' for i in range(3)]+[f'candidate_threshold_{i}' for i in range(3)]
INITIAL = [.6,.5,.7,.4,85.,80.,90.]
# The published v5 runner before the static-wire endpoint repair. Only this
# exact version may retain its frozen study through repair-static-wire.
STATIC_WIRE_BASE_SHA = 'e25a13e78028daac03eee690db0d34bcfb6a0c9f47c0999bef9d34199cc13b40'
STATIC_WIRE_REPAIR = Path('repairs/static_wire_v1')
STOP = False


class Stopped(RuntimeError): pass


def require(ok, message):
    if not ok: raise RuntimeError(message)


def sha(p):
    h = hashlib.sha256()
    with Path(p).open('rb') as f:
        for chunk in iter(lambda:f.read(1024*1024),b''): h.update(chunk)
    return h.hexdigest()


def write(p, data):
    p=Path(p);p.parent.mkdir(parents=True,exist_ok=True)
    tmp=p.with_name(p.name+'.tmp')
    tmp.write_text(json.dumps(data,indent=2,allow_nan=False)+'\n');tmp.replace(p)


def read(p): return json.loads(Path(p).read_text())


def versions():
    return {p:importlib.metadata.version(p) for p in ['Flask','numpy','pandas','xgboost','scikit-learn','scipy','matplotlib']}


def load_plan(out):
    p=read(out/'study.json')
    require(p.get('workflow')=='scope_deadline_pilot_v1','This folder is not owned by the deadline-pilot runner')
    require((out/'study_checksum.txt').is_file() and (out/'study_checksum.txt').read_text().strip()==sha(out/'study.json'),
            'Study settings changed or preparation incomplete; use a new output directory')
    return p


def env():
    e={k:v for k,v in os.environ.items() if not k.startswith(('SCOPE_','EXP3_MC_','RT_OPT_'))
       and k not in ['JAVA_TOOL_OPTIONS','JDK_JAVA_OPTIONS','_JAVA_OPTIONS']}
    e.update(PYTHONUNBUFFERED='1',OMP_NUM_THREADS='1',OPENBLAS_NUM_THREADS='1',MKL_NUM_THREADS='1',MPLBACKEND='Agg')
    return e


def signal_stop(signum, frame):
    global STOP
    STOP=True


def check_stop(out):
    if STOP or (out/'STOP_REQUESTED').exists(): raise Stopped('Stop requested')


def terminate(p):
    if p is None: return
    # Only our newly-created process group. Never kill a pre-existing service.
    try: os.killpg(p.pid, signal.SIGTERM)
    except ProcessLookupError: pass
    try: p.wait(timeout=5)
    except subprocess.TimeoutExpired:
        try: os.killpg(p.pid,signal.SIGKILL)
        except ProcessLookupError: pass
        p.wait()


def managed(cmd, log, out, cwd=None, environ=None, peer=None):
    check_stop(out)
    with Path(log).open('w') as f:
        p=subprocess.Popen(list(map(str,cmd)),cwd=cwd,env=environ or env(),stdout=f,stderr=f,start_new_session=True)
        try:
            while p.poll() is None:
                check_stop(out)
                if peer is not None: require(peer.poll() is None,'Optimizer exited; inspect service.log')
                time.sleep(.2)
            require(p.returncode==0,f'Command failed ({p.returncode}); inspect {log}')
        finally: terminate(p)


def select_java(explicit):
    choices=[explicit] if explicit else [str(Path(os.environ.get('JAVA_HOME','/missing'))/'bin/java'),
        '/Library/Java/JavaVirtualMachines/jdk-21.jdk/Contents/Home/bin/java',shutil.which('java')]
    for j in filter(None,choices):
        try:
            r=subprocess.run([j,'-m','jdk.compiler/com.sun.tools.javac.Main','-version'],
                             capture_output=True,text=True,timeout=15,env=env())
            v=re.search(r'javac\s+(\d+)',r.stdout+r.stderr)
            if r.returncode==0 and v and int(v[1])>=21: return str(Path(j).resolve())
        except (OSError,subprocess.TimeoutExpired): pass
    raise RuntimeError('JDK 21+ compiler required; use --java /path/to/bin/java')


def hashes(folder): return {str(p.relative_to(folder)):sha(p) for p in sorted(folder.rglob('*')) if p.is_file()}


def verify(folder, expected):
    for p,h in expected.items(): require((folder/p).is_file() and sha(folder/p)==h,f'Changed or missing file: {folder/p}')


def verify_runner(out,plan):
    current=sha(__file__)
    if current==plan['runner_sha']:return
    record=out/STATIC_WIRE_REPAIR/'repair.json'
    require(record.is_file(), 'Runner changed. For the published static-weight fix, run repair-static-wire first; otherwise prepare a new output.')
    r=read(record)
    require(r.get('repair')=='static_wire_v1' and
            r.get('original_runner_sha')==plan['runner_sha']==STATIC_WIRE_BASE_SHA and
            r.get('repaired_runner_sha')==current and
            r.get('study_sha')==sha(out/'study.json'),
            'Runner repair does not match this code and frozen study; do not edit its hashes')
    verify(out,{str(STATIC_WIRE_REPAIR/'run_deadline_pilot.py'):current})
    verify(out,r['preserved_hashes'])


def repair_static_wire(out,plan):
    """Register one serialization-only repair without rewriting study/checkpoints.

    main() holds the study lock and checks the original location/environment.
    The original frozen runner, Java, services, inputs and study checksum remain
    intact. A separate record binds the repaired runner to this exact study.
    """
    verify(out,plan['input_hashes'])
    if sha(__file__)==plan['runner_sha']:
        print('No repair needed: this study already uses the current runner.',flush=True);return
    folder=out/STATIC_WIRE_REPAIR
    if (folder/'repair.json').exists():
        verify_runner(out,plan)
        print('Static-wire repair already registered. Run all to resume.',flush=True);return
    require(plan['runner_sha']==STATIC_WIRE_BASE_SHA,
            'This repair only supports the original published deadline-pilot runner')
    original='runtime/services/run_deadline_pilot.py'
    require(plan['input_hashes'].get(original)==STATIC_WIRE_BASE_SHA and
            sha(out/original)==STATIC_WIRE_BASE_SHA,'Original frozen runner is missing or changed')
    preserved=[out/'study.json',out/'study_checksum.txt']
    jobs=sorted((out/'jobs').glob('*/complete.json'))
    for p in jobs:
        check_stop(out);complete(out,p.parent.name);preserved.append(p)
    shortlist_file=out/'static_shortlist.json'
    if shortlist_file.exists():
        checksum=out/'static_shortlist_checksum.txt'
        require(checksum.is_file() and checksum.read_text().strip()==sha(shortlist_file),
                'Static shortlist changed after registration')
        preserved.extend([shortlist_file,checksum])
    check_stop(out)
    folder.mkdir(parents=True,exist_ok=True)
    snapshot=folder/'run_deadline_pilot.py'
    if snapshot.exists():require(sha(snapshot)==sha(__file__),'Incomplete repair contains a different runner')
    else:
        # An interrupted copy is safe to repeat; the atomic record is the commit.
        tmp=snapshot.with_suffix('.tmp');tmp.write_bytes(Path(__file__).read_bytes());tmp.replace(snapshot)
    record=dict(repair='static_wire_v1',created=datetime.now(timezone.utc).isoformat(),
        reason='Clamp floating-point complement of a valid static weight to its existing bounds; 1 - 0.9 must be accepted as 0.1.',
        original_runner_sha=plan['runner_sha'],repaired_runner_sha=sha(snapshot),
        study_sha=sha(out/'study.json'),completed_jobs_preserved=len(jobs),
        preserved_hashes={str(p.relative_to(out)):sha(p) for p in preserved})
    check_stop(out);write(folder/'repair.json',record)
    verify_runner(out,plan)
    print(f'STATIC-WIRE REPAIR REGISTERED. {len(jobs)} completed jobs verified and retained. '
          'Models, frozen inputs and original study unchanged. Run all to resume.',flush=True)


def protocol(profile):
    return dict(format=1,workflow='scope_deadline_pilot_v1',purpose='development only; no superiority or publication readiness claim',
        profile=profile,routing_schema=SCHEMA,lambda_value=.05,r_max=.15,
        minutes=6 if profile=='smoke' else 60,warmup_minutes=3,
        collection_iterations=list(range(3001,3006 if profile=='smoke' else 3011)),
        collection_loads=[900,1800] if profile=='smoke' else [600,900,1200,1500,1800],
        loads=[900,1800] if profile=='smoke' else [900,1200,1800],
        tuning_iterations=[3201] if profile=='smoke' else [3201,3202],
        pilot_iterations=[1904] if profile=='smoke' else [1904,1905,1906],
        policies=POLICIES,static_shortlist_size=4,static_selection='training-ranked shortlist plus initial; select per-load by independent calibration simulation, not exhaustive best-static',
        adaptation_load=900 if profile=='smoke' else 1200,
        adaptation_shift_seconds=240 if profile=='smoke' else 1200,
        adaptation_recovery_seconds=300 if profile=='smoke' else 2400,
        adaptation_rate_multiplier=1.5,
        note='Smoke results only verify plumbing. Full profile is still development. Diagnostic logging is not a runtime benchmark.')


def prepare(out,args):
    if (out/'study.json').exists():
        plan=load_plan(out)
        require(plan['profile']==args.profile,'Profile differs; use a separate --output directory')
        verify(out,plan['input_hashes']);print('Already prepared: '+str(out),flush=True);return plan
    require(not out.exists() or not any(p.name!='.runner.lock' for p in out.iterdir()),'Output exists without a completed preparation. Preserve it and use a new --output directory.')
    out.mkdir(parents=True,exist_ok=True)
    write(out/'preparing.json',dict(profile=args.profile,status='preparing'))
    java=select_java(args.java)
    managed([sys.executable,'-c','import flask,numpy,pandas,xgboost,sklearn,scipy,matplotlib; print("Dependencies OK")'],out/'dependencies.log',out)
    runtime=out/'runtime';runtime.mkdir()
    shutil.copytree(REPO/'ThreeBrains/src',runtime/'src')
    shutil.copytree(REPO/'ThreeBrains/lib',runtime/'lib')
    services=runtime/'services';services.mkdir()
    for p in BASE.glob('*.py'):shutil.copy2(p,services/p.name)
    cfg=out/'inputs';shutil.copytree(BASE/'deadline_pilot',cfg)
    shutil.copytree(BASE/'deadline_pilot/matlab',out/'matlab')
    shutil.copytree(REPO/'ThreeBrains/scripts/sample_app5/config/weka',cfg/'weka')
    require(len(list((cfg/'weka').glob('*.model')))==6,'Six Weka model files are required')
    classes=runtime/'classes';classes.mkdir()
    cp=os.pathsep.join(map(str,sorted((runtime/'lib').glob('*.jar'))))
    require(bool(cp),'Missing Java libraries')
    print('Compiling isolated Java classes with '+java,flush=True)
    managed([java,'-m','jdk.compiler/com.sun.tools.javac.Main','-classpath',cp,'-sourcepath',runtime/'src',
             '-d',classes,runtime/'src'/Path(MAIN.replace('.','/')+'.java')],out/'compile.log',out)
    plan=protocol(args.profile)
    try:commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=REPO,text=True).strip()
    except (OSError,subprocess.CalledProcessError):commit='unknown'
    plan.update(java=java,python=sys.executable,package_versions=versions(),repo=str(REPO),output=str(out),commit=commit,
        created=datetime.now(timezone.utc).isoformat(),runner_sha=sha(__file__),
        input_hashes={str(p.relative_to(out)):sha(p) for d in [runtime,cfg] for p in d.rglob('*') if p.is_file()})
    (out/'python_packages.txt').write_text(subprocess.check_output([sys.executable,'-m','pip','freeze'],text=True))
    write(out/'study.json',plan)
    (out/'study_checksum.txt').write_text(sha(out/'study.json')+'\n')
    print('PREPARED. Original code, models and results have not been replaced. '+str(out),flush=True)
    return plan


def complete(out,key):
    p=out/'jobs'/key/'complete.json'
    if not p.exists():return None
    r=read(p);folder=out/r['attempt'];verify(folder,r['hashes']);return r


def attempt(out,key):
    folder=out/'jobs'/key;folder.mkdir(parents=True,exist_ok=True)
    i=1
    while (folder/f'attempt_{i:03}').exists():i+=1
    p=folder/f'attempt_{i:03}';p.mkdir();return p


def receipt(out,key,folder,result):
    write(folder/'result.json',result)
    write(out/'jobs'/key/'complete.json',dict(attempt=str(folder.relative_to(out)),hashes=hashes(folder),result=result))
    return result


def generic(p):
    lines=p.read_text().splitlines();require(lines.count('#auto generated file!')==1,'Invalid generic log: '+str(p))
    a=[float(v) for v in lines[1].split(';')]
    require(len(a)==14 and all(math.isfinite(x) and x>=0 for x in a),'Invalid finalized metrics')
    require(a[0]+a[1]>0,'No finalized tasks')
    return dict(completed=int(a[0]),failed=int(a[1]),pending=int(a[2]),failure_pct=100*a[1]/(a[0]+a[1]),
        service_seconds=a[4],processing_seconds=a[5],network_seconds=a[6],qoe_completed_pct=a[11],qoe_all_pct=a[12],
        vm_capacity_failures=int(a[9]),mobility_failures=int(a[10]),network_failures=int(a[3]))


def cp(out):return os.pathsep.join([str(out/'runtime/classes')]+list(map(str,sorted((out/'runtime/lib').glob('*.jar')))))


def model_paths(out):
    r=complete(out,'train');require(r is not None,'Run collect and train first')
    folder=out/r['attempt'];return folder/'models',folder/'dataset'


def check_models(out,allow):
    models,data=model_paths(out)
    manifest=read(models/'model_manifest.json');require(manifest.get('routing_schema')==SCHEMA,'Old routing models are forbidden')
    status=read(models/'readiness_report.json')['status']
    require(allow or status=='READY_FOR_OPTIMIZER_INTEGRATION_TEST',
            'Model readiness is '+status+'. Inspect readiness_report.json. For diagnostic-only testing use --allow-unready-models; this is recorded.')
    return models,data


def port_available():
    with socket.socket() as s:
        s.setsockopt(socket.SOL_SOCKET,socket.SO_REUSEADDR,1)
        try:s.bind(('127.0.0.1',5002))
        except OSError as e:raise RuntimeError('Port 5002 is occupied. Stop your old Flask launcher; this runner will not kill it.') from e


def simulation(out,plan,key,policy,n,iteration,static=None,burst=False,allow=False):
    done=complete(out,key)
    if done:return done['result']
    check_stop(out);folder=attempt(out,key);javaout=folder/'java';javaout.mkdir()
    cfg=folder/'config.properties';settings=dict(simulation_time=plan['minutes'],warm_up_period=3,
        min_number_of_mobile_devices=n,max_number_of_mobile_devices=n,mobile_device_counter_size=1,
        orchestrator_policies=policy,file_log_enabled='true',deep_file_log_enabled='false')
    text=(out/'inputs/base.properties').read_text()
    for k,v in settings.items():
        pattern=r'(?m)^'+re.escape(k)+r'=.*$'
        text=re.sub(pattern,k+'='+str(v),text) if re.search(pattern,text) else text+'\n'+k+'='+str(v)+'\n'
    cfg.write_text(text);(folder/'weka').symlink_to(out/'inputs/weka',target_is_directory=True)
    cmd=[plan['java'],'-Xmx2g','-Dscope.optimizer.failFast=true','-Dscope.deadlineTierGuard=true',
         '-Dscope.auditWorkload=true','-Dscope.logPerformanceWindows=true',
         '-Dscope.trainingData.path='+str(folder/'candidate_windows.csv')]
    if static is not None:
        (folder/'static.txt').write_text(wire(static));cmd+=['-Dscope.staticConfig='+str(folder/'static.txt')]
    if burst:cmd+=['-Dscope.workload.shiftSeconds='+str(plan['adaptation_shift_seconds']),
        '-Dscope.workload.recoverySeconds='+str(plan['adaptation_recovery_seconds']),
        '-Dscope.workload.rateMultiplier='+str(plan['adaptation_rate_multiplier'])]
    cmd+=['-cp',cp(out),MAIN,str(cfg),str(out/'inputs/edge_devices.xml'),str(out/'inputs/applications.xml'),str(javaout),str(iteration)]
    write(folder/'command.json',cmd);write(folder/'settings.json',dict(policy=policy,load=n,iteration=iteration,burst=burst,allow_unready_models=allow,routing_schema=SCHEMA))
    server=None;log=None
    print('RUN '+key+' | '+str(folder/'java.log'),flush=True)
    try:
        if policy in ['SCOPE','PERFORMANCE_ONLY','SOFTCOST_OPT']:
            models,data=check_models(out,allow);port_available();e=env()
            e.update(SCOPE_RESULTS_DIR=str(models),SCOPE_CANDIDATE_DATASET=str(data/'candidate_dataset_train.csv'),
                SCOPE_DIAGNOSTIC_DIR=str(folder/'diagnostics'),SCOPE_ABLATION_RESULTS_DIR=str(folder/'scope'),
                SCOPE_HARD_STABILITY='1',SCOPE_LAMBDA='.05',SCOPE_R_MAX='.15',SCOPE_PORT='5002',SCOPE_W_FAILURE='.5',SCOPE_W_SERVICE='.5')
            log=(folder/'service.log').open('w')
            server=subprocess.Popen([sys.executable,'-u',str(out/'runtime/services/scope_diagnostic_service.py')],cwd=out/'runtime/services',env=e,stdout=log,stderr=log,start_new_session=True)
            end=time.monotonic()+60
            while True:
                check_stop(out);require(server.poll() is None,'Service exited: '+str(folder/'service.log'))
                try:
                    with urllib.request.urlopen('http://127.0.0.1:5002/health',timeout=1) as h:health=json.load(h)
                    require(health['routing_schema']==SCHEMA and health['lambda']==.05 and health['r_max']==.15,'Service settings mismatch')
                    write(folder/'health.json',health);break
                except (OSError,ValueError):
                    require(time.monotonic()<end,'Service readiness timeout');time.sleep(.2)
        managed(cmd,folder/'java.log',out,cwd=out,environ=env(),peer=server)
    finally:
        terminate(server)
        if log:log.close()
    text=(folder/'java.log').read_text()
    require(text.count('Scenario finished at ')==1 and 'Simulation finished at ' in text,'Incomplete Java scenario')
    require(not any(t in text for t in ['Exception','ERROR','unexpected error','Training-data write failed']),'Java reported errors')
    if policy!='AI_BASED':require('ROUTING_SCHEMA='+SCHEMA in text,'Routing flag was not applied')
    fingerprints=re.findall(r'WORKLOAD_AUDIT .*sha256=([a-f0-9]{64})',text)
    require(len(fingerprints)==1,'Missing workload audit')
    require(len(parse_windows(text))==3*len(range(70,plan['minutes']*60,60)), 'Missing performance reporting windows')
    metrics={a:generic(javaout/f'SIMRESULT_ITS_SCENARIO_{policy}_{n}DEVICES_{a}_GENERIC.log') for a in APPS}
    records=[json.loads(line) for p in (folder/'diagnostics').rglob('*.jsonl') for line in p.read_text().splitlines()]
    expected=len(range(70,plan['minutes']*60,60)) if server else 0
    require(len(records)==expected,'Missing or duplicated optimizer decisions')
    for r in records:
        q=r['request'];require(q['routing_schema']==SCHEMA and q['iteration']==iteration and q['num_devices']==n and q['policy']==policy,'Decision identity mismatch')
        if policy=='SCOPE':require(r['selected']['reconfiguration_cost']<=.15+1e-9,'Hard bound violated')
    movements=[r['selected']['reconfiguration_cost'] for r in records]
    result=dict(policy=policy,load=n,iteration=iteration,burst=burst,metrics=metrics,workload_sha256=fingerprints[0],
        decisions=len(records),total_movement=None if policy=='AI_BASED' else sum(movements),
        max_step=None if policy=='AI_BASED' else max(movements,default=0),changes=None if policy=='AI_BASED' else sum(x>1e-9 for x in movements))
    receipt(out,key,folder,result)
    m=metrics['ALL_APPS'];print(f"DONE {key}: failures={m['failure_pct']:.4f}%, service={m['service_seconds']:.6f}s",flush=True)
    return result


def collect(out,plan,args):
    for i in plan['collection_iterations']:
        for n in plan['collection_loads']:simulation(out,plan,f'collect_i{i}_n{n}','SCOPE_DATA_COLLECTION',n,i)


def train(out,plan,args):
    if complete(out,'train'):return
    records=[]
    for i in plan['collection_iterations']:
        for n in plan['collection_loads']:
            r=complete(out,f'collect_i{i}_n{n}');require(r is not None,'Collection incomplete; rerun collect')
            records.append(out/r['attempt']/'candidate_windows.csv')
    folder=attempt(out,'train');raw=folder/'candidate_windows.csv'
    with raw.open('w') as f:
        header=None
        for p in records:
            lines=p.read_text().splitlines();require(len(lines)>1,'No training rows: '+str(p))
            if header is None:header=lines[0];f.write(header+'\n')
            require(lines[0]==header,'Training CSV schemas differ')
            f.write('\n'.join(lines[1:])+'\n')
    service=out/'runtime/services';dataset=folder/'dataset';models=folder/'models'
    managed([sys.executable,service/'prepare_candidate_dataset.py','--input',raw,'--output-dir',dataset,'--seed','42'],folder/'prepare_dataset.log',out,cwd=service)
    require(read(dataset/'candidate_feature_schema.json')['routing_schema']==SCHEMA,'Wrong dataset schema')
    print('Training new models; log: '+str(folder/'training.log'),flush=True)
    managed([sys.executable,service/'train_candidate_xgboost.py','--data-dir',dataset,'--output-dir',models,
             '--telemetry-schema','vm_percent_all_vms_v1'],folder/'training.log',out,cwd=service)
    manifest=read(models/'model_manifest.json');require(manifest['routing_schema']==SCHEMA,'Wrong model schema')
    readiness=read(models/'readiness_report.json')
    receipt(out,'train',folder,dict(readiness=readiness['status'],routing_schema=SCHEMA))
    print('TRAINING COMPLETE: '+readiness['status'],flush=True)


def wire(values):
    a,*rest=map(float,values);w=rest[:3];t=rest[3:]
    require(len(values)==7 and .05<=a<=.95 and all(.1<=x<=.9 for x in w) and all(20<=x<=95 for x in t),'Invalid static configuration')
    # Validate the actual candidate first. Only its redundant complement needs
    # endpoint protection: binary floating point makes 1 - 0.9 < 0.1. Java uses
    # wLoad to set both weights after parsing, so this changes no valid action.
    distance=[max(.1,min(.9,1-x)) for x in w]
    return 'ALPHA:'+str(a)+'|'+'|'.join(f'{i}:{w[i]}:{distance[i]}:{t[i]}' for i in range(3))


def normalized(x,low,high):return min(1.,max(0.,(x-low)/(high-low)))


def objective(metrics,support,deadlines):
    total=sum(metrics[a]['completed']+metrics[a]['failed'] for a in APPS[1:]);score=0.
    for a,d in zip(APPS[1:],deadlines):
        m=metrics[a];w=(m['completed']+m['failed'])/total
        # No-completion convention matches the training target (one deadline).
        dnst=m['service_seconds']/d if m['completed'] else 1.
        score+=w*.5*(normalized(m['failure_pct']/100,support['failure_min'],support['failure_max'])+
                         normalized(dnst,support['dnst_min'],support['dnst_max']))
    return score


def shortlist(out,plan):
    p=out/'static_shortlist.json'
    if p.exists():
        require((out/'static_shortlist_checksum.txt').read_text().strip()==sha(p),'Static shortlist changed after registration')
        return read(p)
    import pandas as pd
    models,data=model_paths(out);support=read(models/'model_manifest.json')['normalization']
    frame=pd.read_csv(data/'candidate_dataset_train.csv')
    # Screen only TRAINING observations. Full simulations on independent tuning
    # seeds choose among the shortlist. This is not a global-best-static claim.
    frame['screen_score']=.5*((frame.target_failure_rate-support['failure_min'])/(support['failure_max']-support['failure_min'])).clip(0,1)+.5*((frame.target_deadline_norm_service_time-support['dnst_min'])/(support['dnst_max']-support['dnst_min'])).clip(0,1)
    result={}
    for n in plan['loads']:
        grouped=frame[frame.num_devices==n].groupby(COLS,sort=True).screen_score.mean().sort_values(kind='stable')
        choices=[INITIAL]
        for key in grouped.index:
            candidate=[round(float(x),12) for x in key]
            # Avoid nearly identical shortlist entries; fixed selection rule.
            if all(sum(abs(x-y)/s for x,y,s in zip(candidate,c,[.9,.8,.8,.8,75,75,75]))/7>=.05 for c in choices):choices.append(candidate)
            if len(choices)==plan['static_shortlist_size']:break
        require(len(choices)>=2,'Insufficient training candidate coverage for static calibration')
        result[str(n)]=choices
    write(p,result);(out/'static_shortlist_checksum.txt').write_text(sha(p)+'\n');return result


def deadlines(out):
    import xml.etree.ElementTree as ET
    return [float(a.find('max_delay_requirement').text) for a in ET.parse(out/'inputs/applications.xml').getroot().findall('application')]


def tune(out,plan,args):
    if complete(out,'tune_static'):return
    choices=shortlist(out,plan);models,_=model_paths(out);support=read(models/'model_manifest.json')['normalization'];ds=deadlines(out)
    chosen={};scores=[];fingerprints={}
    for n in plan['loads']:
        ranked=[]
        for c,values in enumerate(choices[str(n)]):
            results=[simulation(out,plan,f'tune_c{c}_i{i}_n{n}','SCOPE_STATIC',n,i,static=values) for i in plan['tuning_iterations']]
            for r in results:
                pair=(n,r['iteration']);expected=fingerprints.setdefault(pair,r['workload_sha256'])
                require(expected==r['workload_sha256'],'Static calibration workloads differ')
            mean=sum(objective(r['metrics'],support,ds) for r in results)/len(results)
            ranked.append((mean,c));scores.append(dict(load=n,candidate=c,score=mean,values=values))
        best=min(ranked)[1];chosen[str(n)]=choices[str(n)][best]
    folder=attempt(out,'tune_static');write(folder/'selection.json',dict(configurations=chosen,scores=scores,criterion='mean normalized .5 failure + .5 deadline-normalized service; calibration seeds only'))
    receipt(out,'tune_static',folder,dict(configurations=chosen))
    print('STATIC CALIBRATION COMPLETE; selections frozen before pilot.',flush=True)


def evaluate(out,plan,args,burst=False):
    check_models(out,args.allow_unready_models)
    t=complete(out,'tune_static');require(t is not None,'Run tune-static first')
    fixed=t['result']['configurations'];loads=[plan['adaptation_load']] if burst else plan['loads'];prefix='adapt' if burst else 'pilot'
    for i in plan['pilot_iterations']:
        for n in loads:
            expected=None
            for policy in plan['policies']:
                r=simulation(out,plan,f'{prefix}_{policy}_i{i}_n{n}',policy,n,i,
                    static=fixed[str(n)] if policy=='SCOPE_STATIC' else None,burst=burst,allow=args.allow_unready_models)
                if expected is None:expected=r['workload_sha256']
                require(r['workload_sha256']==expected,'Paired task streams differ; do not compare these runs')
    summarize(out)


def parse_windows(log):
    windows=[]
    for line in log.splitlines():
        # SimLogger progress dots/numbers can precede a message on the same line.
        if 'PERF_WINDOW |' not in line:continue
        line=line[line.index('PERF_WINDOW |'):]
        end=float(re.search(r'Time=([\d.]+)',line)[1])
        apps=re.findall(r'App(\d+) (.*?)(?= \| App|$)',line)
        require([int(a) for a,_ in apps]==[0,1,2],'Incomplete application reporting window')
        for app,fields in apps:
            fields={k:float(v) for k,v in re.findall(r'(\w+)=([\d.]+)',fields)}
            require(set(fields)=={'Total','Completed','Failed','FailRate','MeanService','DeadlineNorm','DeadlineMissRate'},'Malformed performance reporting fields')
            windows.append(dict(app_id=int(app),window_start=end-60,window_end=end,**fields))
    return windows


def summarize(out):
    rows=[];windows=[]
    for p in sorted((out/'jobs').glob('*/complete.json')):
        r=read(p);data=r['result']
        if 'metrics' not in data:continue
        for app,m in data['metrics'].items():rows.append(dict(job=p.parent.name,policy=data['policy'],load=data['load'],iteration=data['iteration'],burst=data['burst'],application=app,**m,total_movement=data['total_movement'],max_step=data['max_step'],changes=data['changes']))
        log=(out/r['attempt']/'java.log').read_text()
        for window in parse_windows(log):
            windows.append(dict(job=p.parent.name,policy=data['policy'],load=data['load'],iteration=data['iteration'],burst=data['burst'],**window))
    if rows:
        with (out/'pilot_metrics.csv').open('w',newline='') as f:
            w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
    write(out/'performance_windows.json',windows)
    if windows:
        with (out/'window_metrics.csv').open('w',newline='') as f:
            w=csv.DictWriter(f,fieldnames=list(windows[0]));w.writeheader();w.writerows(windows)
    print('Metrics: '+str(out/'pilot_metrics.csv'),flush=True)


def status(out):
    require((out/'study.json').exists(),'Not prepared')
    plan=load_plan(out);print('Profile:',plan['profile'],'|',out)
    jobs=sorted((out/'jobs').glob('*/complete.json'))
    print('Completed jobs:',len(jobs))
    for name in ['collect','train','tune','pilot','adapt']:
        print(name+':',sum(p.parent.name.startswith(name) for p in jobs))
    partial=[p.parent for p in (out/'jobs').glob('*/attempt_*') if not (p.parent/'complete.json').exists()]
    print('Unfinished jobs:',len(set(partial)))


def package(out):
    summarize(out);stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ');target=out.parent/(out.name+'_review_'+stamp+'.zip')
    with zipfile.ZipFile(target,'x',zipfile.ZIP_DEFLATED) as z:
        for p in sorted(out.rglob('*')):
            if not p.is_file() or p.is_symlink() or 'runtime' in p.relative_to(out).parts or 'weka' in p.relative_to(out).parts or p.name=='.runner.lock':continue
            z.write(p,Path(out.name)/p.relative_to(out))
    print('Review ZIP: '+str(target),flush=True)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('stage',choices=['prepare','collect','train','tune-static','pilot','adaptation','all','status','stop','package','repair-static-wire'])
    parser.add_argument('--output',type=Path,default=REPO/'ThreeBrains/sim_results/v5_deadline_pilot')
    parser.add_argument('--profile',choices=['pilot','smoke'],default='pilot')
    parser.add_argument('--java');parser.add_argument('--allow-unready-models',action='store_true',help='Diagnostic override only; logged per simulation.')
    args=parser.parse_args();out=args.output.expanduser().resolve()
    if args.stage=='status':status(out);return
    if args.stage=='stop':
        load_plan(out);(out/'STOP_REQUESTED').touch();print('Stop requested. The running job will be preserved as incomplete.');return
    signal.signal(signal.SIGINT,signal_stop);signal.signal(signal.SIGTERM,signal_stop)
    if args.stage=='prepare' and not (out/'study.json').exists():
        # Preparation cannot race on the same destination: create exclusive marker.
        require(not out.exists() or not any(p.name!='.runner.lock' for p in out.iterdir()),'Use a new empty output directory')
        out.mkdir(parents=True,exist_ok=True)
    require(out.exists(),'Run prepare first')
    if args.stage!='prepare':load_plan(out)
    with (out/'.runner.lock').open('a+') as lock:
        try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:raise RuntimeError('Another runner owns this output directory')
        (out/'STOP_REQUESTED').unlink(missing_ok=True)
        try:
            if args.stage=='prepare':prepare(out,args);return
            plan=load_plan(out);require(plan['profile']==args.profile,'Profile mismatch')
            require(versions()==plan['package_versions'],'Python dependency versions changed; prepare a new output for a new environment')
            require(plan['output']==str(out),'Resume in the original output location')
            if args.stage=='repair-static-wire':repair_static_wire(out,plan);return
            verify_runner(out,plan)
            verify(out,plan['input_hashes'])
            operations={'collect':collect,'train':train,'tune-static':tune,'pilot':evaluate,
                        'adaptation':lambda o,p,a:evaluate(o,p,a,True)}
            if args.stage=='package':package(out);return
            stages=['collect','train','tune-static','pilot','adaptation'] if args.stage=='all' else [args.stage]
            for stage in stages:
                check_stop(out)
                if stage=='tune-static':check_models(out,args.allow_unready_models)
                operations[stage](out,plan,args)
            print('Requested stages complete. These are development results; inspect them before a final study.',flush=True)
        except Stopped:
            print('STOPPED safely. Completed jobs are kept; repeat the same command to resume. The interrupted job restarts in a new attempt folder.',flush=True)
            raise SystemExit(130)


if __name__=='__main__':main()
