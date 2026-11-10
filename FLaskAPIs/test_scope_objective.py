import unittest

import pandas as pd

from scope_objective import (CPU_FEATURES, CURRENT_TELEMETRY, LEGACY_SUPPORT,
                             check_telemetry, manifest_support, training_support, validate_support)


class ObjectiveTests(unittest.TestCase):
    def test_training_support(self):
        frame = pd.DataFrame({'target_failure_rate':[.0,.4,.8],
                              'target_deadline_norm_service_time':[.2,1.,2.9]})
        self.assertEqual(training_support(frame),
                         dict(failure_min=0.,failure_max=.8,dnst_min=.2,dnst_max=2.9))

    def test_legacy_reproduction(self):
        self.assertEqual(manifest_support({}), (LEGACY_SUPPORT,'legacy_reference'))

    def test_invalid_support(self):
        for change in ({'dnst_max':float('nan')}, {'failure_max':0.},
                       {'failure_max':1.1}, {'dnst_min':2.0}):
            with self.assertRaises(ValueError):
                validate_support(dict(LEGACY_SUPPORT, **change))

    def test_old_cpu_model_rejects_new_telemetry(self):
        manifest = {'models':[{'features':list(CPU_FEATURES)}]}
        check_telemetry(manifest, None)  # Historic simulator/model remains reproducible.
        with self.assertRaisesRegex(ValueError, 'CPU telemetry mismatch'):
            check_telemetry(manifest, CURRENT_TELEMETRY)

    def test_no_cpu_model_accepts_either_schema(self):
        manifest = {'telemetry_schema':'unused','models':[{'features':['num_devices']}]}
        check_telemetry(manifest, CURRENT_TELEMETRY)
        check_telemetry(manifest, None)

    def test_corrected_cpu_model_requires_corrected_simulator(self):
        manifest = {'telemetry_schema':CURRENT_TELEMETRY,
                    'models':[{'features':['state_avg_edge_cpu']}]}
        check_telemetry(manifest, CURRENT_TELEMETRY)
        with self.assertRaises(ValueError):
            check_telemetry(manifest, None)


if __name__ == '__main__':
    unittest.main()
