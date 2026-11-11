"""JDK selection regressions, without requiring multiple installed JDKs."""
import subprocess
import unittest
from unittest.mock import patch

import run_adaptation_check as runner


class JavaSelectionTest(unittest.TestCase):
    def select(self, versions, explicit=None):
        def probe(command, **kwargs):
            version = versions[command[0]]
            return subprocess.CompletedProcess(command, 0 if version else 1,
                                               'javac '+version if version else '', '')
        with patch.object(runner, 'java_candidates', return_value=list(versions)), \
             patch.object(runner.subprocess, 'run', side_effect=probe):
            return runner.select_java(explicit)

    def test_skips_path_java17_for_compatible_jdk(self):
        java, major = self.select({'/jdk17/bin/java':'17.0.15', '/jdk21/bin/java':'21.0.6'})
        self.assertEqual((java, major), ('/jdk21/bin/java', 21))

    def test_accepts_newer_jdk(self):
        self.assertEqual(self.select({'/jdk25/bin/java':'25.0.1'})[1], 25)

    def test_missing_compiler_is_not_selected(self):
        self.assertEqual(self.select({'/jre/bin/java':None, '/jdk21/bin/java':'21'})[1], 21)

    def test_java17_only_has_actionable_error(self):
        with self.assertRaisesRegex(ValueError, 'requires JDK 21'):
            self.select({'/jdk17/bin/java':'17.0.15'})

    def test_explicit_choice_is_only_candidate(self):
        self.assertEqual(runner.java_candidates('/selected/bin/java'), ['/selected/bin/java'])
        with self.assertRaisesRegex(ValueError, 'requires JDK 21'):
            self.select({'/selected/bin/java':'17.0.15'}, explicit='/selected/bin/java')

    def test_unavailable_executable(self):
        with patch.object(runner, 'java_candidates', return_value=['/missing/java']), \
             patch.object(runner.subprocess, 'run', side_effect=FileNotFoundError):
            with self.assertRaisesRegex(ValueError, 'executable unavailable'):
                runner.select_java()


if __name__ == '__main__':
    unittest.main()
