function output = plot_scope_paper_results(studyRoot, output)
% Replot completed v5 results. No simulator, optimizer, or model is run.
% Default: read the completed study above this copied matlab folder.
% MATLAB R2020a+ is required for exportgraphics and readtable TextType.
base = fileparts(mfilename('fullpath'));
if nargin < 1 || isempty(studyRoot), studyRoot = fileparts(base); end
if nargin < 2 || isempty(output)
    output = fullfile(base,['figures_paper_' datestr(now,'yyyymmdd_HHMMSS')]);
end
assert(~isfolder(output), 'Output folder already exists. Choose a new output folder.');
status = jsondecode(fileread(fullfile(studyRoot,'completion.json')));
plan = jsondecode(fileread(fullfile(studyRoot,'study.json')));
assert(status.complete && strcmp(plan.profile,'full'), ...
    'Use a complete final study, not a pilot or smoke run.');
assert(status.completed == 400 && status.expected == 400, ...
    'This figure package was prepared for the completed 400-scenario study.');
assert(isequal(sort(plan.iterations(:)),(3401:3410)'), 'Unexpected final seeds.');
assert(abs(plan.lambda_value-0.01)<1e-12 && abs(plan.r_max-0.15)<1e-12, ...
    'The final study uses lambda=0.01 and Rmax=0.15.');
M = readtable(fullfile(studyRoot,'mean_metrics.csv'),'TextType','string');
P = readtable(fullfile(studyRoot,'phase_means.csv'),'TextType','string');
assert(all(M.n==10) && all(P.n==10), 'Every summary must include all ten seeds.');
assert(all(isfinite(M.mean)) && all(isfinite(M.lower)) && all(isfinite(M.upper)), ...
    'Missing or nonfinite mean/interval.');
assert(all(M.lower <= M.mean) && all(M.mean <= M.upper), 'Invalid intervals.');
assert(any(strcmpi(listfonts,'Times New Roman')), ...
    'Install Times New Roman before exporting figures in the original style.');
mkdir(output);
folders = {'main','static_control','ablations','adaptation','supplementary'};
for k=1:numel(folders), mkdir(fullfile(output,folders{k})); end
loads = plan.loads(:)';
assert(isequal(loads,[600 900 1200 1500 1800]), 'Unexpected load grid.');
main = ["SCOPE","AI_BASED","EXP3_MC","RAIDER_TRAX"];
allPolicies = string(plan.main_policies(:))';
apps = ["ALL_APPS","TRAFFIC_MANAGEMENT","DANGER_ASSESSMENT","INFOTAINMENT"];
metrics = ["failure_pct","service_seconds","qoe_all_pct", ...
    "processing_seconds","network_seconds","edge_utilization_pct","cloud_utilization_pct"];
ylabs = ["Failed tasks (%)","Service time (s)","QoE, all tasks (%)", ...
    "Processing time (s)","Network delay (s)","Edge VM utilization (%)","Cloud VM utilization (%)"];

% Two four-panel figure sets in the manuscript: failures and service time.
% Each panel is exported separately at the original 11 x 11 cm size.
for a=1:numel(apps)
    for k=1:2
        loadplot(M,loads,main,apps(a),metrics(k),ylabs(k), ...
            fullfile(output,'main'),apps(a)+"_"+metrics(k),10);
    end
end
loadplot(M,loads,main,"ALL_APPS",metrics(3),ylabs(3), ...
    fullfile(output,'main'),"ALL_APPS_"+metrics(3),10);

% Reviewer 2 comment 4: retain the tuned static control at EVERY tested load.
for k=1:2
    loadplot(M,loads,["SCOPE","SCOPE_STATIC"],"ALL_APPS",metrics(k),ylabs(k), ...
        fullfile(output,'static_control'),"SCOPE_vs_static_"+metrics(k),10);
end

% Retain all original main comparators in the supplementary results.
% Removing a curve from a main figure does not remove it from the analysis.
for a=1:numel(apps)
    last = 3;
    if a==1, last=numel(metrics); end
    for k=1:last
        loadplot(M,loads,allPolicies,apps(a),metrics(k),ylabs(k), ...
            fullfile(output,'supplementary'),"all_controls_"+apps(a)+"_"+metrics(k),10);
    end
end

% These results exist at 1800 vehicles only. Do not invent load-sweep curves.
labels = ["SCOPE","SCOPE_STATIC","HARD_ONLY","SOFTCOST_OPT","PERFORMANCE_ONLY"];
shortNames = {'SCOPE','Static','Hard','Soft','Perf.'};
am = ["failure_pct","service_seconds","total_movement","changes","qoe_all_pct"];
ay = ["Failed tasks (%)","Service time (s)","Total normalized movement", ...
    "Configuration changes","QoE, all tasks (%)"];
for k=1:numel(am)
    V=zeros(numel(labels),3);
    for j=1:numel(labels)
        R=M(M.group=="ablation" & M.label==labels(j) & ...
            M.load==plan.ablation_load & M.application=="ALL_APPS" & M.metric==am(k),:);
        V(j,:)=values(R,10);
    end
    [fig,ax]=newfigure();
    for j=1:numel(labels)
        s=style(labels(j));
        bar(ax,j,V(j,1),0.6,'FaceColor',s.color,'EdgeColor',s.color,'HandleVisibility','off');
    end
    errorbar(ax,1:numel(labels),V(:,1),V(:,2),V(:,3),'k.', ...
        'LineStyle','none','LineWidth',1.2,'HandleVisibility','off');
    set(ax,'XTick',1:numel(labels),'XTickLabel',shortNames);
    xlabel(ax,sprintf('Configuration variants (%d vehicles)',plan.ablation_load),'FontSize',13);
    ylabel(ax,ay(k),'FontSize',13); xlim(ax,[0.4 numel(labels)+0.6]);
    saveplot(fig,fullfile(output,'ablations'),am(k));
end

% Essential adaptation controls only in the focused plots; all controls below.
phaseLabels=["SCOPE","SCOPE_FROZEN","SCOPE_STATIC"];
for k=1:2
    phaseplot(P,phaseLabels,metrics(k),ylabs(k),fullfile(output,'adaptation'), ...
        "phases_"+metrics(k),10);
    phaseplot(P,string(plan.adaptation_policies(:))',metrics(k),ylabs(k), ...
        fullfile(output,'supplementary'),"all_adaptation_phases_"+metrics(k),10);
end

% Preserve all registered comparisons, including RANDOM and tuned static.
copyfile(fullfile(studyRoot,'paired_comparisons.csv'),fullfile(output,'paired_comparisons.csv'));
copyfile(fullfile(studyRoot,'mean_metrics.csv'),fullfile(output,'all_mean_metrics.csv'));
copyfile(fullfile(studyRoot,'phase_means.csv'),fullfile(output,'all_phase_means.csv'));
fprintf('Paper figures saved to: %s\n',output);
fprintf('400 completed scenarios; final seeds 3401-3410; lambda 0.01; Rmax 0.15.\n');
fprintf('Service/processing/network means describe completed tasks only.\n');
fprintf('Mean and 95%% t intervals across ten seeds; see paired_comparisons.csv for Holm tests.\n');
if isfield(plan,'exp3_routing_schema')
    fprintf('EXP3 routing: %s. Guard-on comparison is retained separately.\n',plan.exp3_routing_schema);
else
    fprintf('EXP3-MC-adapted uses the shared deadline guard.\n');
end
fprintf('Static calibration uses separate seeds. Phase means are not response-time estimates.\n');
fprintf('Static is a calibrated control, not an external baseline. Read FIGURE_GUIDE.md.\n');
if isfile(fullfile(studyRoot,'exp3_guard_pairs.csv'))
    guardplots(studyRoot,output,loads);
end
end

function guardplots(studyRoot,output,loads)
G=readtable(fullfile(studyRoot,'exp3_guard_pairs.csv'),'TextType','string');
folder=fullfile(output,'exp3_routing_ablation');mkdir(folder);
metrics=["failure_pct","service_seconds"];ylabs=["Failed tasks (%)","Service time (s)"];
for k=1:2
    [fig,ax]=newfigure();
    for variant=["guard_off","guard_on"]
        V=zeros(numel(loads),3);
        for n=1:numel(loads)
            R=G(G.load==loads(n) & G.application=="ALL_APPS" & G.metric==metrics(k),:);
            assert(height(R)==10 && numel(unique(R.iteration))==10,'Missing paired seeds');
            v=R.(variant);m=mean(v);h=2.262157162854099*std(v)/sqrt(10);
            V(n,:)=[m h h];
        end
        if variant=="guard_off"
            color=[0.8500 0.3250 0.0980];mark='^';line='-';name='EXP3: guard off';
        else
            color=[0.4940 0.1840 0.5560];mark='p';line='--';name='EXP3: guard on';
        end
        errorbar(ax,loads,V(:,1),V(:,2),V(:,3),'Color',color,'Marker',mark, ...
            'LineStyle',line,'LineWidth',1.5,'MarkerSize',6,'DisplayName',name);
    end
    set(ax,'XTick',loads);xlim(ax,[loads(1)-30 loads(end)+30]);
    xlabel(ax,'Number of Vehicles','FontSize',13);ylabel(ax,ylabs(k),'FontSize',13);
    legend(ax,'show','Location','best','FontName','Times New Roman','FontSize',12, ...
        'Interpreter','none','Box','off');
    saveplot(fig,folder,metrics(k));
end
end

function loadplot(M,loads,labels,app,metric,ylab,folder,name,N)
[fig,ax]=newfigure();
for j=1:numel(labels)
    V=zeros(numel(loads),3);
    for n=1:numel(loads)
        R=M(M.group=="main" & M.label==labels(j) & M.load==loads(n) & ...
            M.application==app & M.metric==metric,:);
        V(n,:)=values(R,N);
    end
    drawline(ax,loads,V,labels(j));
end
set(ax,'XTick',loads);xlim(ax,[loads(1)-30 loads(end)+30]);
xlabel(ax,'Number of Vehicles','FontSize',13);ylabel(ax,ylab,'FontSize',13);
legend(ax,'show','Location','best','FontName','Times New Roman', ...
    'FontSize',12,'Interpreter','none','Box','off');
saveplot(fig,folder,name);
end

function phaseplot(P,labels,metric,ylab,folder,name,N)
[fig,ax]=newfigure(); phases=["before","increase","recovery"];
for j=1:numel(labels)
    V=zeros(3,3);
    for k=1:3
        R=P(P.label==labels(j) & P.phase==phases(k) & P.metric==metric,:);
        V(k,:)=values(R,N);
    end
    drawline(ax,1:3,V,labels(j));
end
set(ax,'XTick',1:3,'XTickLabel',{'Before','Increase','Recovery'});
xlim(ax,[0.9 3.1]); xlabel(ax,'Workload phase','FontSize',13);ylabel(ax,ylab,'FontSize',13);
legend(ax,'show','Location','best','FontName','Times New Roman', ...
    'FontSize',12,'Interpreter','none','Box','off');
saveplot(fig,folder,name);
end

function v=values(R,N)
assert(height(R)==1 && R.n==N,'Missing/duplicate summary, or missing seeds.');
v=[R.mean R.mean-R.lower R.upper-R.mean];
assert(all(isfinite(v)) && all(v(2:3)>=0),'Invalid plotted values.');
% Keep the complete recorded interval, including negative statistical bounds.
% No curve is clipped, smoothed, resampled, or filtered by its outcome.
end

function [fig,ax]=newfigure()
fig=figure('Visible','off','Color','w','Units','centimeters','Position',[6 3 11 11]);
ax=axes('Parent',fig,'FontName','Times New Roman','FontSize',12,'Color','none');
hold(ax,'on');axis(ax,'square');grid(ax,'off');box(ax,'on');
set(fig,'PaperUnits','centimeters','PaperPositionMode','manual', ...
    'PaperPosition',[0 0 11 11],'PaperSize',[11 11]);
end

function drawline(ax,x,V,label)
s=style(label);
errorbar(ax,x,V(:,1),V(:,2),V(:,3),'Color',s.color,'Marker',s.marker, ...
    'LineStyle',s.line,'LineWidth',s.width,'MarkerFaceColor',s.face, ...
    'MarkerSize',s.size,'DisplayName',s.name);
end

function s=style(label)
s=struct('color',[0.2 0.2 0.2],'marker','o','line','-','width',1.5, ...
    'face','none','size',6,'name',char(label));
switch char(label)
    case 'SCOPE'
        s.color=[0 0.4470 0.7410];s.marker='o';s.width=2.5;
        s.face=s.color;s.size=8;s.name='SCOPE';
    case 'AI_BASED'
        s.color=[0.15 0.55 0.25];s.marker='s';s.line='--';s.name='AI-based';
    case 'EXP3_MC'
        s.color=[0.8500 0.3250 0.0980];s.marker='^';s.name='EXP3-MC-adapted';
    case 'RAIDER_TRAX'
        s.color=[0.9290 0.6940 0.1250];s.marker='d';s.line='--';s.name='RAIDER-TRAX';
    case 'RANDOM'
        s.color=[0.5 0.5 0.5];s.marker='s';s.line=':';s.name='RANDOM';
    case 'SCOPE_STATIC'
        s.color=[0.4940 0.1840 0.5560];s.marker='p';s.line='--';s.name='Calibrated static';
    case 'SCOPE_FROZEN'
        s.color=[0.3 0.3 0.3];s.marker='x';s.line=':';s.name='SCOPE frozen';
    case 'HARD_ONLY'
        s.color=[0.3010 0.7450 0.9330];s.marker='s';s.line='--';s.name='Hard bound only';
    case 'SOFTCOST_OPT'
        s.color=[0.6350 0.0780 0.1840];s.marker='d';s.line='-.';s.name='Soft penalty only';
    case 'PERFORMANCE_ONLY'
        s.color=[0.4660 0.6740 0.1880];s.marker='v';s.line=':';s.name='Performance only';
end
end

function saveplot(fig,folder,name)
drawnow;
ax=findobj(fig,'Type','axes');
assert(isscalar(ax),'Expected one axes object per exported panel.');
exportgraphics(ax,fullfile(folder,char(name+".pdf")),'ContentType','vector');
exportgraphics(ax,fullfile(folder,char(name+".png")),'Resolution',300);
savefig(fig,fullfile(folder,char(name+".fig")));
close(fig);
end
