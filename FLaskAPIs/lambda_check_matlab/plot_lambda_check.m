function plot_lambda_check()
% Calibration only: mean and 95% t interval across independent simulation seeds.
% Use MATLAB's Command Window from the new output's matlab folder.
root=fileparts(fileparts(mfilename('fullpath')));
status=jsondecode(fileread(fullfile(root,'completion.json')));
assert(status.complete,'Finish every registered lambda-check scenario first.');
T=readtable(fullfile(root,'lambda_metrics.csv'),'TextType','string');
T=T(T.application=="ALL_APPS",:);
P=readtable(fullfile(root,'phase_metrics.csv'),'TextType','string');
folder=fullfile(root,'figures');if ~exist(folder,'dir'),mkdir(folder);end
lambdas=unique(T.lambda_value);cases=["steady","burst"];
variants=["adaptive","frozen"];labels=["SCOPE adaptive","SCOPE frozen before increase"];
metrics=["failure_pct","service_seconds","qoe_all_pct","total_movement"];
ylabels=["Failed tasks (%)","Completed-task service time (s)","QoE, all tasks (%)","Total normalized configuration movement"];
colors=lines(2);
for k=1:numel(metrics)
    fig=figure('Color','w');
    for c=1:numel(cases)
        subplot(1,2,c);hold on;
        for v=1:numel(variants)
            S=T(T.("case")==cases(c) & T.variant==variants(v),:);
            if isempty(S),continue;end
            means=nan(size(lambdas));ci=nan(size(lambdas));
            for j=1:numel(lambdas)
                x=S{S.lambda_value==lambdas(j),char(metrics(k))};
                [means(j),ci(j)]=interval(x);
            end
            errorbar(lambdas,means,ci,'-o','Color',colors(v,:),'LineWidth',1.6,'DisplayName',labels(v));
        end
        xlabel('\lambda (R_{max}=0.15 for every setting)');ylabel(ylabels(k));
        xticks(lambdas);grid on;legend('Location','best');
        if c==1,title('Constant workload: 1800 vehicles');else,title('Workload increase/recovery: 1200 vehicles');end
    end
    savefigure(fig,folder,metrics(k));
end
fig=figure('Color','w');phases=["before","burst","recovery"];
for j=1:numel(lambdas)
    subplot(1,numel(lambdas),j);hold on;
    for v=1:numel(variants)
        means=nan(1,3);ci=nan(1,3);
        for k=1:3
            x=P.failure_pct(P.("case")=="burst" & P.variant==variants(v) & P.lambda_value==lambdas(j) & P.phase==phases(k));
            [means(k),ci(k)]=interval(x);
        end
        errorbar(1:3,means,ci,'-o','Color',colors(v,:),'LineWidth',1.6,'DisplayName',labels(v));
    end
    xticks(1:3);xticklabels(phases);ylabel('Failed finalized tasks in phase (%)');
    title(sprintf('Calibration: lambda = %.2f',lambdas(j)));grid on;legend('Location','best');
end
savefigure(fig,folder,"adaptation_phases");
fprintf('Calibration figures saved to: %s\n',folder);
fprintf('Intervals use seeds, not tasks/windows. One-seed smoke checks have no confidence intervals.\n');
fprintf('Phase plots exclude windows crossing warmup/transitions; outcomes are not admission cohorts.\n');
fprintf('This script does not choose lambda or generate a superiority claim.\n');
end

function [m,c]=interval(x)
assert(~isempty(x) && all(isfinite(x)),'Missing/nonfinite metric values.');
m=mean(x);n=numel(x);c=0;
if n>1
    df=n-1;t=sqrt(df*(1/betaincinv(.05,df/2,.5)-1));c=t*std(x)/sqrt(n);
end
end

function savefigure(fig,folder,name)
exportgraphics(fig,fullfile(folder,char(name+".pdf")),'ContentType','vector');
exportgraphics(fig,fullfile(folder,char(name+".png")),'Resolution',300);
savefig(fig,fullfile(folder,char(name+".fig")));
end
