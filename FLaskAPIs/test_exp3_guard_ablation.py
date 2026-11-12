"""The routing variant must not alter SCOPE or EXP3 learning configuration."""
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import run_exp3_guard_ablation as ablation
import run_confirmatory_study as study


class GuardAblationTests(unittest.TestCase):
    def test_exactly_fifty_exp3_pairs_keep_all_original_controls(self):
        p = study.protocol('full')
        p['exp3_routing_schema'] = 'edge_first_v1'
        jobs = ablation.jobs(p)
        self.assertEqual(len(jobs), 50)
        self.assertEqual({(j['load'],j['iteration']) for j in jobs},
                         {(n,i) for n in p['loads'] for i in p['iterations']})
        self.assertTrue(all(j['label'] == 'EXP3_MC' and j['group'] == 'main' for j in jobs))
        self.assertEqual(len(study.evaluation_specs(p)), 400)
        self.assertIn('SCOPE_STATIC', p['main_policies'])

    def test_legacy_studies_still_use_guard_and_only_exp3_can_disable_it(self):
        p = study.protocol('full')
        self.assertEqual(study.routing_schema(p, 'EXP3_MC'), 'deadline_guard_v1')
        p['exp3_routing_schema'] = 'edge_first_v1'
        self.assertEqual(study.routing_schema(p, 'EXP3_MC'), 'edge_first_v1')
        for policy in ['SCOPE','SOFTCOST_OPT','PERFORMANCE_ONLY','SCOPE_STATIC']:
            self.assertEqual(study.routing_schema(p, policy), 'deadline_guard_v1')
        p['exp3_routing_schema'] = 'anything'
        with self.assertRaisesRegex(RuntimeError, 'Unsupported'):
            study.routing_schema(p, 'EXP3_MC')

    def test_normalization_override_does_not_change_any_other_service_setting(self):
        p = study.protocol('full')
        job = study.spec('main','EXP3_MC',900,3401)
        out = Path('/out')
        with patch.dict('os.environ',{'EXP3_MC_ETA':'999','JAVA_TOOL_OPTIONS':'bad'}):
            old = study.service_environment(out,out/'job',p,job)
            p.update(exp3_routing_schema='edge_first_v1',
                     exp3_normalization_manifest='inputs/exp3_edge_first_normalization.json')
            new = study.service_environment(out,out/'job',p,job)
        self.assertEqual({k for k in old if old[k] != new[k]}, {'EXP3_MC_NORMALIZATION_MANIFEST'})
        self.assertNotIn('EXP3_MC_ETA', new)
        self.assertNotIn('JAVA_TOOL_OPTIONS', new)
        self.assertEqual(new['EXP3_MC_ARM_COUNT'], '0')
        self.assertEqual(new['EXP3_MC_QOS_THRESHOLD'], '0.2')
        self.assertEqual(new['SCOPE_LAMBDA'], '0.01')

    def test_tampered_protocol_is_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            out=Path(d)
            ablation.core.write(out/'study.json',dict(workflow=ablation.WORKFLOW))
            (out/'study_checksum.txt').write_text(ablation.core.sha(out/'study.json'))
            ablation.load_plan(out)
            ablation.core.write(out/'study.json',dict(workflow=ablation.WORKFLOW,exp3_routing_schema='bad'))
            with self.assertRaisesRegex(RuntimeError,'Frozen protocol changed'):
                ablation.load_plan(out)


if __name__ == '__main__':
    unittest.main()
