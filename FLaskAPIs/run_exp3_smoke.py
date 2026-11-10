"""Compile and run a short isolated integration check; no production config edits.
Usage: python run_exp3_smoke.py [--arms 5|0|N] [--qos 0.20] [--eta 0.1]
Java 21+ and the existing repository dependencies are required.
"""
import argparse, json, os, shutil, socket, subprocess, sys, time, urllib.request
from datetime import datetime, timezone
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('--arms',type=int,default=5);p.add_argument('--qos',default='0.20');p.add_argument('--eta');a=p.parse_args()
flask=Path(__file__).resolve().parent;root=flask.parent;three=root/'ThreeBrains'
port=5003
with socket.socket() as sock:
 if sock.connect_ex(('127.0.0.1',port))==0:
  raise SystemExit('Stop the existing EXP3 service on port 5003 before running this isolated smoke test.')
java=shutil.which('java');javac=shutil.which('javac')
if not java or not javac:raise SystemExit('Java and javac (JDK 21+) must be on PATH.')
run='smoke_'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
out=flask/'revision_smoke_results'/run;out.mkdir(parents=True)
config=three/'scripts/sample_app5/config'
text=(config/'default_config.properties').read_text()
settings={'simulation_time':'6','warm_up_period':'0','min_number_of_mobile_devices':'100','max_number_of_mobile_devices':'100','orchestrator_policies':'EXP3_MC'}
text='\n'.join(k+'='+settings[k] if '=' in line and (k:=line.split('=',1)[0].strip()) in settings else line for line in text.splitlines())+'\n'
(out/'smoke.properties').write_text(text);(out/'weka').symlink_to(config/'weka',target_is_directory=True)
(out/'simulation').mkdir();classes=out/'classes';classes.mkdir()
subprocess.run([javac,'-classpath',str(three/'lib/*'),'-sourcepath',str(three/'src'),str(three/'src/edu/boun/edgecloudsim/applications/sample_app5/VehicularMainApp.java'),'-d',str(classes)],check=True)
env=dict(os.environ,EXP3_MC_ARM_COUNT=str(a.arms),EXP3_MC_QOS_THRESHOLD=a.qos,EXP3_MC_EXPERIMENT_ID=run,EXP3_MC_RESULTS_DIR=str(out/'decisions'),EXP3_MC_PORT=str(port))
env.pop('EXP3_MC_DECISION_LOG',None)
if a.eta is None:env.pop('EXP3_MC_ETA',None)
else:env['EXP3_MC_ETA']=a.eta
with (out/'service.log').open('w') as sl,(out/'simulator.log').open('w') as jl:
 service=subprocess.Popen([sys.executable,str(flask/'exp3_mc_service.py')],env=env,stdout=sl,stderr=sl)
 try:
  for _ in range(100):
   if service.poll() is not None:raise RuntimeError('Service failed; see '+str(out/'service.log'))
   try:
    with urllib.request.urlopen(f'http://127.0.0.1:{port}/health',timeout=1) as response:health=json.load(response)
    break
   except OSError:time.sleep(.1)
  else:raise RuntimeError('Service did not start')
  subprocess.run([java,'-cp',str(classes)+os.pathsep+str(three/'lib/*'),'edu.boun.edgecloudsim.applications.sample_app5.VehicularMainApp',str(out/'smoke.properties'),str(config/'edge_devices.xml'),str(config/'applications.xml'),str(out/'simulation'),'1'],cwd=root,stdout=jl,stderr=jl,check=True,timeout=180)
 finally:service.terminate();service.wait()
import pandas as pd
logs=list((out/'decisions').glob('*.csv'))
if not logs:raise RuntimeError('No decision logs; inspect simulator.log')
df=pd.concat([pd.read_csv(f) for f in logs],ignore_index=True)
assert df.learning_updates.sum()>0,'No learning observed'
assert df.unknown_feedback_windows.sum()==0,'Unknown feedback attribution'
assert df.eta.gt(0).all()
assert not any(term in (out/'service.log').read_text() for term in ['Traceback','optimization failed'])
assert 'EXP3_MC Error:' not in (out/'simulator.log').read_text()
summary={'status':'passed','catalogue_count':health['candidate_count'],'arms':int(df.arm_count.iloc[0]),'eta':float(df.eta.iloc[0]),'decisions':len(df),'learning_updates':int(df.learning_updates.sum()),'switches':int(df.switched.sum()),'results':str(out)}
(out/'summary.json').write_text(json.dumps(summary,indent=2));print(json.dumps(summary,indent=2))
