"""Run from FLaskAPIs: python shared_catalogue_revision/test_shared.py"""
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import pandas as pd
from run_shared import prepare, start, INITIAL, members

PROJECT = Path(os.getenv('TEST_SCOPE_PROJECT', Path(__file__).resolve().parent.parent)).resolve()

class SharedTests(unittest.TestCase):
    def test_sizes_and_existing_selection(self):
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ):
            for k in [5,25,100,2537]:
                exp = Path(tmp)/str(k)
                prepare(PROJECT, exp, k, 20260828)
                scope = start(PROJECT, exp, 'scope', True)
                bandit = start(PROJECT, exp, 'exp3', True)
                self.assertEqual(len(scope.CANDIDATE_CATALOGUE), k)
                self.assertEqual(members(scope.CANDIDATE_CATALOGUE), members(bandit._candidate_batch(INITIAL)))
                self.assertFalse((exp/'scope').exists())
                self.assertFalse((exp/'exp3').exists())

    def test_repeat_and_tamper_rejected(self):
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ):
            exp = Path(tmp)/'pilot'
            prepare(PROJECT, exp, 5, 20260828)
            with self.assertRaises(ValueError): prepare(PROJECT, exp, 5, 20260828)
            with (exp/'catalogue.csv').open('a') as stream: stream.write('\n')
            with self.assertRaises(ValueError): start(PROJECT, exp, 'scope', True)

    def test_api_and_metadata(self):
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ):
            exp = Path(tmp)/'pilot'
            prepare(PROJECT, exp, 5, 20260828)
            for policy in ['scope','exp3']:
                service = start(PROJECT, exp, policy, True)
                data = {'policy': 'SCOPE' if policy=='scope' else 'EXP3_MC',
                    'run_id':'test','iteration':1,'simulation_seed':20260829,'num_devices':1800,'timestamp':70,
                    'servers':[{'load':50}],
                    'path_stats':{'curr_alpha':.6,'sent_edge':500,'sent_rsu':200,'sent_gsm':200,
                                  'fail_edge':30,'fail_rsu':20,'fail_gsm':10},
                    'app_stats':{str(i):{'total':300,'lag':250,'completed':270,'failures':30,
                        'failure_rate':.1,'mean_service_time':.6,'deadline_norm_service_time':1.2,
                        'deadline_miss_rate':.2,'curr_w_load':INITIAL[f'candidate_w_load_{i}'],
                        'curr_thr':INITIAL[f'candidate_threshold_{i}']} for i in range(3)}}
                client = service.app.test_client()
                for _ in range(3):
                    result = client.post('/optimize', json=data)
                    self.assertEqual(result.status_code,200,result.get_data(as_text=True))
                    response = result.get_json() if result.is_json else result.get_data(as_text=True)
                    parts = response.rstrip('|').split('|')
                    current = {'candidate_alpha':float(parts[0].split(':')[1])}
                    data['path_stats']['curr_alpha']=current['candidate_alpha']
                    for part in parts[1:]:
                        i,w,_,t=part.split(':')
                        current[f'candidate_w_load_{i}']=float(w)
                        current[f'candidate_threshold_{i}']=float(t)
                        data['app_stats'][i].update(curr_w_load=float(w),curr_thr=float(t))
                    self.assertTrue(members(pd.DataFrame([current])) <= members(service.CANDIDATE_CATALOGUE))
                    data['timestamp']+=60
                self.assertTrue(list((exp/policy).rglob('*.csv')))
            # Mock only the blocking web server to verify production startup metadata.
            exp2=Path(tmp)/'metadata'
            prepare(PROJECT,exp2,5,20260828)
            with patch('flask.Flask.run'):
                start(PROJECT,exp2,'scope')
                start(PROJECT,exp2,'exp3')
            import json
            a=json.loads((exp2/'scope/run_manifest.json').read_text())
            b=json.loads((exp2/'exp3/run_manifest.json').read_text())
            self.assertEqual(a['catalogue_file_sha256'],b['catalogue_file_sha256'])

if __name__=='__main__': unittest.main(verbosity=2)
