"""Focused controls/protocol tests; native paired/abort checks are documented separately."""
import math
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import run_deadline_pilot as core
import run_lambda_check as check
from scope_lambda_service import FreezeControl


def request(time,iteration=3301):
    return dict(timestamp=time,iteration=iteration,simulation_seed=20264129,
                num_devices=1200,policy='SCOPE',run_id='iteration_'+str(iteration))


class FreezeTests(unittest.TestCase):
    def test_follows_history_then_freezes_existing_configuration(self):
        c=FreezeControl(1200)
        self.assertFalse(c.observe(request(70),[.6,.5]))
        self.assertFalse(c.observe(request(1150),[.8,.7]))
        self.assertTrue(c.observe(request(1210),[.75,.9]))
        self.assertEqual(c.frozen,(.75,.9))
        self.assertTrue(c.observe(request(1270),[.75,.9]))
        self.assertTrue(c.observe(request(2470),[.75,.9]))

    def test_freezes_at_exact_cutoff(self):
        c=FreezeControl(1200);c.observe(request(70),[.6])
        self.assertTrue(c.observe(request(1200),[.8]))

    def test_unfrozen_mode_never_blocks_configuration_changes(self):
        c=FreezeControl()
        for time,config in [(70,[.6]),(1210,[.8]),(2470,[.4])]:self.assertFalse(c.observe(request(time),config))
        self.assertIsNone(c.frozen)

    def test_changed_frozen_action_is_rejected(self):
        c=FreezeControl(1200);c.observe(request(70),[.6]);c.observe(request(1210),[.8])
        with self.assertRaisesRegex(ValueError,'changed after'):c.observe(request(1270),[.9])

    def test_late_start_and_mixed_simulations_are_rejected(self):
        with self.assertRaisesRegex(ValueError,'no pre-cutoff'):FreezeControl(1200).observe(request(1210),[.8])
        c=FreezeControl(1200);c.observe(request(70),[.6])
        with self.assertRaisesRegex(ValueError,'exactly one'):c.observe(request(130,3302),[.6])

    def test_duplicate_invalid_times_and_wrong_policy_rejected(self):
        for time in [70,69,float('nan'),float('inf')]:
            c=FreezeControl();c.observe(request(70),[.6])
            with self.assertRaisesRegex(ValueError,'request time'):c.observe(request(time),[.6])
        q=request(70);q['policy']='PERFORMANCE_ONLY'
        with self.assertRaisesRegex(ValueError,'hard bound'):FreezeControl().observe(q,[.6])

    def test_invalid_cutoffs_rejected(self):
        for cutoff in [0,-1,float('nan'),float('inf')]:
            with self.assertRaises(ValueError):FreezeControl(cutoff)


class WorkflowTests(unittest.TestCase):
    def test_full_plan_has_27_cases_with_nine_matched_pairs(self):
        plan=check.protocol('pilot');jobs=check.job_specs(plan)
        self.assertEqual(len(jobs),27);self.assertEqual(len({j['key'] for j in jobs}),27)
        self.assertEqual(plan['r_max'],.15);self.assertEqual(plan['lambdas'],[0.,.01,.05])
        self.assertEqual(len([j for j in jobs if j['case']=='steady']),9)
        for j in jobs:
            if j['variant']=='frozen':
                before=[x for x in jobs if x['key']==j['key'].replace('_frozen_','_adaptive_')]
                self.assertEqual(len(before),1)
                self.assertLess(jobs.index(before[0]),jobs.index(j))

    def test_new_seeds_do_not_reuse_source_or_old_final_runs(self):
        old=core.protocol('pilot');used=set(old['collection_iterations']+old['tuning_iterations']+old['pilot_iterations']+list(range(2001,2011)))
        for profile in ['smoke','pilot']:self.assertFalse(set(check.protocol(profile)['iterations']) & used)
        self.assertFalse(set(check.protocol('smoke')['iterations']) & set(check.protocol('pilot')['iterations']))

    def test_source_cannot_be_output_or_nested(self):
        source=Path('/a/study')
        for out in [source,source/'new',source.parent]:
            with self.assertRaisesRegex(RuntimeError,'non-nested'):check.check_location(source,out)
        check.check_location(source,Path('/a/new_study'))

    def test_lambda_zero_keeps_bound_and_removes_inherited_override(self):
        with patch.dict('os.environ',{'SCOPE_LAMBDA':'.9','SCOPE_R_MAX':'.8','SCOPE_FREEZE_AFTER_SECONDS':'123'}):
            e=check.service_env(Path('/out'),Path('/out/job'),0.,None)
        self.assertEqual(e['SCOPE_LAMBDA'],'0.0');self.assertEqual(e['SCOPE_R_MAX'],'.15')
        self.assertEqual(e['SCOPE_HARD_STABILITY'],'1');self.assertNotIn('SCOPE_FREEZE_AFTER_SECONDS',e)
        self.assertEqual(check.service_env(Path('/o'),Path('/o/j'),.01,1200)['SCOPE_FREEZE_AFTER_SECONDS'],'1200')

    def test_changed_plan_is_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            out=Path(d);core.write(out/'study.json',check.protocol('pilot'))
            (out/'study_checksum.txt').write_text(core.sha(out/'study.json'))
            self.assertEqual(check.load_plan(out)['lambdas'],[0.,.01,.05])
            p=core.read(out/'study.json');p['r_max']=.9;core.write(out/'study.json',p)
            with self.assertRaisesRegex(RuntimeError,'settings changed'):check.load_plan(out)

    def test_completed_job_cannot_be_reused_for_another_lambda(self):
        with tempfile.TemporaryDirectory() as d:
            out=Path(d);plan=check.protocol('pilot');spec=check.job_specs(plan)[0]
            folder=core.attempt(out,spec['key']);core.receipt(out,spec['key'],folder,dict(spec=dict(spec,lambda_value=.05)))
            with self.assertRaisesRegex(RuntimeError,'different settings'):check.simulate(out,plan,spec)


if __name__=='__main__':unittest.main()
