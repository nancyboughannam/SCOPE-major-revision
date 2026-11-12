"""Fast safety and schema checks; native end-to-end checks are documented separately."""
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import threading
import time
import unittest

import pandas as pd
import run_deadline_pilot as pilot
from scope_objective import check_routing, DEADLINE_ROUTING, LEGACY_ROUTING, LEGACY_SUPPORT
from prepare_candidate_dataset import clean_rows
from train_candidate_xgboost import load_and_validate


class RoutingTests(unittest.TestCase):
    def test_legacy_compatibility(self):
        check_routing({},None);check_routing({},LEGACY_ROUTING)

    def test_both_mismatch_directions(self):
        for manifest,received in [({},DEADLINE_ROUTING),({'routing_schema':DEADLINE_ROUTING},None),
                                  ({'routing_schema':'unknown'},'unknown')]:
            with self.assertRaisesRegex(ValueError,'Routing schema mismatch'):check_routing(manifest,received)

    def test_matching_new_schema(self):
        check_routing({'routing_schema':DEADLINE_ROUTING},DEADLINE_ROUTING)

    def test_exp3_loads_manifest_and_rejects_legacy_request(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp);manifest=p/'manifest.json';catalogue=p/'catalogue.csv'
            manifest.write_text(json.dumps(dict(routing_schema=DEADLINE_ROUTING,normalization=LEGACY_SUPPORT)))
            pd.DataFrame([pilot.INITIAL],columns=pilot.COLS).to_csv(catalogue,index=False)
            e=pilot.env();e.update(EXP3_MC_NORMALIZATION_MANIFEST=str(manifest),EXP3_MC_CANDIDATE_DATASET=str(catalogue),EXP3_MC_RESULTS_DIR=str(p/'results'))
            script="import exp3_mc_service as s; assert s.app.test_client().get('/health').get_json()['routing_schema']=='deadline_guard_v1'; r=s.app.test_client().post('/optimize',json={'routing_schema':'edge_first_v1'}); assert r.status_code==500 and 'Routing schema mismatch' in r.get_json()['error']; assert not s.STATES"
            r=subprocess.run([sys.executable,'-c',script],cwd=Path(__file__).parent,env=e,capture_output=True,text=True)
            self.assertEqual(r.returncode,0,r.stderr)

    def test_dataset_labels_cannot_be_relabelled(self):
        with tempfile.TemporaryDirectory() as tmp:
            d=Path(tmp)
            (d/'candidate_feature_schema.json').write_text(json.dumps(dict(routing_schema=DEADLINE_ROUTING,feature_columns=['num_devices'])))
            pd.DataFrame([dict(run_id='a',num_devices=900,routing_schema=LEGACY_ROUTING,target_failure_rate=.1,target_deadline_norm_service_time=.5)]).to_csv(d/'candidate_dataset_train.csv',index=False)
            with self.assertRaisesRegex(ValueError,'routing does not match'):load_and_validate(d)


class RunnerTests(unittest.TestCase):
    def test_completed_job_is_immutable(self):
        with tempfile.TemporaryDirectory() as tmp:
            out=Path(tmp);folder=pilot.attempt(out,'one');(folder/'data').write_text('original')
            pilot.receipt(out,'one',folder,{'ok':True})
            self.assertEqual(pilot.complete(out,'one')['result'],{'ok':True})
            (folder/'data').write_text('changed')
            with self.assertRaisesRegex(RuntimeError,'Changed or missing'):pilot.complete(out,'one')

    def test_retry_preserves_partial_attempt(self):
        with tempfile.TemporaryDirectory() as tmp:
            out=Path(tmp);first=pilot.attempt(out,'job');(first/'partial').write_text('keep')
            second=pilot.attempt(out,'job')
            self.assertNotEqual(first,second);self.assertEqual((first/'partial').read_text(),'keep')

    def test_unowned_folder_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp);(p/'study.json').write_text('{"profile":"pilot"}')
            with self.assertRaisesRegex(RuntimeError,'not owned'):pilot.load_plan(p)

    def test_registered_settings_cannot_change_silently(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp);pilot.write(p/'study.json',pilot.protocol('pilot'))
            (p/'study_checksum.txt').write_text(pilot.sha(p/'study.json'))
            self.assertEqual(pilot.load_plan(p)['lambda_value'],.05)
            v=pilot.read(p/'study.json');v['lambda_value']=.2;pilot.write(p/'study.json',v)
            with self.assertRaisesRegex(RuntimeError,'settings changed'):pilot.load_plan(p)

    def test_stop_terminates_child_group(self):
        with tempfile.TemporaryDirectory() as tmp:
            out=Path(tmp);pidfile=out/'child.pid'
            code='import os,time;open('+repr(str(pidfile))+',"w").write(str(os.getpid()));time.sleep(60)'
            def stopper():
                end=time.monotonic()+5
                while not pidfile.exists() and time.monotonic()<end:time.sleep(.01)
                (out/'STOP_REQUESTED').touch()
            thread=threading.Thread(target=stopper);thread.start()
            with self.assertRaises(pilot.Stopped):pilot.managed([sys.executable,'-c',code],out/'log',out)
            thread.join();pid=int(pidfile.read_text())
            with self.assertRaises(ProcessLookupError):os.kill(pid,0)

    def test_existing_listener_is_not_killed(self):
        import socket
        with socket.socket() as s:
            s.setsockopt(socket.SOL_SOCKET,socket.SO_REUSEADDR,1)
            try:s.bind(('127.0.0.1',5002))
            except OSError:self.skipTest('Existing unrelated service on 5002')
            s.listen()
            with self.assertRaisesRegex(RuntimeError,'occupied'):pilot.port_available()
            self.assertNotEqual(s.fileno(),-1)

    def test_static_wire_requires_valid_ranges(self):
        self.assertTrue(pilot.wire(pilot.INITIAL).startswith('ALPHA:0.6|'))
        for v in [[1,.5,.7,.4,85,80,90],[.6,.5,.7,.4,19,80,90]]:
            with self.assertRaises(RuntimeError):pilot.wire(v)

    def test_smoke_and_pilot_separate_from_old_final_seeds(self):
        for profile in ['pilot','smoke']:
            p=pilot.protocol(profile)
            self.assertFalse(set(p['pilot_iterations']) & set(range(2001,2011)))
            self.assertFalse(set(p['pilot_iterations']) & set(p['collection_iterations']))
            self.assertFalse(set(p['pilot_iterations']) & set(p['tuning_iterations']))

    def test_progress_prefix_does_not_hide_windows(self):
        line='.......10.....PERF_WINDOW | Policy=SCOPE | Time=250.0'
        for i in range(3):line+=f' | App{i} Total=12 Completed=10 Failed=1 FailRate=0.0833 MeanService=0.5 DeadlineNorm=1.0 DeadlineMissRate=0.2'
        rows=pilot.parse_windows(line)
        self.assertEqual(len(rows),3);self.assertEqual(rows[0]['window_start'],190)
        self.assertEqual(rows[2]['Completed'],10)


if __name__=='__main__':unittest.main()
