import edu.boun.edgecloudsim.applications.sample_app5.ArrivalRateSchedule;
public final class DeadlineRecoveryTest {
    static int n;
    static void check(double got,double want) {n++;if(Math.abs(got-want)>1e-10)throw new AssertionError(got+" != "+want);}
    public static void main(String[] args) {
        System.setProperty("scope.workload.shiftSeconds","100");
        System.setProperty("scope.workload.rateMultiplier","2");
        System.setProperty("scope.workload.recoverySeconds","200");
        ArrivalRateSchedule s=ArrivalRateSchedule.fromProperties(300);
        check(s.nextArrival(0,10),10);check(s.nextArrival(90,20),105);
        check(s.nextArrival(100,20),110);check(s.nextArrival(190,30),210);
        check(s.nextArrival(90,230),220);check(s.nextArrival(200,30),230);
        check(s.nextArrival(190,20),200);
        System.setProperty("scope.workload.rateMultiplier","0.5");
        s=ArrivalRateSchedule.fromProperties(300);check(s.nextArrival(190,10),205);
        System.clearProperty("scope.workload.recoverySeconds");
        s=ArrivalRateSchedule.fromProperties(300);check(s.nextArrival(190,10),210);
        System.setProperty("scope.workload.recoverySeconds","90");
        try {ArrivalRateSchedule.fromProperties(300);throw new AssertionError("Invalid recovery accepted");}
        catch(IllegalArgumentException expected) {n++;}
        System.out.println("PASS: "+n+" workload step/recovery checks");
    }
}
