package edu.boun.edgecloudsim.applications.sample_app5;

/** Optional, policy-independent arrival-rate steps for paired diagnostic runs. */
public final class ArrivalRateSchedule {
    private final double shiftSeconds;
    private final double multiplier;
    private double recoverySeconds = Double.POSITIVE_INFINITY;

    public ArrivalRateSchedule(double shiftSeconds, double multiplier) {
        if (!Double.isFinite(shiftSeconds) || shiftSeconds <= 0
                || !Double.isFinite(multiplier) || multiplier <= 0) {
            throw new IllegalArgumentException("Arrival shift and multiplier must be finite and positive");
        }
        this.shiftSeconds = shiftSeconds;
        this.multiplier = multiplier;
    }

    public static ArrivalRateSchedule fromProperties(double simulationSeconds) {
        return fromProperties(simulationSeconds, 1)[0];
    }

    public static ArrivalRateSchedule[] fromProperties(double simulationSeconds, int applications) {
        if (applications <= 0) throw new IllegalArgumentException("Application count must be positive");
        String shift = System.getProperty("scope.workload.shiftSeconds");
        String rate = System.getProperty("scope.workload.rateMultiplier");
        String perApp = System.getProperty("scope.workload.appRateMultipliers");
        String recovery = System.getProperty("scope.workload.recoverySeconds");
        ArrivalRateSchedule[] schedules = new ArrivalRateSchedule[applications];
        if (shift == null && rate == null && perApp == null) {
            if (recovery != null) throw new IllegalArgumentException("Recovery requires a workload shift");
            for (int app = 0; app < applications; app++) {
                schedules[app] = new ArrivalRateSchedule(simulationSeconds, 1.0);
            }
            return schedules;
        }
        if (shift == null || (rate == null) == (perApp == null)) {
            throw new IllegalArgumentException("Set scope.workload.shiftSeconds and exactly one of "
                    + "scope.workload.rateMultiplier or scope.workload.appRateMultipliers");
        }
        double shiftSeconds = Double.parseDouble(shift);
        if (shiftSeconds >= simulationSeconds) {
            throw new IllegalArgumentException("Arrival shift must precede simulation end");
        }
        double recoverySeconds = recovery == null ? Double.POSITIVE_INFINITY : Double.parseDouble(recovery);
        if (recovery != null && (!Double.isFinite(recoverySeconds) || recoverySeconds <= shiftSeconds
                || recoverySeconds >= simulationSeconds))
            throw new IllegalArgumentException("Recovery must follow shift and precede simulation end");
        String[] rates = perApp == null ? null : perApp.split(",", -1);
        if (rates != null && rates.length != applications) {
            throw new IllegalArgumentException("Provide one arrival multiplier for each application in XML order");
        }
        for (int app = 0; app < applications; app++) {
            schedules[app] = new ArrivalRateSchedule(shiftSeconds,
                    Double.parseDouble(rates == null ? rate : rates[app].trim()));
            schedules[app].recoverySeconds = recoverySeconds;
        }
        return schedules;
    }

    /** Integrate a sampled baseline exponential interval across the rate step.
     * Active/idle period boundaries are still handled by the original generator.
     */
    public double nextArrival(double time, double baselineInterval) {
        if (multiplier == 1.0 || time + baselineInterval <= shiftSeconds) {
            return time + baselineInterval;
        }
        if (Double.isFinite(recoverySeconds)) {
            if (time >= recoverySeconds) return time + baselineInterval;
            double start = Math.max(time, shiftSeconds);
            double remaining = baselineInterval - Math.max(0, shiftSeconds-time);
            double burstEnd = start + remaining / multiplier;
            return burstEnd <= recoverySeconds ? burstEnd
                    : recoverySeconds + remaining - (recoverySeconds-start)*multiplier;
        }
        if (time >= shiftSeconds) {
            return time + baselineInterval / multiplier;
        }
        return shiftSeconds + (baselineInterval - (shiftSeconds - time)) / multiplier;
    }
}
