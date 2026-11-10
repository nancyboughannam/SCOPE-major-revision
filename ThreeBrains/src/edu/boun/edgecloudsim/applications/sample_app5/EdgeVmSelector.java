package edu.boun.edgecloudsim.applications.sample_app5;

import java.util.List;
import java.util.Random;
import java.util.function.ToDoubleFunction;

/** Shared selection rule for SCOPE, EXP3 and RAIDER_TRAX. Loads are percentages. */
public final class EdgeVmSelector {
    private EdgeVmSelector() { }

    public static <T> T select(List<T> candidates, T planned,
            ToDoubleFunction<T> load, ToDoubleFunction<T> distance,
            double wLoad, double wDist, double threshold, double requiredCapacity, Random random) {
        // Preserve the original decision if still eligible after upload.
        if (planned != null && candidates.contains(planned)
                && eligible(load.applyAsDouble(planned), threshold, requiredCapacity)) return planned;
        T best = null;
        double bestScore = Double.POSITIVE_INFINITY;
        for (T candidate : candidates) {
            double currentLoad = load.applyAsDouble(candidate);
            if (!eligible(currentLoad, threshold, requiredCapacity)) continue;
            double d = distance.applyAsDouble(candidate);
            if (!Double.isFinite(d) || d < 0) continue;
            double score = wDist * d / 1000.0 + wLoad * currentLoad / 100.0
                    + random.nextDouble() * 0.1;
            if (score < bestScore) { bestScore = score; best = candidate; }
        }
        // Existing device manager treats null as a capacity rejection.
        return best;
    }

    private static boolean eligible(double load, double threshold, double requiredCapacity) {
        // Match the simulator's admission check: equality with remaining capacity fits.
        // Keep the policy threshold on CURRENT load, not projected load.
        return Double.isFinite(load) && load >= 0 && load <= 100
                && Double.isFinite(requiredCapacity) && requiredCapacity >= 0
                && load < threshold && requiredCapacity <= 100.0 - load;
    }
}
