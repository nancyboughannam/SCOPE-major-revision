package edu.boun.edgecloudsim.applications.sample_app5;

/** Validate the complete wire response before changing any simulator state. */
public final class OptimizerReply {
    public final double alpha;
    public final double[] weights;
    public final double[] thresholds;

    private OptimizerReply(double alpha, double[] weights, double[] thresholds) {
        this.alpha = alpha;
        this.weights = weights;
        this.thresholds = thresholds;
    }

    private static double number(String text, double low, double high) {
        double value = Double.parseDouble(text);
        if (!Double.isFinite(value) || value < low || value > high)
            throw new IllegalArgumentException("Optimizer value outside [" + low + "," + high + "]");
        return value;
    }

    public static OptimizerReply parse(String response) {
        if (response == null) throw new IllegalArgumentException("Empty optimizer response");
        String value = response.trim();
        // Flask's EXP3 endpoint returns a JSON string; SCOPE returns plain text.
        if (value.startsWith("\"") && value.endsWith("\""))
            value = value.substring(1, value.length() - 1);
        if (value.endsWith("|")) value = value.substring(0, value.length() - 1);
        double alpha = Double.NaN;
        double[] weights = new double[3], thresholds = new double[3];
        boolean[] seen = new boolean[3];
        for (String section : value.split("\\|", -1)) {
            String[] parts = section.split(":", -1);
            if (parts.length == 2 && parts[0].equals("ALPHA")) {
                if (Double.isFinite(alpha)) throw new IllegalArgumentException("Duplicate alpha");
                alpha = number(parts[1], .05, .95);
            } else if (parts.length == 4) {
                int app = Integer.parseInt(parts[0]);
                if (app < 0 || app >= 3 || seen[app])
                    throw new IllegalArgumentException("Invalid/duplicate application");
                weights[app] = number(parts[1], .1, .9);
                double distanceWeight = number(parts[2], .1, .9);
                if (Math.abs(weights[app] + distanceWeight - 1) > 1e-8)
                    throw new IllegalArgumentException("Weights must sum to one");
                thresholds[app] = number(parts[3], 20, 95);
                seen[app] = true;
            } else throw new IllegalArgumentException("Malformed optimizer response");
        }
        if (!Double.isFinite(alpha) || !seen[0] || !seen[1] || !seen[2])
            throw new IllegalArgumentException("Incomplete optimizer response");
        return new OptimizerReply(alpha, weights, thresholds);
    }

    public static double distance(double firstAlpha, double[] firstWeights, double[] firstThresholds,
                                  double secondAlpha, double[] secondWeights, double[] secondThresholds) {
        double sum = Math.abs(firstAlpha - secondAlpha) / .9;
        for (int i = 0; i < 3; i++) {
            sum += Math.abs(firstWeights[i] - secondWeights[i]) / .8;
            sum += Math.abs(firstThresholds[i] - secondThresholds[i]) / 75;
        }
        return sum / 7;
    }
}
