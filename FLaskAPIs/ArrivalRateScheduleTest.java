import edu.boun.edgecloudsim.applications.sample_app5.ArrivalRateSchedule;

public class ArrivalRateScheduleTest {
    private static void equal(double actual, double expected) {
        if (Math.abs(actual - expected) > 1e-12) throw new AssertionError(actual + " != " + expected);
    }
    public static void main(String[] args) {
        ArrivalRateSchedule doubled = new ArrivalRateSchedule(10, 2);
        equal(doubled.nextArrival(3, 2), 5);
        equal(doubled.nextArrival(8, 2), 10);
        equal(doubled.nextArrival(9, 3), 11);
        equal(doubled.nextArrival(10, 4), 12);
        equal(doubled.nextArrival(12, 4), 14);
        equal(new ArrivalRateSchedule(10, .5).nextArrival(9, 3), 14);
        equal(new ArrivalRateSchedule(10, 1).nextArrival(9, 3), 12);
        equal(ArrivalRateSchedule.fromProperties(100).nextArrival(9, 3), 12);
        int rejected = 0;
        for (double rate : new double[]{0, -1, Double.NaN, Double.POSITIVE_INFINITY}) {
            try { new ArrivalRateSchedule(10, rate); }
            catch (IllegalArgumentException expected) { rejected++; }
        }
        System.setProperty("scope.workload.shiftSeconds", "10");
        try { ArrivalRateSchedule.fromProperties(100); }
        catch (IllegalArgumentException expected) { rejected++; }
        System.setProperty("scope.workload.rateMultiplier", "1.5");
        equal(ArrivalRateSchedule.fromProperties(100).nextArrival(9, 4), 12);
        try { ArrivalRateSchedule.fromProperties(5); }
        catch (IllegalArgumentException expected) { rejected++; }
        System.clearProperty("scope.workload.shiftSeconds");
        System.clearProperty("scope.workload.rateMultiplier");
        if (rejected != 6) throw new AssertionError("Invalid schedules accepted");
        System.out.println("Arrival schedule: 9 timing checks and 6 invalid-setting checks passed");
    }
}
