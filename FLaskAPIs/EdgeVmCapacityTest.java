import java.util.*;
import edu.boun.edgecloudsim.applications.sample_app5.EdgeVmSelector;

public class EdgeVmCapacityTest {
    static class V { double load; V(double value) { load = value; } }
    static V pick(List<V> v, V planned, double demand) {
        return EdgeVmSelector.select(v, planned, x -> x.load, x -> 0,
                .5, .5, 85, demand, new Random(1));
    }
    static void check(boolean value, String message) {
        if (!value) throw new AssertionError(message);
    }
    public static void main(String[] args) {
        V busy = new V(80), fits = new V(60);
        List<V> all = Arrays.asList(busy, fits);
        check(pick(all, null, 40) == fits, "80+40 rejected; 60+40 fits");
        check(pick(all, busy, 40) == fits, "Insufficient planned VM must be reselected");
        check(pick(all, fits, 40) == fits, "Exact-fit planned VM retained");
        check(pick(all, null, 41) == null, "No feasible VM must return null");
        check(pick(Collections.singletonList(busy), busy, 20) == busy,
                "Projected load may exceed threshold but must fit physical capacity");
        check(pick(all, fits, Double.NaN) == null, "NaN demand rejected");
        check(pick(all, fits, -1) == null, "Negative demand rejected");
        check(pick(all, fits, Double.POSITIVE_INFINITY) == null, "Infinite demand rejected");
        System.out.println("PASS: eight task-capacity regression checks");
    }
}
