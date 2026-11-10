package edu.boun.edgecloudsim.applications.sample_app5;

import java.util.*;

/** Complete admission cohorts: delayed outcomes never move to a newer arm. */
public final class Exp3FeedbackTracker {
    private static final class Cohort {
        long id;
        int[] generated = new int[3], completed = new int[3], failed = new int[3];
        double[] service = new double[3];
        boolean closed;
        Cohort(long value) { id = value; }
        boolean ready() {
            if (!closed) return false;
            for (int i=0;i<3;i++) if (generated[i] != completed[i]+failed[i]) return false;
            return true;
        }
    }
    private final Map<Long,Cohort> cohorts = new LinkedHashMap<>();
    private final Map<String,Long> tasks = new HashMap<>();
    private long active = 0;
    public Exp3FeedbackTracker() { cohorts.put(0L,new Cohort(0)); }
    public void admit(String key,int type) {
        if(type<0 || type>=3) return;
        if(tasks.putIfAbsent(key,active)!=null) throw new IllegalStateException("Duplicate task admission");
        cohorts.get(active).generated[type]++;
    }
    public void finish(String key,int type,boolean success,double service) {
        Long id=tasks.remove(key);
        if(id==null) return;
        Cohort c=cohorts.get(id);
        if(success) { c.completed[type]++; c.service[type]+=service; }
        else c.failed[type]++;
    }
    public long closeWindow() {
        long closed=active;
        cohorts.get(active).closed=true;
        active++;
        cohorts.put(active,new Cohort(active));
        return closed;
    }
    public List<Long> readyIds() {
        List<Long> ids=new ArrayList<>();
        for(Cohort c:cohorts.values()) if(c.ready()) ids.add(c.id);
        return ids;
    }
    public void acknowledge(List<Long> ids) { for(Long id:ids) cohorts.remove(id); }
    public int pendingTasks() { return tasks.size(); }
    public String feedbackJson(List<Long> ids,double[] deadlines) {
        StringBuilder b=new StringBuilder("[");
        boolean comma=false;
        for(Long id:ids) {
            if(comma) b.append(','); comma=true;
            Cohort c=cohorts.get(id);
            b.append("{\"window_id\":").append(id).append(",\"app_stats\":{");
            for(int i=0;i<3;i++) {
                if(i>0) b.append(',');
                int n=c.completed[i]+c.failed[i];
                double failure=n>0?(double)c.failed[i]/n:0;
                double dnst=c.completed[i]>0?c.service[i]/c.completed[i]/deadlines[i]:(c.failed[i]>0?1:0);
                b.append('"').append(i).append("\":{\"total\":").append(c.generated[i])
                 .append(",\"completed\":").append(c.completed[i])
                 .append(",\"failures\":").append(c.failed[i])
                 .append(",\"failure_rate\":").append(failure)
                 .append(",\"deadline_norm_service_time\":").append(dnst).append('}');
            }
            b.append("}}");
        }
        return b.append(']').toString();
    }
}
