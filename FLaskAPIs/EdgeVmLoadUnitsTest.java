package edu.boun.edgecloudsim.applications.sample_app5;

import java.util.List;
import java.util.Random;
import org.cloudbus.cloudsim.CloudletSchedulerTimeShared;
import edu.boun.edgecloudsim.edge_server.EdgeVM;

/** Exercises the production load adapter, which the generic selector tests omit. */
public class EdgeVmLoadUnitsTest {
    public static void main(String[] args) {
        for (double percent : new double[]{6, 20, 40, 85}) {
            CloudletSchedulerTimeShared scheduler = new CloudletSchedulerTimeShared() {
                @Override public double getTotalUtilizationOfCpu(double time) {
                    return percent;
                }
            };
            EdgeVM vm = new EdgeVM(0, 0, 1000, 1, 1024, 1000, 1000, "test", scheduler);
            double measured = VehicularEdgeOrchestrator.edgeVmLoadPercent(vm, 0);
            if (measured != percent) throw new AssertionError("CPU percentage rescaled: " + measured);
            EdgeVM selected = EdgeVmSelector.select(List.of(vm), null,
                v -> VehicularEdgeOrchestrator.edgeVmLoadPercent(v, 0),
                v -> 0, .5, .5, 85, 0, new Random(1));
            if ((selected != null) != (percent < 85))
                throw new AssertionError("Wrong eligibility at " + percent + "%");
        }
        System.out.println("PASS: production load adapter preserves 6/20/40/85 percent");
    }
}
