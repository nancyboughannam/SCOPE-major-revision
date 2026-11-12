"""Controls, source preservation and statistical unit checks for confirmation."""
import csv
import math
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import run_confirmatory_study as study
import confirmatory_reports as reports


class ProtocolTests(unittest.TestCase):
    def test_full_plan_keeps_baselines_and_factorial_ablations(self):
        p=study.protocol('full');jobs=study.evaluation_specs(p)
        self.assertEqual(len(jobs),400);self.assertEqual(len({j['key'] for j in jobs}),400)
        self.assertEqual(p['iterations'],list(range(3401,3411)))
        self.assertEqual(p['loads'],[600,900,1200,1500,1800])
        self.assertEqual([sum(j['group']==g for j in jobs) for g in ['main','ablation','adaptation']],[300,30,70])
        self.assertTrue({'AI_BASED','EXP3_MC','RAIDER_TRAX','RANDOM','SCOPE_STATIC'} <= set(p['main_policies']))
        for j in jobs:
            if j['label']=='SCOPE_FROZEN':
                a=next(x for x in jobs if x['key']==j['key'].replace('SCOPE_FROZEN','SCOPE'))
                self.assertLess(jobs.index(a),jobs.index(j));self.assertEqual(j['policy'],'SCOPE')
            if j['label']=='HARD_ONLY':self.assertEqual(j['policy'],'SCOPE')

    def test_smoke_seeds_are_separate_and_keep_all_policy_paths(self):
        f=study.protocol('full');s=study.protocol('smoke')
        self.assertFalse(set(f['iterations']) & set(s['iterations']+s['tuning_iterations']))
        self.assertEqual(len(study.evaluation_specs(s)),22)
        self.assertEqual(s['main_policies'],f['main_policies']);self.assertEqual(s['adaptation_policies'],f['adaptation_policies'])

    def test_service_environment_clears_old_settings_and_sets_ablation(self):
        p=study.protocol('full');out=Path('/out')
        with patch.dict('os.environ',{'SCOPE_FREEZE_AFTER_SECONDS':'1','EXP3_MC_ETA':'999','SCOPE_LAMBDA':'.2'}):
            e=study.service_environment(out,out/'job',p,study.spec('ablation','HARD_ONLY',1800,3401))
        self.assertEqual(e['SCOPE_LAMBDA'],'0.0');self.assertEqual(e['SCOPE_R_MAX'],'.15')
        self.assertNotIn('SCOPE_FREEZE_AFTER_SECONDS',e);self.assertNotIn('EXP3_MC_ETA',e)
        self.assertEqual(e['EXP3_MC_ARM_COUNT'],'0')
        e=study.service_environment(out,out/'job',p,study.spec('adaptation','SCOPE_FROZEN',1200,3401))
        self.assertEqual(e['SCOPE_FREEZE_AFTER_SECONDS'],'1200');self.assertEqual(e['SCOPE_LAMBDA'],'0.01')

    def test_static_weights_are_checked_without_float_complement_confusion(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'static.txt';values=[.65,.9,.3,.7,85,65,75]
            p.write_text('ALPHA:0.65|0:0.9:0.09999999999999998:85|1:0.3:0.7:65|2:0.7:0.3:75')
            study.verify_static(p,values)
            with self.assertRaisesRegex(RuntimeError,'configuration differs'):study.verify_static(p,[.6,*values[1:]])

    def test_resume_rejects_a_receipt_for_another_policy(self):
        with tempfile.TemporaryDirectory() as d:
            out=Path(d);p=study.protocol('full');j=study.spec('main','SCOPE',600,3401)
            folder=study.core.attempt(out,j['key'])
            study.core.receipt(out,j['key'],folder,dict(spec=dict(j,label='HARD_ONLY')))
            with self.assertRaisesRegex(RuntimeError,'different settings'):study.saved_run(out,p,j)

    def test_shortlist_and_final_seeds_do_not_overlap(self):
        p=study.protocol('full');p['shortlist']={str(n):[study.core.INITIAL]*4 for n in p['loads']}
        jobs=study.tuning_specs(p);self.assertEqual(len(jobs),40)
        self.assertFalse(set(j['iteration'] for j in jobs)&set(p['iterations']))


class StatisticalTests(unittest.TestCase):
    def test_interval_uses_seed_sample_size(self):
        r=reports.interval([1.,2.,3.])
        self.assertEqual(r['n'],3);self.assertEqual(r['mean'],2.)
        self.assertAlmostEqual(r['upper']-r['mean'],2.4841377117,places=8)
        self.assertEqual(reports.interval([4.])['lower'],4.)

    def test_holm_counts_every_comparison_in_its_family(self):
        rows=[dict(family='main',p_raw=p) for p in [.01,.04,.03]]+[dict(family='adaptation',p_raw=.02)]
        result=reports.holm(rows)
        for r,p in zip(result,[.03,.06,.06,.02]):self.assertAlmostEqual(r['p_holm'],p)
        self.assertEqual(result[0]['family_tests'],3);self.assertEqual(result[3]['family_tests'],1)

    def test_paired_zero_and_single_seed_cases(self):
        self.assertEqual(reports.paired([0.]*10)['p_raw'],1.)
        self.assertIsNone(reports.paired([.3])['p_raw'])
        self.assertEqual(reports.paired([1.,2.,3.])['mean'],2.)

    def test_phase_windows_exclude_warmup_and_both_transitions(self):
        p=study.protocol('smoke');windows=[]
        for start,end in [(130,190),(190,250),(310,370),(370,430),(430,490),(490,550)]:
            windows.append(dict(job='j',group='adaptation',label='SCOPE',load=900,iteration=3491,
                window_start=start,window_end=end,Completed=9,Failed=1,MeanService=.5))
        rows=reports.phase_rows(None,p,windows)
        self.assertEqual([r['phase'] for r in rows],['before','increase','recovery'])
        self.assertTrue(all(r['app_windows']==1 and r['failure_pct']==10 and r['service_seconds']==.5 for r in rows))

    def test_confirmatory_families_have_fixed_sizes(self):
        p=study.protocol('full');rows=[]
        for j in study.evaluation_specs(p):
            rows.append(dict(group=j['group'],label=j['label'],load=j['load'],iteration=j['iteration'],
                application='ALL_APPS',failure_pct=(j['iteration']%10)*.01,service_seconds=.5))
        result=reports.contrasts(rows,p)
        self.assertEqual(len(result),58)
        self.assertEqual({r['family']:r['family_tests'] for r in result},{'main':50,'ablation':6,'adaptation':2})
        self.assertTrue(all(r['n']==10 and r['mean']==0 and r['p_holm']==1 for r in result))


if __name__=='__main__':unittest.main()
