import os, json, tempfile, unittest
from pathlib import Path
import numpy as np
import pandas as pd
_tmp=tempfile.TemporaryDirectory()
cols=['candidate_alpha']+[f'candidate_w_load_{i}' for i in range(3)]+[f'candidate_threshold_{i}' for i in range(3)]
rng=np.random.default_rng(42)
rows=np.column_stack([rng.uniform(.05,.95,3000),rng.uniform(.1,.9,(3000,3)),rng.uniform(20,95,(3000,3))])
f=Path(_tmp.name)/'c.csv';pd.DataFrame(rows,columns=cols).to_csv(f,index=False)
os.environ['EXP3_MC_CANDIDATE_DATASET']=str(f)
os.environ['EXP3_MC_RESULTS_DIR']=_tmp.name
os.environ.pop('EXP3_MC_ETA',None)
import exp3_mc_service as m

def req(w=0,feedback=None,c=None):
 c=m.CANDIDATE_CATALOGUE.iloc[0] if c is None else c
 return dict(timestamp=(w+1)*10,closed_window_id=w,feedback_protocol='admission_cohort_v1',feedback=feedback or [],run_id='test',simulation_seed=42,num_devices=100,path_stats={'curr_alpha':float(c.iloc[0])},app_stats={str(i):{'curr_w_load':float(c[f'candidate_w_load_{i}']),'curr_thr':float(c[f'candidate_threshold_{i}'])} for i in range(3)})
def cohort(w,n=10,bad=False):
 return {'window_id':w,'app_stats':{str(i):dict(total=n if i==0 else 0,completed=n if i==0 and not bad else 0,failures=n if i==0 and bad else 0,failure_rate=1 if bad else 0,deadline_norm_service_time=1 if bad else .6) for i in range(3)}}
class Tests(unittest.TestCase):
 def setUp(self):
  m.STATES.clear();m.ARM_COUNT=5;m.ETA_OVERRIDE=None;m.QOS_THRESHOLD=.2
 def test_initial_probability(self):
  _,r=m._decision(req(feedback=[cohort(0)]));self.assertEqual(json.loads(r['feedback_updates'])[0]['probability'],1)
 def test_empty(self):
  _,r=m._decision(req(feedback=[cohort(0,0)]));self.assertEqual(r['learning_updates'],0);self.assertFalse(r['triggered']);self.assertIsNone(r['reward'])
 def test_retention(self):
  c,_=m._decision(req(feedback=[cohort(0)]));_,r=m._decision(req(1,[cohort(1)],c));self.assertEqual(json.loads(r['feedback_updates'])[0]['probability'],1)
 def test_sample_probability(self):
  c,a=m._decision(req(feedback=[cohort(0,bad=True)]));self.assertTrue(a['triggered']);_,b=m._decision(req(1,[cohort(1)],c));self.assertEqual(json.loads(b['feedback_updates'])[0]['probability'],a['selection_probability'])
 def test_delayed_original_arm(self):
  m._decision(req());s=next(iter(m.STATES.values()));original=s.pending[0][0];s.current_index=1;s.pending[1]=(1,.25)
  _,r=m._decision(req(1,[cohort(0,bad=True)],s.candidates.iloc[1]));self.assertEqual(json.loads(r['feedback_updates'])[0]['arm'],original);self.assertFalse(r['triggered'])
 def test_duplicate(self):
  c,_=m._decision(req(feedback=[cohort(0)]));_,r=m._decision(req(1,[cohort(0)],c));self.assertEqual(r['learning_updates'],0);self.assertEqual(r['duplicate_feedback_windows'],1)
 def test_incomplete(self):
  f=cohort(0);f['app_stats']['0']['completed']=9
  with self.assertRaisesRegex(ValueError,'complete admission'):m._decision(req(feedback=[f]))
 def test_protocol(self):
  d=req();del d['feedback_protocol']
  with self.assertRaisesRegex(ValueError,'Updated Java'):m._decision(d)
 def test_empty_class_weight(self):
  _,r=m._decision(req(feedback=[cohort(0)]));self.assertEqual(r['app_weight_0'],1);self.assertEqual(r['app_weight_1'],0)
 def test_full_eta(self):
  m.ARM_COUNT=0;_,r=m._decision(req(feedback=[cohort(0,bad=True)]));self.assertEqual(r['arm_count'],3000);self.assertAlmostEqual(r['eta'],.5/3000);self.assertTrue(np.isfinite(m._softmax(next(iter(m.STATES.values())).logits)).all())
 def test_nested_subsets(self):
  c=m._current_candidate(req());a=m._candidate_batch(c);m.ARM_COUNT=20;b=m._candidate_batch(c);self.assertTrue(set(map(tuple,a.to_numpy())).issubset(set(map(tuple,b.to_numpy()))))
 def test_log_names(self):
  _,r=m._decision(req());p=m._decision_log_path(r);r['arm_count']=20;self.assertNotEqual(p,m._decision_log_path(r))
 def test_http(self):
  r=m.app.test_client().post('/optimize',json=req(feedback=[cohort(0)]));self.assertEqual(r.status_code,200);self.assertTrue(r.get_json().startswith('ALPHA:'))
 def test_restart_unknown(self):
  _,r=m._decision(req(4,[cohort(3)]));self.assertEqual(r['unknown_feedback_windows'],1);self.assertEqual(r['learning_updates'],0)
 def test_failed_batch_does_not_commit(self):
  c,_=m._decision(req());state=next(iter(m.STATES.values()));before=state.logits.copy()
  broken=cohort(1);broken['app_stats']['0']['completed']=9
  with self.assertRaises(ValueError):m._decision(req(1,[cohort(0),broken],c))
  self.assertTrue(np.array_equal(next(iter(m.STATES.values())).logits,before))
 def test_five_arm_subset_preserved(self):
  current=m._current_candidate(req());actual=m._candidate_batch(current)
  allc=pd.concat([pd.DataFrame([current]),m.CANDIDATE_CATALOGUE],ignore_index=True).astype(float).round(10).drop_duplicates(cols).reset_index(drop=True)
  old=np.random.default_rng(m.ARM_SELECTION_SEED).choice(np.arange(1,len(allc)),size=4,replace=False)
  expected=allc.iloc[np.concatenate(([0],np.sort(old)))].reset_index(drop=True)
  pd.testing.assert_frame_equal(actual,expected[cols])
 def test_explicit_eta(self):
  m.ETA_OVERRIDE='0.003';m.ETA=.003;m.ARM_COUNT=0
  _,r=m._decision(req());self.assertEqual(r['eta'],.003);m.ETA=.1
if __name__=='__main__':unittest.main()
