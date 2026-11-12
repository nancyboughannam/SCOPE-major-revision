"""Export immutable-job evidence; seeds, not tasks/windows, are replicates."""
from collections import defaultdict
import csv
import math
import statistics

import run_deadline_pilot as core


def write_csv(path,rows,fields=None):
    if not rows and not fields:
        path.unlink(missing_ok=True);return
    with path.open('w',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=fields or list(rows[0]));writer.writeheader();writer.writerows(rows)


def interval(values):
    from scipy.stats import t
    core.require(bool(values) and all(math.isfinite(x) for x in values),'Missing or nonfinite statistical input')
    n=len(values);mean=statistics.mean(values)
    half=float(t.ppf(.975,n-1))*statistics.stdev(values)/math.sqrt(n) if n>1 else 0.
    return dict(n=n,mean=mean,lower=mean-half,upper=mean+half)


def paired(values):
    from scipy.stats import t
    row=interval(values)
    if len(values)<2:p=None
    else:
        sd=statistics.stdev(values)
        p=(1. if row['mean']==0 else 0.) if sd==0 else float(2*t.sf(abs(row['mean'])/(sd/math.sqrt(len(values))),len(values)-1))
    return dict(**row,p_raw=p)


def holm(rows):
    families=defaultdict(list)
    for r in rows:
        if r['p_raw'] is not None:families[r['family']].append(r)
    for group in families.values():
        running=0.
        for i,r in enumerate(sorted(group,key=lambda r:r['p_raw'])):
            running=max(running,min(1.,(len(group)-i)*r['p_raw']));r['p_holm']=running
            r['family_tests']=len(group)
    return rows


def contrasts(rows,plan):
    lookup={(r['group'],r['label'],r['load'],r['iteration']):r for r in rows if r['application']=='ALL_APPS'}
    specifications=[]
    for n in plan['loads']:
        for label in plan['main_policies']:
            if label!='SCOPE':specifications.append(('main','main','SCOPE','main',label,n))
    for label in plan['ablation_policies']:
        specifications.append(('ablation','main','SCOPE','ablation',label,plan['ablation_load']))
    specifications.append(('adaptation','adaptation','SCOPE','adaptation','SCOPE_FROZEN',plan['adaptation_load']))
    output=[]
    for family,ga,a,gb,b,n in specifications:
        for metric in plan['inference']['primary_metrics']:
            differences=[lookup[(ga,a,n,i)][metric]-lookup[(gb,b,n,i)][metric] for i in plan['iterations']]
            output.append(dict(family=family,comparison=a+' minus '+b,load=n,metric=metric,
                **paired(differences),p_holm=None,family_tests=0,
                interpretation='negative favors SCOPE for failures and completed-task service'))
    return holm(output)


def phase_rows(out,plan,windows):
    groups={}
    for r in windows:
        if r['group']!='adaptation' or r['window_start']<plan['warmup_minutes']*60:continue
        start,end=r['window_start'],r['window_end'];phase=None
        if end<=plan['shift_seconds']:phase='before'
        elif start>=plan['shift_seconds'] and end<=plan['recovery_seconds']:phase='increase'
        elif start>=plan['recovery_seconds']:phase='recovery'
        if phase is None:continue
        key=(r['job'],phase)
        if key not in groups:
            groups[key]={k:r[k] for k in ['job','group','label','load','iteration']}
            groups[key].update(phase=phase,completed=0,failed=0,service_sum=0.,app_windows=0)
        g=groups[key];g['completed']+=r['Completed'];g['failed']+=r['Failed'];g['service_sum']+=r['Completed']*r['MeanService'];g['app_windows']+=1
    result=[]
    for g in groups.values():
        core.require(g['completed']>0 and g['completed']+g['failed']>0,'Empty finalized phase')
        g['failure_pct']=100*g['failed']/(g['completed']+g['failed']);g['service_seconds']=g.pop('service_sum')/g['completed'];result.append(g)
    return result


