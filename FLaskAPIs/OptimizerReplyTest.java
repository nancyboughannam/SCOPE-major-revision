import edu.boun.edgecloudsim.applications.sample_app5.OptimizerReply;

public class OptimizerReplyTest {
    public static void main(String[] args) {
        String good = "ALPHA:0.60|0:0.50:0.50:85.0|1:0.70:0.30:80.0|2:0.40:0.60:90.0|";
        for (String wire : new String[]{good, "\"" + good + "\"", good.substring(0, good.length()-1)}) {
            OptimizerReply reply = OptimizerReply.parse(wire);
            if (reply.alpha != .6 || reply.thresholds[2] != 90 || reply.weights[1] != .7)
                throw new AssertionError("Valid response changed");
        }
        String[] invalid = {null, "ERROR", "ALPHA:0.60|", good + "ALPHA:0.70|",
            good.replace("2:0.40:0.60:90.0|", ""), good + "0:0.50:0.50:85.0|",
            good.replace("0.60|0:", "NaN|0:"), good.replace("90.0", "Infinity"),
            good.replace("90.0", "96.0"), good.replace("2:0.40:0.60", "2:0.40:0.50"),
            good.replace("2:0.40", "3:0.40"), good + "|"};
        for (String wire : invalid) {
            try { OptimizerReply.parse(wire); }
            catch (IllegalArgumentException expected) { continue; }
            throw new AssertionError("Accepted invalid response: " + wire);
        }
        double[] lowW = {.1,.1,.1}, highW = {.9,.9,.9};
        double[] lowT = {20,20,20}, highT = {95,95,95};
        if (Math.abs(OptimizerReply.distance(.05,lowW,lowT,.95,highW,highT)-1)>1e-12)
            throw new AssertionError("Full-range normalized distance must be one");
        if (Math.abs(OptimizerReply.distance(.05,lowW,lowT,.95,lowW,lowT)-1.0/7)>1e-12)
            throw new AssertionError("One-coordinate distance must be one seventh");
        System.out.println("PASS: 3 valid, 12 invalid replies; 2 normalized-distance checks");
    }
}
