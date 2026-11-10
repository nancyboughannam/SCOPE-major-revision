package edu.boun.edgecloudsim.applications.sample_app5;

/** Optional, policy-independent arrival-rate step for paired diagnostic runs. */
public final class ArrivalRateSchedule {
    private final double shiftSeconds;
    private final double multiplier;

    public ArrivalRateSchedule(double shiftSeconds, double multiplier) {
        if (!Double.isFinite(shiftSeconds) || shiftSeconds <= 0
                || !Double.isFinite(multiplier) || multiplier <= 0) {
            throw new IllegalArgumentException("Arrival shift and multiplier must be finite and positive");
        }
        this.shiftSeconds = shiftSeconds;
        this.multiplier = multiplier;
    }

    public static ArrivalRateSchedule fromProperties(double simulationSeconds) {
        String shift = System.getProperty("scope.workload.shiftSeconds");
        String rate = System.getProperty("scope.workload.rateMultiplier");
        if (shift == null && rate == null) {
            return new ArrivalRateSchedule(simulationSeconds, 1.0);
        }
        if (shift == null || rate == null) {
            throw new IllegalArgumentException("Set both scope.workload.shiftSeconds and scope.workload.rateMultiplier");
        }
        ArrivalRateSchedule schedule = new ArrivalRateSchedule(
                Double.parseDouble(shift), Double.parseDouble(rate));
        if (schedule.shiftSeconds >= simulationSeconds) {
            throw new IllegalArgumentException("Arrival shift must precede simulation end");
        }
        return schedule;
    }

    /** Integrate a sampled baseline exponential interval across the rate step.
     * Active/idle period boundaries are still handled by the original generator.
     */
    public double nextArrival(double time, double baselineInterval) {
        if (multiplier == 1.0 || time + baselineInterval <= shiftSeconds) {
            return time + baselineInterval;
        }
        if (time >= shiftSeconds) {
            return time + baselineInterval / multiplier;
        }
        return shiftSeconds + (baselineInterval - (shiftSeconds - time)) / multiplier;
    }
}
