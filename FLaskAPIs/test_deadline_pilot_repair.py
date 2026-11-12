"""Regression checks for static-wire interoperability and checkpoint-preserving repair."""
import itertools
import math
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import run_deadline_pilot as pilot


class StaticWireTests(unittest.TestCase):
    def test_valid_endpoints_parse_in_java_without_changing_candidate(self):
        java=shutil.which('java')
        if not java:self.skipTest('JDK required for Java interoperability test')
        with tempfile.TemporaryDirectory() as tmp:
            out=Path(tmp)
            source=out/'WireCheck.java'
            source.write_text('''
import java.nio.file.*;
import edu.boun.edgecloudsim.applications.sample_app5.OptimizerReply;
public class WireCheck {
  public static void main(String[] args) throws Exception {
    String old = "ALPHA:0.65|0:0.9:0.09999999999999998:85.0|1:0.3:0.7:65.0|2:0.7:0.30000000000000004:75.0";
    try { OptimizerReply.parse(old); throw new AssertionError("Expected original crash"); }
    catch (IllegalArgumentException expected) { }
    for (String line : Files.readAllLines(Path.of(args[0]))) {
      String[] pair = line.split("\\t");
      OptimizerReply r = OptimizerReply.parse(pair[0]);
      String[] expected = pair[1].split(",");
      if (r.alpha != Double.parseDouble(expected[0])) throw new AssertionError("alpha changed");
      for (int i=0; i<3; i++) {
        if (r.weights[i] != Double.parseDouble(expected[i+1])) throw new AssertionError("weight changed");
        if (r.thresholds[i] != Double.parseDouble(expected[i+4])) throw new AssertionError("threshold changed");
      }
    }
  }
}
''')
            vectors=[]
            for a,w,t in itertools.product([.05,.6,.95],itertools.product([.1,.5,.9],repeat=3),itertools.product([20,95],repeat=3)):
                values=[a,*w,*t]
                vectors.append(pilot.wire(values)+'\t'+','.join(map(str,values)))
            values=[.65,.9,.3,.7,85,65,75]  # Candidate that stopped full calibration.
            vectors.append(pilot.wire(values)+'\t'+','.join(map(str,values)))
            data=out/'vectors.txt';data.write_text('\n'.join(vectors))
            parser=pilot.REPO/'ThreeBrains/src/edu/boun/edgecloudsim/applications/sample_app5/OptimizerReply.java'
            compiled=subprocess.run([java,'-m','jdk.compiler/com.sun.tools.javac.Main','-d',str(out),str(parser),str(source)],capture_output=True,text=True)
            self.assertEqual(compiled.returncode,0,compiled.stderr)
            result=subprocess.run([java,'-cp',str(out),'WireCheck',str(data)],capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stderr)

    def test_real_out_of_range_candidates_still_fail(self):
        for weight in [math.nextafter(.9,1),math.nextafter(.1,0),float('nan'),float('inf'),-1]:
            values=[.65,weight,.3,.7,85,65,75]
            with self.assertRaisesRegex(RuntimeError,'Invalid static configuration'):pilot.wire(values)


class RepairTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.out=Path(self.tmp.name)
        old=self.out/'runtime/services/run_deadline_pilot.py';old.parent.mkdir(parents=True)
        old.write_text('original runner fixture\n')
        self.base_sha=pilot.sha(old)
        patcher=patch.object(pilot,'STATIC_WIRE_BASE_SHA',self.base_sha)
        patcher.start();self.addCleanup(patcher.stop)
        plan=pilot.protocol('smoke')
        plan.update(runner_sha=self.base_sha,input_hashes={str(old.relative_to(self.out)):self.base_sha})
        pilot.write(self.out/'study.json',plan)
        (self.out/'study_checksum.txt').write_text(pilot.sha(self.out/'study.json')+'\n')
        self.plan=pilot.load_plan(self.out)
        for key in ['collect_i3001_n900','train','tune_c0_i3201_n900']:
            folder=pilot.attempt(self.out,key);(folder/'evidence').write_text(key)
            pilot.receipt(self.out,key,folder,{'key':key})
        pilot.write(self.out/'static_shortlist.json',{'900':[pilot.INITIAL]})
        (self.out/'static_shortlist_checksum.txt').write_text(pilot.sha(self.out/'static_shortlist.json'))
        failed=pilot.attempt(self.out,'tune_c2_i3201_n900')
        (failed/'java.log').write_text('Original failure retained')

    def test_register_preserves_every_original_byte_and_retries_new_attempt(self):
        before=pilot.hashes(self.out)
        with self.assertRaisesRegex(RuntimeError,'Runner changed'):pilot.verify_runner(self.out,self.plan)
        pilot.repair_static_wire(self.out,self.plan)
        pilot.verify(self.out,before);pilot.verify_runner(self.out,self.plan)
        record=pilot.read(self.out/pilot.STATIC_WIRE_REPAIR/'repair.json')
        self.assertEqual(record['completed_jobs_preserved'],3)
        after=pilot.hashes(self.out)
        pilot.repair_static_wire(self.out,self.plan)
        self.assertEqual(pilot.hashes(self.out),after)
        with patch.object(pilot,'attempt',side_effect=AssertionError('Completed job rerun')):
            self.assertEqual(pilot.simulation(self.out,self.plan,'collect_i3001_n900','unused',0,0),{'key':'collect_i3001_n900'})
            pilot.train(self.out,self.plan,None)
        self.assertEqual(pilot.attempt(self.out,'tune_c2_i3201_n900').name,'attempt_002')

    def test_changed_frozen_input_is_rejected(self):
        (self.out/'runtime/services/run_deadline_pilot.py').write_text('changed')
        with self.assertRaisesRegex(RuntimeError,'Changed or missing'):pilot.repair_static_wire(self.out,self.plan)

    def test_changed_completed_data_is_rejected(self):
        (self.out/'jobs/train/attempt_001/evidence').write_text('changed')
        with self.assertRaisesRegex(RuntimeError,'Changed or missing'):pilot.repair_static_wire(self.out,self.plan)
        self.assertFalse((self.out/pilot.STATIC_WIRE_REPAIR/'repair.json').exists())

    def test_changed_shortlist_is_rejected(self):
        pilot.write(self.out/'static_shortlist.json',{})
        with self.assertRaisesRegex(RuntimeError,'shortlist changed'):pilot.repair_static_wire(self.out,self.plan)

    def test_unknown_original_runner_is_rejected(self):
        plan=dict(self.plan,runner_sha='unknown')
        with self.assertRaisesRegex(RuntimeError,'only supports'):pilot.repair_static_wire(self.out,plan)

    def test_registration_does_not_authorize_later_runner_changes(self):
        pilot.repair_static_wire(self.out,self.plan)
        original_sha=pilot.sha
        with patch.object(pilot,'sha',side_effect=lambda p:'different' if Path(p)==Path(pilot.__file__) else original_sha(p)):
            with self.assertRaisesRegex(RuntimeError,'does not match'):pilot.verify_runner(self.out,self.plan)

    def test_registered_evidence_cannot_be_rewritten(self):
        pilot.repair_static_wire(self.out,self.plan)
        (self.out/'jobs/train/complete.json').write_text('{}')
        with self.assertRaisesRegex(RuntimeError,'Changed or missing'):pilot.verify_runner(self.out,self.plan)

    def test_interrupt_before_record_keeps_original_study_resumable(self):
        before=pilot.hashes(self.out)
        with patch.object(pilot,'write',side_effect=pilot.Stopped('interrupted before atomic record')):
            with self.assertRaises(pilot.Stopped):pilot.repair_static_wire(self.out,self.plan)
        pilot.verify(self.out,before)
        self.assertFalse((self.out/pilot.STATIC_WIRE_REPAIR/'repair.json').exists())
        pilot.repair_static_wire(self.out,self.plan);pilot.verify_runner(self.out,self.plan)

    def test_new_study_needs_no_registration(self):
        plan=dict(self.plan,runner_sha=pilot.sha(pilot.__file__))
        pilot.repair_static_wire(self.out,plan);pilot.verify_runner(self.out,plan)
        self.assertFalse((self.out/pilot.STATIC_WIRE_REPAIR).exists())


if __name__=='__main__':unittest.main()
