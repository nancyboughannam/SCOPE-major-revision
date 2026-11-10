"""Synthetic feedback tests; no simulation or original result files are touched."""
import importlib.util
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
import numpy as np
import pandas as pd

HERE=Path(__file__).resolve().parent
COLS=['candidate_alpha']+[f'candidate_w_load_{i}' for i in range(3)]+[f'candidate_threshold_{i}' for i in range(3)]
INITIAL=dict(zip(COLS,[.6,.5,.7,.4,85.,80.,90.]))

class Choose:
    def choice(self,size,p): return 0

class AuditTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.csv=Path(self.tmp.name)/'catalogue.csv'
        pd.DataFrame([INITIAL]+[dict(zip(COLS,[a,.5,.7,.4,85.,80.,90.])) for a in np.linspace(.05,.95,2536)]).to_csv(self.csv,index=False)
        self.s=self.load()

    def load(self,mode='fixed',count=2537,eta='.1'):
        with patch.dict(os.environ,{'EXP3_MC_CANDIDATE_DATASET':str(self.csv),
                'EXP3_MC_ARM_COUNT':str(count),'EXP3_MC_ETA_MODE':mode,'EXP3_MC_ETA':eta,
                'EXP3_MC_QOS_THRESHOLD':'.2','EXP3_MC_RESULTS_DIR':self.tmp.name}):
            spec=importlib.util.spec_from_file_location('test_exp3_service',HERE/'service.py')
            s=importlib.util.module_from_spec(spec);sys.modules[spec.name]=s;spec.loader.exec_module(s)
        return s

    def request(self,t=70,current=INITIAL,cost=.22):
        return {'run_id':'test','simulation_seed':20260829,'num_devices':1800,'timestamp':t,
            'path_stats':{'curr_alpha':float(current['candidate_alpha'])},
            'app_stats':{str(i):{'total':100,'failure_rate':cost*.7353648757016841,
                'deadline_norm_service_time':.5327461065548065+cost*(1.6538610651089858-.5327461065548065),
                'curr_w_load':float(current[f'candidate_w_load_{i}']),
                'curr_thr':float(current[f'candidate_threshold_{i}'])} for i in range(3)}}

    def state(self): return next(iter(self.s.STATES.values()))

    def test_fixed_initial_not_weighted_by_K(self):
        _,r=self.s._decision(self.request())
        self.assertEqual(r['feedback_origin'],'initial_fixed')
        self.assertEqual(r['feedback_probability'],1)
        self.assertAlmostEqual(r['score_increment'],.078)
        self.assertLess(r['max_selection_probability'],.001)

    def test_saved_probability_not_recomputed(self):
        a,r=self.s._decision(self.request())
        prob=r['next_behavior_probability']
        self.state().logits[:]=np.linspace(-2,2,len(self.state().logits))
        _,later=self.s._decision(self.request(130,a))
        self.assertEqual(later['feedback_origin'],'sampled')
        self.assertEqual(later['feedback_probability'],prob)
        self.assertAlmostEqual(later['estimated_reward'],later['reward']/prob)

    def test_deterministic_retention(self):
        a,r=self.s._decision(self.request(cost=.1))
        self.assertFalse(r['triggered']);self.assertEqual(r['next_behavior_probability'],1)
        _,later=self.s._decision(self.request(130,a,cost=.1))
        self.assertEqual(later['feedback_origin'],'retained')
        self.assertEqual(later['feedback_probability'],1)
        self.assertAlmostEqual(later['score_increment'],.09)

    def test_same_arm_random_draw_is_not_retention(self):
        a,_=self.s._decision(self.request(cost=.1));self.state().rng=Choose()
        a,r=self.s._decision(self.request(130,a))
        self.assertTrue(r['triggered']);self.assertFalse(r['switched'])
        self.assertLess(r['next_behavior_probability'],1)
        _,later=self.s._decision(self.request(190,a))
        self.assertEqual(later['feedback_origin'],'sampled')
        self.assertEqual(later['feedback_probability'],r['next_behavior_probability'])

    def test_unexpected_action_rejected_without_learning(self):
        self.s._decision(self.request(cost=.1));before=self.state().logits.copy()
        with self.assertRaisesRegex(ValueError,'Observed arm differs'):
            self.s._decision(self.request(130,self.state().candidates.iloc[1]))
        np.testing.assert_array_equal(before,self.state().logits)

    def test_repeated_timestamp_resets(self):
        self.s._decision(self.request());_,r=self.s._decision(self.request())
        self.assertTrue(r['reset']);self.assertEqual(r['window'],1)
        self.assertEqual(r['feedback_probability'],1)

    def test_seed_isolates_state(self):
        self.s._decision(self.request());req=self.request();req['simulation_seed']+=1
        _,r=self.s._decision(req)
        self.assertTrue(r['reset']);self.assertEqual(len(self.s.STATES),2)

    def test_scaling_actual_arm_count(self):
        for count in [5,25,100,2537,3000]:
            s=self.load('scaled_k5',count);_,r=s._decision(self.request())
            self.assertEqual(r['arm_count'],min(count,2537))
            self.assertAlmostEqual(r['eta'],.1*5/min(count,2537))

    def test_invalid_settings(self):
        for mode,eta in [('bad','.1'),('fixed','nan'),('fixed','inf'),('fixed','0')]:
            with self.assertRaises(ValueError): self.load(mode,eta=eta)

    def test_endpoint_logs_probabilities_and_resets(self):
        c=self.s.app.test_client();r=c.post('/optimize',json=self.request())
        self.assertEqual(r.status_code,200);self.assertTrue(r.get_json().startswith('ALPHA:'))
        row=pd.read_csv(next(Path(self.tmp.name).glob('exp3_audit_*.csv'))).iloc[0]
        self.assertEqual(row['feedback_probability'],1)
        self.assertEqual(c.get('/health').get_json()['algorithm_version'],'exp3-mc-feedback-v1')
        self.assertEqual(c.post('/reset').status_code,200);self.assertFalse(self.s.STATES)

    def test_fixed_eta_still_can_collapse_after_a_random_draw(self):
        # Important negative control: startup correction is not a scaling cure.
        a,_=self.s._decision(self.request());_,r=self.s._decision(self.request(130,a))
        self.assertGreater(r['score_increment'],100)
        self.assertGreater(r['max_selection_probability'],.999)

    def test_scaled_eta_first_random_update_example(self):
        self.s=self.load('scaled_k5');a,_=self.s._decision(self.request())
        _,r=self.s._decision(self.request(130,a))
        self.assertLess(r['score_increment'],.5)
        self.assertLess(r['max_selection_probability'],.001)

    def test_runner_checks_catalogue_order_and_tampering(self):
        import json,hashlib
        spec=importlib.util.spec_from_file_location('runner',HERE/'run_audit.py')
        runner=importlib.util.module_from_spec(spec);spec.loader.exec_module(runner)
        root=Path(self.tmp.name)
        manifest={'count':2537,'selection_seed':20260828,'initial':INITIAL,
                  'catalogue_file_sha256':hashlib.sha256(self.csv.read_bytes()).hexdigest()}
        (root/'catalogue_manifest.json').write_text(json.dumps(manifest))
        _,meta=runner.prepare(root,root/'new_result','scaled_k5',.1)
        self.assertAlmostEqual(meta['effective_eta'],.5/2537)
        self.assertFalse((root/'new_result').exists())
        with self.csv.open('a') as f:f.write('\n')
        with self.assertRaisesRegex(ValueError,'checksum'):
            runner.prepare(root,root/'new_result','fixed',.1)
        (root/'existing').mkdir()
        with self.assertRaisesRegex(ValueError,'already exists'):
            runner.prepare(root,root/'existing','fixed',.1)

if __name__=='__main__': unittest.main(verbosity=2)
