function plot_deadline_pilot()
% Run in MATLAB, from the output folder's matlab directory.
% Development results only. Service time is conditional on completion.
root = fileparts(fileparts(mfilename('fullpath')));
T = readtable(fullfile(root,'pilot_metrics.csv'),'TextType','string');
T = T(startsWith(T.job,"pilot_") & T.application=="ALL_APPS",:);
assert(~isempty(T),'No completed pilot rows. Finish the pilot stage first.');
policies = ["SCOPE","SCOPE_STATIC","PERFORMANCE_ONLY","AI_BASED"];
labels = ["SCOPE + deadline check","Tuned static + deadline check", ...
          "Performance only + deadline check","AI based"];
metrics = ["failure_pct","service_seconds","qoe_all_pct"];
ylabels = ["Failed tasks (%)","Completed-task service time (s)","QoE, all tasks (%)"];
folder = fullfile(root,'figures'); if ~exist(folder,'dir'), mkdir(folder); end
loads = unique(T.load); colors = lines(4);
for k=1:numel(metrics)
    fig=figure('Color','w'); hold on;
    for p=1:numel(policies)
        means=nan(size(loads)); ci=nan(size(loads));
        for j=1:numel(loads)
            v=T{T.policy==policies(p) & T.load==loads(j),char(metrics(k))};
            means(j)=mean(v); n=numel(v);
            if n>1
                % t critical from inverse incomplete beta, no Statistics Toolbox.
                df=n-1; t=sqrt(df*(1/betaincinv(.05,df/2,.5)-1));
                ci(j)=t*std(v)/sqrt(n);
            else
                ci(j)=0; % One-run smoke check has no confidence interval.
            end
        end
        errorbar(loads,means,ci,'-o','LineWidth',1.6,'Color',colors(p,:),'DisplayName',labels(p));
    end
    xlabel('Vehicles'); ylabel(ylabels(k)); grid on; legend('Location','best');
    title('Development pilot; mean and 95% t interval when n > 1');
    exportgraphics(fig,fullfile(folder,char(metrics(k)+".pdf")),'ContentType','vector');
    exportgraphics(fig,fullfile(folder,char(metrics(k)+".png")),'Resolution',300);
    savefig(fig,fullfile(folder,char(metrics(k)+".fig")));
end
fprintf('Pilot figures saved to %s\n',folder);
fprintf('These are development comparisons, not final publication evidence.\n');
fprintf('Adaptation window data are in window_metrics.csv (outcome windows, not admission cohorts).\n');
end
