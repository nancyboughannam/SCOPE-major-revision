import edu.boun.edgecloudsim.applications.sample_app5.DeadlineTierGuard;
import edu.boun.edgecloudsim.applications.sample_app5.EdgeVmSelector;
import java.util.*;

public final class DeadlineTierGuardTest {
    static int n;
    static void check(boolean value, String message) {
        n++; if (!value) throw new AssertionError(message);
    }
    static int route(double length, double deadline, double wu, double wd,
            double au, double ad, double gu, double gd, double alpha, double draw) {
        return DeadlineTierGuard.choose(length, 10000, 75000, deadline,
                wu, wd, au, ad, gu, gd, alpha, draw);
    }
    public static void main(String[] args) {
        check(route(3000,.5,.02,.02,.02,.02,.02,.02,.7,.1)==0, "Keep timely edge task");
        check(route(10000,1,.02,.02,.02,.02,.02,.02,.7,.1)==0, "Boundary equals deadline");
        check(route(20000,1.5,.02,.02,.02,.02,.02,.02,.7,.1)==1, "Late edge, feasible RSU");
        check(route(20000,1.5,.02,.02,.02,.02,.02,.02,.7,.9)==2, "Alpha retains GSM choice");
        check(route(20000,1.5,.02,.02,.02,.02,0,.02,.7,.9)==1, "Unavailable GSM cannot be selected");
        check(route(20000,1.5,0,.02,.02,.02,.02,.02,.7,.1)==2, "RSU needs WLAN upload");
        check(route(20000,1.5,.02,0,.02,.02,.02,.02,.7,.1)==2, "RSU needs WLAN download");
        check(route(20000,1.5,.02,.02,0,.02,.02,.02,.7,.1)==2, "RSU needs WAN upload");
        check(route(20000,1.5,.02,.02,.02,0,.02,.02,.7,.1)==2, "RSU needs WAN download");
        check(route(20000,1.5,.02,.02,.02,.02,.02,0,.7,.9)==1, "GSM needs download");
        check(route(20000,1.5,0,.02,.02,.02,0,.02,.7,.1)==0, "Do not send to unavailable networks");
        check(route(20000,1.5,.5,.5,.5,.5,1,1,.7,.1)==0, "Neither cloud estimate meets deadline");
        check(route(200000,1.5,.02,.02,.02,.02,.02,.02,.7,.1)==0, "Cloud processing can itself be too late");
        check(route(Double.NaN,1.5,.02,.02,.02,.02,.02,.02,.7,.1)==0, "Invalid task size");
        check(route(20000,1.5,Double.NaN,.02,.02,.02,.02,.02,.7,.1)==2, "Invalid route excluded");
        check(route(20000,1.5,.02,.02,.02,.02,Double.POSITIVE_INFINITY,.02,.7,.9)==1, "Infinite delay excluded");
        List<Double> loads=List.of(30.0);
        check(EdgeVmSelector.select(loads,null,x->x,x->0,.5,.5,20,20,new Random(1))==null,
                "Original threshold may reject physically feasible task");
        check(EdgeVmSelector.select(loads,null,x->x,x->0,.5,.5,100,20,new Random(1))!=null,
                "Assignment fallback can recover physically feasible task");
        check(EdgeVmSelector.select(List.of(90.0),null,x->x,x->0,.5,.5,100,20,new Random(1))==null,
                "Fallback must still reject overload");
        check(EdgeVmSelector.select(List.of(80.0),null,x->x,x->0,.5,.5,100,20,new Random(1))!=null,
                "Fallback admits exact capacity fit");
        System.out.println("PASS: "+n+" deadline and assignment-capacity checks");
    }
}