def export(out,plan,completed,pairs,expected):
    metrics=[];windows=[];decisions=[];responses=[]
    for folder,r in completed:
        s=r['spec'];meta=dict(job=s['key'],group=s['group'],label=s['label'],policy=s['policy'],load=s['load'],iteration=s['iteration'])
        for app,m in r['metrics'].items():metrics.append(dict(**meta,application=app,**m,total_movement=r['total_movement'],max_step=r['max_step'],changes=r['changes']))
        for w in core.parse_windows((folder/'java.log').read_text()):windows.append(dict(**meta,**w))
        for d in r['decisions']:decisions.append(dict(**meta,**d))
        if s['group']=='adaptation' and s['label'] in ['SCOPE','HARD_ONLY','SOFTCOST_OPT','PERFORMANCE_ONLY','SCOPE_FROZEN']:
            change=[d['timestamp'] for d in r['decisions'] if d['movement']>1e-9]
            first=next((t for t in change if plan['shift_seconds']<=t<plan['recovery_seconds']),None)
            responses.append(dict(**meta,first_change_during_increase=first,
                response_delay_seconds=None if first is None else first-plan['shift_seconds'],
                changes_during_increase=sum(plan['shift_seconds']<=t<plan['recovery_seconds'] for t in change),
                changes_during_recovery=sum(t>=plan['recovery_seconds'] for t in change)))
    write_csv(out/'study_metrics.csv',metrics);write_csv(out/'window_metrics.csv',windows)
    write_csv(out/'decision_metrics.csv',decisions);write_csv(out/'adaptation_responses.csv',responses)
    phases=phase_rows(out,plan,windows);write_csv(out/'phase_metrics.csv',phases)
    displayed=list(metrics)
    # Reuse the very same main runs as controls in the ablation plot; no second
    # sample, duplicate simulation, or increased statistical replication count.
    displayed.extend(dict(r,group='ablation') for r in metrics if r['group']=='main' and
                     r['load']==plan['ablation_load'] and r['label'] in ['SCOPE','SCOPE_STATIC'])
    groups=defaultdict(list)
    measurement_names=['failure_pct','service_seconds','processing_seconds','network_seconds','qoe_all_pct',
                       'edge_utilization_pct','cloud_utilization_pct','pending','total_movement','changes']
    for r in displayed:
        for metric in measurement_names:
            if r[metric] is not None:groups[(r['group'],r['label'],r['load'],r['application'],metric)].append((r['iteration'],r[metric]))
    means=[]
    for (group,label,load,app,metric),values in sorted(groups.items()):
        core.require(len({i for i,v in values})==len(values),'Repeated seed in statistical cell')
        means.append(dict(group=group,label=label,load=load,application=app,metric=metric,**interval([v for i,v in values])))
    write_csv(out/'mean_metrics.csv',means)
    groups=defaultdict(list)
    for r in phases:
        for metric in ['failure_pct','service_seconds']:groups[(r['label'],r['phase'],metric)].append(r[metric])
    write_csv(out/'phase_means.csv',[dict(label=l,phase=p,metric=m,**interval(v)) for (l,p,m),v in sorted(groups.items())])
    complete=len(completed)==expected
    core.require(len({r['spec']['key'] for _,r in completed})==len(completed),'Duplicate completed job')
    if complete:core.require(len(pairs)==len(plan['iterations']),'Missing frozen pair')
    fields=['family','comparison','load','metric','n','mean','lower','upper','p_raw','p_holm','family_tests','interpretation']
    write_csv(out/'paired_comparisons.csv',contrasts(metrics,plan) if complete else [],fields)
    core.write(out/'pair_checks.json',pairs)
    core.write(out/'completion.json',dict(complete=complete,completed=len(completed),expected=expected,matched_pairs=len(pairs),
        profile=plan['profile'],iterations=plan['iterations'],model_retraining=False,
        note='Finish the entire registered set before final figures. No automatic winner, parameter adjustment, or selective stopping.'))
    print(f'Completed {len(completed)}/{expected} evaluation scenarios; verified {len(pairs)} frozen pairs. Results: {out}',flush=True)
