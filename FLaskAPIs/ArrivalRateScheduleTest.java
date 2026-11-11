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
        System.setProperty("scope.workload.shiftSeconds", "10");
        System.setProperty("scope.workload.appRateMultipliers", "0.5,2,1");
        ArrivalRateSchedule[] schedules = ArrivalRateSchedule.fromProperties(100, 3);
        equal(schedules[0].nextArrival(9, 3), 14);
        equal(schedules[1].nextArrival(9, 3), 11);
        equal(schedules[2].nextArrival(9, 3), 12);
        equal(schedules[0].nextArrival(3, 2), 5);
        equal(schedules[1].nextArrival(3, 2), 5);
        equal(schedules[2].nextArrival(3, 2), 5);
        int invalid = 0;
        for (String rates : new String[]{"1,2", "1,2,3,4", "1,0,1", "1,NaN,1", "1,Infinity,1", "1,,1"}) {
            System.setProperty("scope.workload.appRateMultipliers", rates);
            try { ArrivalRateSchedule.fromProperties(100, 3); }
            catch (IllegalArgumentException expected) { invalid++; }
        }
        System.setProperty("scope.workload.appRateMultipliers", "1,1,1");
        System.setProperty("scope.workload.rateMultiplier", "1");
        try { ArrivalRateSchedule.fromProperties(100, 3); }
        catch (IllegalArgumentException expected) { invalid++; }
        System.clearProperty("scope.workload.rateMultiplier");
        System.clearProperty("scope.workload.shiftSeconds");
        try { ArrivalRateSchedule.fromProperties(100, 3); }
        catch (IllegalArgumentException expected) { invalid++; }
        System.clearProperty("scope.workload.appRateMultipliers");
        if (invalid != 8) throw new AssertionError("Invalid application schedules accepted");
        for (ArrivalRateSchedule schedule : ArrivalRateSchedule.fromProperties(100, 3)) {
            equal(schedule.nextArrival(9, 3), 12);
        }
        System.out.println("Arrival schedule: common/app-specific timing and invalid-setting checks passed");
    }
}
