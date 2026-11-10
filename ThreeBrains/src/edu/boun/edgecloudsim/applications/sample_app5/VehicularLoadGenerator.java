package edu.boun.edgecloudsim.applications.sample_app5;

import java.util.ArrayList;
import java.nio.ByteBuffer;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;

import org.apache.commons.math3.distribution.ExponentialDistribution;

import edu.boun.edgecloudsim.core.SimSettings;
import edu.boun.edgecloudsim.task_generator.LoadGeneratorModel;
import edu.boun.edgecloudsim.utils.TaskProperty;
import edu.boun.edgecloudsim.utils.SimLogger;
import edu.boun.edgecloudsim.utils.SimUtils;

public class VehicularLoadGenerator extends LoadGeneratorModel {
    // Array storing the assigned task type for each mobile device

    int taskTypeOfDevices[];

    /**
     * Constructor for vehicular load generator.
     *
     * @param _numberOfMobileDevices total number of mobile devices (vehicles)
     * @param _simulationTime total simulation duration in seconds
     * @param _simScenario simulation scenario identifier
     */
    public VehicularLoadGenerator(int _numberOfMobileDevices, double _simulationTime, String _simScenario) {
        super(_numberOfMobileDevices, _simulationTime, _simScenario);
    }

    /**
     * Initializes the load generation model by creating task schedules for all
     * vehicles. Each vehicle is assigned a random task type and generates tasks
     * using Poisson distribution.
     */
    @Override
    public void initializeModel() {
        taskList = new ArrayList<TaskProperty>();
        ArrivalRateSchedule[] arrivalSchedules = ArrivalRateSchedule.fromProperties(
                simulationTime, SimSettings.getInstance().getTaskLookUpTable().length);

        // Assign each mobile device (vehicle) a specific application type (task type)
        taskTypeOfDevices = new int[numberOfMobileDevices];
        for (int i = 0; i < numberOfMobileDevices; i++) {
            int randomTaskType = -1;

            // Select task type based on probability distribution from lookup table
            double taskTypeSelector = SimUtils.getRandomDoubleNumber(0, 100);
            double taskTypePercentage = 0;
            for (int j = 0; j < SimSettings.getInstance().getTaskLookUpTable().length; j++) {
                taskTypePercentage += SimSettings.getInstance().getTaskLookUpTable()[j][0];
                if (taskTypeSelector <= taskTypePercentage) {
                    randomTaskType = j;
                    break;
                }
            }
            if (randomTaskType == -1) {
                SimLogger.printLine("Impossible is occurred! no random task type!");
                continue;
            }

            taskTypeOfDevices[i] = randomTaskType;
            ArrivalRateSchedule arrivalSchedule = arrivalSchedules[randomTaskType];

            // Get task generation parameters from lookup table
            double poissonMean = SimSettings.getInstance().getTaskLookUpTable()[randomTaskType][2];
            double activePeriod = SimSettings.getInstance().getTaskLookUpTable()[randomTaskType][3];
            double idlePeriod = SimSettings.getInstance().getTaskLookUpTable()[randomTaskType][4];

            // Start activity at a random time within the initial window
            double activePeriodStartTime = SimUtils.getRandomDoubleNumber(
                    SimSettings.CLIENT_ACTIVITY_START_TIME,
                    SimSettings.CLIENT_ACTIVITY_START_TIME * 2);
            double virtualTime = activePeriodStartTime;

            // Create exponential distribution for Poisson process (inter-arrival times)
//			ExponentialDistribution rng = new ExponentialDistribution(poissonMean);
            ExponentialDistribution rng
                    = new ExponentialDistribution(poissonMean);

            long workloadSeed = Long.parseLong(
                    System.getProperty("scope.simSeed", "20260828")
            );

            rng.reseedRandomGenerator(
                    workloadSeed + 1_000_003L * i
            );

            // Generate tasks for this device throughout the simulation
            while (virtualTime < simulationTime) {
                // Sample next task inter-arrival time from exponential distribution
                double interval = rng.sample();

                if (interval <= 0) {
                    SimLogger.printLine("Impossible is occurred! interval is " + interval + " for device " + i + " time " + virtualTime);
                    continue;
                }

                virtualTime = arrivalSchedule.nextArrival(virtualTime, interval);

                // Check if we've exceeded the current active period
                if (virtualTime > activePeriodStartTime + activePeriod) {
                    // Move to next active period (skip idle period)
                    activePeriodStartTime = activePeriodStartTime + activePeriod + idlePeriod;
                    virtualTime = activePeriodStartTime;
                    continue;
                }

                // Get base task parameters from lookup table
                long inputFileSize = (long) SimSettings.getInstance().getTaskLookUpTable()[randomTaskType][5];
                long inputFileSizeBias = inputFileSize / 10;

                long outputFileSize = (long) SimSettings.getInstance().getTaskLookUpTable()[randomTaskType][6];
                long outputFileSizeBias = outputFileSize / 10;

                long length = (long) SimSettings.getInstance().getTaskLookUpTable()[randomTaskType][7];
                long lengthBias = length / 10;

                int pesNumber = (int) SimSettings.getInstance().getTaskLookUpTable()[randomTaskType][8];

                // Add random variation to task parameters (±10% of base value)
                inputFileSize = SimUtils.getRandomLongNumber(inputFileSize - inputFileSizeBias, inputFileSize + inputFileSizeBias);
                outputFileSize = SimUtils.getRandomLongNumber(outputFileSize - outputFileSizeBias, outputFileSize + outputFileSizeBias);
                length = SimUtils.getRandomLongNumber(length - lengthBias, length + lengthBias);

                // Create and add the task to the global task list
                taskList.add(new TaskProperty(virtualTime, i, randomTaskType, pesNumber, length, inputFileSize, outputFileSize));
            }
        }
        if (System.getProperty("scope.workload.shiftSeconds") != null) {
            // Include every scheduled task field, without consuming any RNG draws.
            // Equal fingerprints are required for adaptive/frozen comparisons.
            try {
                MessageDigest digest = MessageDigest.getInstance("SHA-256");
                ByteBuffer bytes = ByteBuffer.allocate(44);
                for (TaskProperty task : taskList) {
                    bytes.clear();
                    bytes.putDouble(task.getStartTime()).putInt(task.getMobileDeviceId())
                            .putInt(task.getTaskType()).putInt(task.getPesNumber())
                            .putLong(task.getLength()).putLong(task.getInputFileSize())
                            .putLong(task.getOutputFileSize());
                    digest.update(bytes.array());
                }
                StringBuilder hash = new StringBuilder();
                for (byte b : digest.digest()) hash.append(String.format("%02x", b & 0xff));
                SimLogger.printLine("WORKLOAD_AUDIT shift_seconds="
                        + System.getProperty("scope.workload.shiftSeconds")
                        + " rate_multiplier=" + System.getProperty("scope.workload.rateMultiplier")
                        + " app_rate_multipliers=" + System.getProperty("scope.workload.appRateMultipliers")
                        + " scheduled_tasks=" + taskList.size() + " sha256=" + hash);
                long[][] phaseCounts = new long[arrivalSchedules.length][2];
                double shift = Double.parseDouble(System.getProperty("scope.workload.shiftSeconds"));
                for (TaskProperty task : taskList) {
                    if (task.getStartTime() < simulationTime) {
                        phaseCounts[task.getTaskType()][task.getStartTime() < shift ? 0 : 1]++;
                    }
                }
                for (int app = 0; app < phaseCounts.length; app++) {
                    SimLogger.printLine("WORKLOAD_PHASE_TASKS app=" + app
                            + " before=" + phaseCounts[app][0] + " after=" + phaseCounts[app][1]);
                }
            } catch (NoSuchAlgorithmException error) {
                throw new IllegalStateException(error);
            }
        }
    }

    /**
     * Returns the assigned task type for a specific device.
     *
     * @param deviceId the device identifier
     * @return task type assigned to the device
     */
    @Override
    public int getTaskTypeOfDevice(int deviceId) {
        return taskTypeOfDevices[deviceId];
    }

}
