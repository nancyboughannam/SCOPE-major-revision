package edu.boun.edgecloudsim.applications.sample_app5;

/** Development probe only: optimistic processing bounds are NOT deadline guarantees. */
public final class DeadlineTierGuard {
    private DeadlineTierGuard() { }
    public static final int KEEP_EDGE = 0, RSU = 1, GSM = 2;

    public static int choose(double length, double edgeMips, double cloudMips,
            double deadline, double wlanUp, double wlanDown, double wanUp, double wanDown,
            double gsmUp, double gsmDown, double alpha, double draw) {
        if (!positive(length) || !positive(edgeMips) || !positive(cloudMips)
                || !positive(deadline) || length / edgeMips <= deadline) return KEEP_EDGE;
        double processing = length / cloudMips;
        boolean rsu = positive(wlanUp) && positive(wlanDown) && positive(wanUp) && positive(wanDown)
                && processing + wlanUp + wlanDown + wanUp + wanDown <= deadline;
        boolean gsm = positive(gsmUp) && positive(gsmDown)
                && processing + gsmUp + gsmDown <= deadline;
        if (rsu && gsm) return draw < alpha ? RSU : GSM;
        return rsu ? RSU : gsm ? GSM : KEEP_EDGE;
    }

    private static boolean positive(double x) { return Double.isFinite(x) && x > 0; }
}
