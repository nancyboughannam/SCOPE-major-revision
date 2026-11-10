"""Run selector regression tests and isolated 6-minute Java smoke scenarios.
No Flask service needed: RAIDER_TRAX exercises the shared patched selector.
Usage from FLaskAPIs: python test_edge_vm_fix.py
"""
from pathlib import Path
from datetime import datetime, timezone
import csv, hashlib, json, os, re, shutil, subprocess, xml.etree.ElementTree as ET

root = Path(__file__).resolve().parent.parent
three = root / 'ThreeBrains'
config = three / 'scripts/sample_app5/config'
package = 'edu/boun/edgecloudsim/applications/sample_app5'
java, javac = shutil.which('java'), shutil.which('javac')
if not java or not javac:
    raise SystemExit('Java and javac (JDK 21+) must both be on PATH.')
out = three / 'revision_results' / ('edge_vm_smoke_' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ'))
classes = out / 'classes'
classes.mkdir(parents=True)
subprocess.run([javac, '-d', str(classes), str(three/'src'/package/'EdgeVmSelector.java'),
                str(Path(__file__).with_name('EdgeVmSelectorTest.java')),
                str(Path(__file__).with_name('EdgeVmCapacityTest.java'))], check=True)
subprocess.run([java, '-cp', str(classes), 'EdgeVmSelectorTest'], check=True)
subprocess.run([java, '-cp', str(classes), 'EdgeVmCapacityTest'], check=True)
subprocess.run([javac, '-classpath', str(three/'lib/*'), '-sourcepath', str(three/'src'),
                '-d', str(classes), str(three/'src'/package/'VehicularMainApp.java')], check=True)
test_cp = str(classes)+os.pathsep+str(three/'lib/*')
subprocess.run([javac, '-classpath', test_cp, '-d', str(classes),
                str(Path(__file__).with_name('EdgeVmLoadUnitsTest.java'))], check=True)
subprocess.run([java, '-cp', test_cp,
                'edu.boun.edgecloudsim.applications.sample_app5.EdgeVmLoadUnitsTest'], check=True)
subprocess.run([javac, '-classpath', test_cp, '-d', str(classes),
                str(Path(__file__).with_name('OptimizerReplyTest.java'))], check=True)
subprocess.run([java, '-cp', test_cp, 'OptimizerReplyTest'], check=True)
settings = {'simulation_time':'6','warm_up_period':'0','min_number_of_mobile_devices':'100',
            'max_number_of_mobile_devices':'1800','mobile_device_counter_size':'1700',
            'orchestrator_policies':'RAIDER_TRAX','file_log_enabled':'true'}
lines=[]
for line in (config/'default_config.properties').read_text().splitlines():
    k=line.split('=',1)[0].strip()
    lines.append(k+'='+settings[k] if '=' in line and k in settings else line)
(out/'smoke.properties').write_text('\n'.join(lines)+'\n')
(out/'weka').symlink_to((config/'weka').resolve(), target_is_directory=True)
sim = out/'ite1'; sim.mkdir()
with (out/'simulator.log').open('w') as log:
    subprocess.run([java,'-cp',str(classes)+os.pathsep+str(three/'lib/*'),
                   'edu.boun.edgecloudsim.applications.sample_app5.VehicularMainApp',
                   str(out/'smoke.properties'),str(config/'edge_devices.xml'),
                   str(config/'applications.xml'),str(sim),'1'],cwd=root,stdout=log,stderr=log,
                   check=True,timeout=300)
text=(out/'simulator.log').read_text()
if any(x in text for x in ('Exception','Terminating simulation','Error:','write edge VM audit')):
    raise RuntimeError('Simulator reported an error; inspect '+str(out/'simulator.log'))
expected=len(ET.parse(config/'edge_devices.xml').getroot().findall('.//VM'))
summaries=[]
for n in (100,1800):
    p=sim/f'EDGE_VM_SELECTION_RAIDER_TRAX_{n}DEVICES.csv'
    with p.open() as f: rows=list(csv.DictReader(f))
    if len(rows)!=expected: raise AssertionError('Inventory differs from XML: '+str(p))
    used=[r for r in rows if int(r['assignment_selections'])>0]
    if not used: raise AssertionError('No edge assignments: '+str(p))
    nonfirst=[r for r in used if int(r['vm_index_on_host'])>0]
    if any(int(r['vm_index_on_host'])>0 for r in rows) and not nonfirst:
        raise AssertionError('No non-first VM selected: '+str(p))
    summaries.append({'devices':n,'configured_vms':expected,'selectable_vms':len(rows),
                      'distinct_vms_selected':len(used),'nonfirst_vms_selected':len(nonfirst)})
summary={'status':'passed','selector_checks':7,'cpu_load_unit_checks':5,'patch_version':4,'capacity_checks':8,
         'optimizer_reply_checks':15,'normalized_distance_checks':2,'policy':'RAIDER_TRAX',
         'purpose':'shared selector mechanics; not a SCOPE performance evaluation',
         'scenarios':summaries,'results':str(out),
         'input_sha256':{name:hashlib.sha256((config/name).read_bytes()).hexdigest()
                         for name in ('default_config.properties','edge_devices.xml','applications.xml')}}
(out/'summary.json').write_text(json.dumps(summary,indent=2))
print(json.dumps(summary,indent=2))
