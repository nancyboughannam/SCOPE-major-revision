function plot_confirmatory_results()
% Run in MATLAB after the complete registered study, using its matlab folder.
root=fileparts(fileparts(mfilename('fullpath')));
status=jsondecode(fileread(fullfile(root,'completion.json')));
assert(status.complete,'Complete every registered evaluation scenario first.');
plan=jsondecode(fileread(fullfile(root,'study.json')));
M=readtable(fullfile(root,'mean_metrics.csv'),'TextType','string');
P=readtable(fullfile(root,'phase_means.csv'),'TextType','string');
assert(all(M.n==numel(plan.iterations)) && all(P.n==numel(plan.iterations)), ...
    'A plotted cell is missing one or more registered seeds.');
folder=fullfile(root,'figures');
groups=["main","ablations","adaptation"];
for g=groups,if ~exist(fullfile(folder,g),'dir'),mkdir(fullfile(folder,g));end,end
main=string(plan.main_policies);loads=plan.loads(:)';colors=lines(numel(main));
metrics=["failure_pct","service_seconds","processing_seconds","network_seconds", ...
    "qoe_all_pct","edge_utilization_pct","cloud_utilization_pct"];
ylabels=["Failed tasks (%)","Completed-task service time (s)", ...
    "Completed-task processing time (s)","Completed-task network delay (s)", ...
    "QoE, all tasks (%)","Edge VM utilization (%)","Cloud VM utilization (%)"];
apps=["ALL_APPS","TRAFFIC_MANAGEMENT","DANGER_ASSESSMENT","INFOTAINMENT"];
for a=1:numel(apps)
    for k=1:numel(metrics)
        if a>1 && ~ismember(metrics(k),["failure_pct","service_seconds","qoe_all_pct"]),continue;end
        fig=figure('Color','w','Position',[100 100 960 560]);hold on;
        for j=1:numel(main)
            values=zeros(numel(loads),3);
            for n=1:numel(loads)
                R=M(M.group=="main" & M.label==main(j) & M.load==loads(n) & ...
                    M.application==apps(a) & M.metric==metrics(k),:);
                assert(height(R)==1,'Missing/duplicated main result.');
                values(n,:)=[R.mean,R.mean-R.lower,R.upper-R.mean];
            end
            errorbar(loads,values(:,1),values(:,2),values(:,3),'-o', ...
                'Color',colors(j,:),'LineWidth',1.7,'DisplayName',displayname(main(j)));
        end
        xlabel('Vehicles');ylabel(ylabels(k));xticks(loads);grid on;
        title(apps(a),'Interpreter','none');legend('Location','eastoutside');
        saveplot(fig,fullfile(folder,'main'),apps(a)+"_"+metrics(k));
    end
end
labels=["SCOPE","SCOPE_STATIC","HARD_ONLY","SOFTCOST_OPT","PERFORMANCE_ONLY"];
am=["failure_pct","service_seconds","qoe_all_pct","total_movement","changes"];
ay=["Failed tasks (%)","Completed-task service time (s)","QoE, all tasks (%)", ...
    "Total normalized parameter movement","Configuration changes"];
for k=1:numel(am)
    values=zeros(numel(labels),3);
    for j=1:numel(labels)
        R=M(M.group=="ablation" & M.label==labels(j) & M.application=="ALL_APPS" & M.metric==am(k),:);
        assert(height(R)==1,'Missing/duplicated ablation result.');
        values(j,:)=[R.mean,R.mean-R.lower,R.upper-R.mean];
    end
    fig=figure('Color','w','Position',[100 100 960 560]);
    bar(1:numel(labels),values(:,1));hold on;
    errorbar(1:numel(labels),values(:,1),values(:,2),values(:,3),'k.','LineWidth',1.4);
    names=strings(size(labels));
    for j=1:numel(labels),names(j)=displayname(labels(j));end
    xticks(1:numel(labels));xticklabels(names);xtickangle(15);
    ylabel(ay(k));title(sprintf('Ablations: %d vehicles',plan.ablation_load));grid on;
    saveplot(fig,fullfile(folder,'ablations'),am(k));
end
labels=string(plan.adaptation_policies);colors=lines(numel(labels));phases=["before","increase","recovery"];
for k=1:2
    metric=metrics(k);fig=figure('Color','w','Position',[100 100 1000 560]);hold on;
    for j=1:numel(labels)
        values=zeros(3,3);
        for n=1:3
            R=P(P.label==labels(j) & P.phase==phases(n) & P.metric==metric,:);
            assert(height(R)==1,'Missing/duplicated adaptation phase.');
            values(n,:)=[R.mean,R.mean-R.lower,R.upper-R.mean];
        end
        errorbar(1:3,values(:,1),values(:,2),values(:,3),'-o', ...
            'Color',colors(j,:),'LineWidth',1.7,'DisplayName',displayname(labels(j)));
    end
    xticks(1:3);xticklabels(phases);ylabel(ylabels(k));grid on;
    title(sprintf('Increase and recovery: %d vehicles',plan.adaptation_load));
    legend('Location','eastoutside');saveplot(fig,fullfile(folder,'adaptation'),"phases_"+metric);
end
fprintf('Figures saved to: %s\n',folder);
fprintf('Means and 95%% t intervals across %d seeds. Profile: %s.\n',numel(plan.iterations),plan.profile);
fprintf('Service time covers completed tasks. Failure denominator is completed + failed.\n');
fprintf('Phase windows exclude warmup and boundaries; they are outcome windows, not admission cohorts.\n');
fprintf('Paired contrasts and Holm-adjusted tests are in paired_comparisons.csv.\n');
fprintf('Parameter movement is not measured migration cost. No runtime-overhead claim is generated.\n');
end

function name=displayname(label)
switch char(label)
    case 'SCOPE',name="SCOPE";
    case 'SCOPE_STATIC',name="Calibrated static";
    case 'SCOPE_FROZEN',name="SCOPE frozen before increase";
    case 'HARD_ONLY',name="Hard bound only";
    case 'SOFTCOST_OPT',name="Soft penalty only";
    case 'PERFORMANCE_ONLY',name="Performance only";
    case 'AI_BASED',name="AI-based";
    case 'RAIDER_TRAX',name="RAIDER/TRAX";
    case 'EXP3_MC',name="EXP3-MC (adapted)";
    otherwise,name=string(label);
end
end

function saveplot(fig,folder,name)
exportgraphics(fig,fullfile(folder,char(name+".pdf")),'ContentType','vector');
exportgraphics(fig,fullfile(folder,char(name+".png")),'Resolution',300);
savefig(fig,fullfile(folder,char(name+".fig")));
close(fig);
end
