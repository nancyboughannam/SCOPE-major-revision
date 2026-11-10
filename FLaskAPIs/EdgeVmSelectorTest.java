import java.util.*;
import edu.boun.edgecloudsim.applications.sample_app5.EdgeVmSelector;

public class EdgeVmSelectorTest {
    static class V { double load, distance; V(double l,double d){load=l;distance=d;} }
    static class R extends Random { int calls; public double nextDouble(){calls++; return 0;} }
    static V pick(List<V> v,V planned,R r) {
        return EdgeVmSelector.select(v,planned,x->x.load,x->x.distance,.5,.5,85,0,r);
    }
    static void check(boolean b,String msg){if(!b)throw new AssertionError(msg);}
    public static void main(String[] args){
        V first=new V(90,0), second=new V(10,0), otherHost=new V(20,0);
        List<V> all=Arrays.asList(first,second,otherHost); R r=new R();
        check(pick(all,null,r)==second,"Second VM must be reachable when first is overloaded");
        r.calls=0;
        check(pick(all,otherHost,r)==otherHost && r.calls==0,"Eligible plan retained without resampling");
        otherHost.load=86;
        check(pick(all,otherHost,r)==second,"Stale overloaded plan must be reselected");
        second.load=85;
        check(pick(all,second,r)==null,"Threshold equality rejected; no first-VM fallback");
        second.load=Double.NaN;
        check(pick(all,null,r)==null,"Invalid load rejected");
        check(pick(Collections.emptyList(),null,r)==null,"Empty inventory rejected");
        V outsider=new V(0,0); second.load=10;
        check(pick(all,outsider,r)==second,"Foreign cached VM cannot bypass inventory");
        System.out.println("PASS: seven edge-selection regression checks");
    }
}
