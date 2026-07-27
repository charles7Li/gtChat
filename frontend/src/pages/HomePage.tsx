import { FormEvent, useEffect, useMemo, useState } from "react";
import { api, type LoginState, type Platform } from "../api";
import { BriefBuilder } from "../components/BriefBuilder";
import { ErrorNotice } from "../components/ErrorNotice";
import { RunTimeline } from "../components/RunTimeline";
import { StatusBadge } from "../components/StatusBadge";
import type { ChatRun, MonitorJob, RunStatus } from "../types";

type HomeMode = "monitor" | "chat";
type MonitorPlatform = "douyin_hot_board" | "xiaohongshu";

const platformOptions: Array<{ value: MonitorPlatform; label: string; auth: Platform }> = [
  { value: "douyin_hot_board", label: "抖音热榜", auth: "douyin" },
  { value: "xiaohongshu", label: "小红书", auth: "xiaohongshu" },
];

const intervalOptions = [
  { value: 1800, label: "每 30 分钟" },
  { value: 3600, label: "每小时" },
  { value: 21600, label: "每 6 小时" },
];

const defaultRule = { min_heat_score: 80, min_growth_rate: 0, min_rank: 100, min_engagement: 0, required_sources: [] as string[] };
const ACTIVE_RUN_KEY = "mochi-active-web-run";

export function HomePage({
  onOpenReports,
  onOpenSettings,
}: {
  onOpenReports: () => void;
  onOpenSettings: (platform?: Platform) => void;
}) {
  const [mode, setMode] = useState<HomeMode>("monitor");
  const [authStates, setAuthStates] = useState<Partial<Record<Platform, LoginState>>>({});
  const [authIssue, setAuthIssue] = useState<Platform | "all" | null>(null);

  const [platform, setPlatform] = useState<MonitorPlatform>("douyin_hot_board");
  const [keywords, setKeywords] = useState("pet");
  const [intervalSeconds, setIntervalSeconds] = useState(3600);
  const [jobName, setJobName] = useState("宠物热点检查");
  const [signalsPath, setSignalsPath] = useState("");
  const [monitorAllowLive, setMonitorAllowLive] = useState(false);
  const [rule, setRule] = useState(defaultRule);
  const [jobs, setJobs] = useState<MonitorJob[]>([]);
  const [savedId, setSavedId] = useState("");
  const [monitorStatus, setMonitorStatus] = useState<RunStatus>("pending");
  const [monitorResult, setMonitorResult] = useState<Record<string, unknown> | null>(null);
  const [digest, setDigest] = useState<Record<string, unknown> | null>(null);
  const [monitorError, setMonitorError] = useState("");

  const [query, setQuery] = useState("帮我找出宠物内容里最值得跟进的角度，并整理成可执行的拍摄方案。");
  const [taskType, setTaskType] = useState("趋势分析");
  const [outputTarget, setOutputTarget] = useState("策略报告");
  const [sourceContext, setSourceContext] = useState("本地结果");
  const [allowLive, setAllowLive] = useState(false);
  const [chatStatus, setChatStatus] = useState<RunStatus>("pending");
  const [run, setRun] = useState<ChatRun | null>(null);
  const [recentRuns, setRecentRuns] = useState<ChatRun[]>([]);
  const [chatError, setChatError] = useState("");

  const selectedPlatform = useMemo(
    () => platformOptions.find((item) => item.value === platform) || platformOptions[0],
    [platform],
  );
  const activeStatus = mode === "monitor" ? monitorStatus : chatStatus;

  useEffect(() => {
    if (!run?.run_id || !["queued", "running", "cancelling"].includes(run.status)) return;
    const timer = window.setInterval(async () => {
      try {
        const next = await api.getChatRun(run.run_id);
        setRun(next);
        setChatStatus(next.status);
        if (["success", "failed", "cancelled"].includes(next.status)) {
          setRecentRuns(await api.listChatRuns());
          window.localStorage.removeItem(ACTIVE_RUN_KEY);
          if (next.error) setChatError(next.error);
          window.clearInterval(timer);
        }
      } catch (error) {
        setChatError(error instanceof Error ? error.message : "无法读取任务进度");
      }
    }, 800);
    return () => window.clearInterval(timer);
  }, [run?.run_id, run?.status]);

  useEffect(() => {
    void api.authStatus().then(setAuthStates).catch(() => setAuthIssue("all"));
    void api.listJobs().then(setJobs).catch(() => setJobs([]));
    void api.listChatRuns().then((items) => {
      setRecentRuns(items);
      const activeId = window.localStorage.getItem(ACTIVE_RUN_KEY);
      const active = items.find((item) => item.run_id === activeId)
        || items.find((item) => ["queued", "running", "cancelling"].includes(item.status));
      if (active) {
        setRun(active);
        setChatStatus(active.status);
      }
    }).catch(() => setRecentRuns([]));
  }, []);

  function buildJob(): MonitorJob {
    const terms = keywords.split(",").map((item) => item.trim()).filter(Boolean);
    return {
      job_id: savedId || undefined,
      name: jobName.trim() || `${selectedPlatform.label} · ${terms[0] || "热点"}检查`,
      enabled: true,
      platforms: [platform],
      keywords: terms.length ? terms : ["pet"],
      interval_seconds: intervalSeconds,
      allow_live: monitorAllowLive,
      signals_path: signalsPath.trim() || undefined,
      output_dir: "outputs/hotspot",
      rule,
    };
  }

  async function saveMonitor(event?: FormEvent) {
    event?.preventDefault();
    setMonitorStatus("running");
    setMonitorError("");
    setAuthIssue(null);
    try {
      const saved = await api.saveJob(buildJob());
      setSavedId(saved.job_id || "");
      setJobName(saved.name);
      setJobs(await api.listJobs());
      setMonitorStatus("success");
      return saved.job_id || "";
    } catch (error) {
      const message = error instanceof Error ? error.message : "保存失败";
      setMonitorStatus("failed");
      setMonitorError(message);
      markAuthIssue(message);
      return "";
    }
  }

  async function runMonitorOnce() {
    const jobId = savedId || await saveMonitor();
    if (!jobId) return;
    setMonitorStatus("running");
    setMonitorError("");
    setAuthIssue(null);
    try {
      setMonitorResult(await api.runJob(jobId));
      setMonitorStatus("success");
    } catch (error) {
      const message = error instanceof Error ? error.message : "运行失败";
      setMonitorStatus("failed");
      setMonitorError(message);
      markAuthIssue(message);
    }
  }

  async function refreshDigest() {
    setMonitorStatus("running");
    setMonitorError("");
    try {
      setDigest(await api.digest());
      setMonitorStatus("success");
    } catch (error) {
      setMonitorStatus("failed");
      setMonitorError(error instanceof Error ? error.message : "摘要刷新失败");
    }
  }

  async function deleteMonitor() {
    if (!savedId || !window.confirm("删除这个监控任务？历史报告不会被删除。")) return;
    setMonitorStatus("running");
    try {
      await api.deleteJob(savedId);
      setSavedId("");
      setJobs(await api.listJobs());
      setMonitorResult(null);
      setMonitorStatus("pending");
    } catch (error) {
      setMonitorStatus("failed");
      setMonitorError(error instanceof Error ? error.message : "删除失败");
    }
  }

  async function submitChat(event: FormEvent) {
    event.preventDefault();
    const brief = `任务：${taskType}。输出：${outputTarget}。来源：${sourceContext}。简报：${query}`;
    setChatStatus("running");
    setChatError("");
    setAuthIssue(null);
    try {
      const created = await api.runChat(brief, allowLive);
      setRun(created);
      setChatStatus(created.status);
      setRecentRuns((current) => [created, ...current.filter((item) => item.run_id !== created.run_id)]);
      window.localStorage.setItem(ACTIVE_RUN_KEY, created.run_id);
    } catch (error) {
      const message = error instanceof Error ? error.message : "运行失败";
      setChatStatus("failed");
      setChatError(message);
      markAuthIssue(message);
    }
  }

  async function cancelRun() {
    if (!run) return;
    try {
      const next = await api.cancelChatRun(run.run_id);
      setRun(next);
      setChatStatus(next.status);
    } catch (error) {
      setChatError(error instanceof Error ? error.message : "取消失败");
    }
  }

  async function retryRun() {
    if (!run) return;
    setChatError("");
    try {
      const next = await api.retryChatRun(run.run_id);
      setRun(next);
      setChatStatus(next.status);
      window.localStorage.setItem(ACTIVE_RUN_KEY, next.run_id);
      setRecentRuns((current) => [next, ...current]);
    } catch (error) {
      setChatError(error instanceof Error ? error.message : "重试失败");
    }
  }

  function markAuthIssue(message: string) {
    if (!/(auth|login|cookie|session|401|403|登录|未授权|凭证|认证)/i.test(message)) return;
    const lower = message.toLowerCase();
    if (lower.includes("xhs") || message.includes("小红书")) setAuthIssue("xiaohongshu");
    else if (lower.includes("douyin") || message.includes("抖音")) setAuthIssue("douyin");
    else setAuthIssue("all");
  }

  function loadSavedJob(job: MonitorJob) {
    setSavedId(job.job_id || "");
    setPlatform((job.platforms[0] as MonitorPlatform) || "douyin_hot_board");
    setKeywords(job.keywords.join(", "));
    setIntervalSeconds(job.interval_seconds || 3600);
    setJobName(job.name);
    setSignalsPath(job.signals_path || "");
    setMonitorAllowLive(job.allow_live);
    setRule({ ...defaultRule, ...job.rule });
    setMonitorResult(job.last_result || null);
    setMode("monitor");
  }

  return (
    <section className="home-workbench">
      <section className="home-control-strip" aria-label="首页功能切换与登录状态">
        <div className="mode-switch" role="tablist" aria-label="首页功能">
          <button type="button" role="tab" aria-selected={mode === "monitor"} className={mode === "monitor" ? "active" : ""} onClick={() => setMode("monitor")}>
            定时任务
          </button>
          <button type="button" role="tab" aria-selected={mode === "chat"} className={mode === "chat" ? "active" : ""} onClick={() => setMode("chat")}>
            对话任务
          </button>
        </div>
        <div className="auth-strip" aria-label="平台登录状态">
          {platformOptions.map((item) => {
            const needsAuth = authIssue === "all" || authIssue === item.auth || authStates[item.auth]?.status === "invalid";
            const isSaved = authStates[item.auth]?.status === "saved";
            return (
              <button key={item.auth} type="button" className="platform-login-button compact-auth" onClick={() => onOpenSettings(item.auth)}>
                <span className={needsAuth ? "login-light needs-auth" : isSaved ? "login-light" : "login-light auth-missing"} aria-hidden="true" />
                <span>
                  <strong>{item.auth === "douyin" ? "抖音" : "小红书"}</strong>
                  <small>{needsAuth ? "需重登" : isSaved ? "已登录" : "未登录"}</small>
                </span>
              </button>
            );
          })}
        </div>
      </section>

      <div className="home-grid">
        <main className="home-primary">
          {mode === "monitor" ? (
            <form className="studio-panel monitor-form compact-monitor" onSubmit={saveMonitor}>
              <div className="panel-intro compact">
                <p className="section-kicker">定时任务</p>
                <h2>{savedId ? "编辑监控任务" : "新建监控任务"}</h2>
                <p>本地信号文件可离线运行；只有明确开启联网时才会访问外部平台。</p>
              </div>
              <label>
                任务名
                <input value={jobName} onChange={(event) => setJobName(event.target.value)} />
              </label>
              <div className="field-group">
                <label>
                  平台
                  <select value={platform} onChange={(event) => setPlatform(event.target.value as MonitorPlatform)}>
                    {platformOptions.map((item) => <option key={item.value} value={item.value}>{item.label}</option>)}
                  </select>
                </label>
                <label>
                  频率
                  <select value={intervalSeconds} onChange={(event) => setIntervalSeconds(Number(event.target.value))}>
                    {intervalOptions.map((item) => <option key={item.value} value={item.value}>{item.label}</option>)}
                  </select>
                </label>
              </div>
              <label className="brief-input">
                关键词
                <input value={keywords} onChange={(event) => setKeywords(event.target.value)} placeholder="例如：pet, 萌宠, 猫粮" />
              </label>
              <details className="advanced-fields">
                <summary>阈值与数据源</summary>
                <div className="threshold-grid">
                  <label>最低热度<input type="number" value={rule.min_heat_score} onChange={(event) => setRule({ ...rule, min_heat_score: Number(event.target.value) })} /></label>
                  <label>最低增长<input type="number" step="0.01" value={rule.min_growth_rate} onChange={(event) => setRule({ ...rule, min_growth_rate: Number(event.target.value) })} /></label>
                  <label>最高排名<input type="number" min="1" value={rule.min_rank} onChange={(event) => setRule({ ...rule, min_rank: Number(event.target.value) })} /></label>
                  <label>最低互动<input type="number" min="0" value={rule.min_engagement} onChange={(event) => setRule({ ...rule, min_engagement: Number(event.target.value) })} /></label>
                </div>
                <label>
                  信号文件
                  <input value={signalsPath} onChange={(event) => setSignalsPath(event.target.value)} placeholder="留空时使用任务自己的本地信号文件" />
                </label>
                <label className="toggle-line live-toggle">
                  <input type="checkbox" checked={monitorAllowLive} onChange={(event) => setMonitorAllowLive(event.target.checked)} />
                  <span>
                    允许联网采集
                    <small>{monitorAllowLive ? "运行时可能访问外部平台，请确认登录状态" : "保持本地检查，不访问外部平台"}</small>
                  </span>
                </label>
              </details>
              <div className="actions command-row">
                <button className="primary" disabled={monitorStatus === "running" || !keywords.trim()}>{savedId ? "保存修改" : "保存任务"}</button>
                <button type="button" disabled={monitorStatus === "running" || !keywords.trim()} onClick={() => void runMonitorOnce()}>运行一次</button>
                <button type="button" disabled={monitorStatus === "running"} onClick={() => void refreshDigest()}>刷新摘要</button>
                {savedId && <button className="danger-button" type="button" disabled={monitorStatus === "running"} onClick={() => void deleteMonitor()}>删除</button>}
              </div>
            </form>
          ) : (
            <form className="brief-panel" onSubmit={submitChat}>
              <div className="panel-intro compact">
                <p className="section-kicker">对话任务</p>
                <h2>把一句需求变成一次分析</h2>
              </div>
              <BriefBuilder
                taskType={taskType}
                outputTarget={outputTarget}
                sourceContext={sourceContext}
                allowLive={allowLive}
                onTaskTypeChange={setTaskType}
                onOutputTargetChange={setOutputTarget}
                onSourceContextChange={setSourceContext}
                onAllowLiveChange={setAllowLive}
              />
              <label className="brief-input">
                需求
                <textarea value={query} onChange={(event) => setQuery(event.target.value)} rows={7} placeholder="写下目标人群、平台、素材和你想判断的问题。" />
              </label>
              <div className="actions command-row">
                <button className="primary" disabled={["queued", "running", "cancelling"].includes(chatStatus) || !query.trim()}>
                  {["queued", "running", "cancelling"].includes(chatStatus) ? "运行中" : "开始分析"}
                </button>
                <button type="button" disabled={["queued", "running", "cancelling"].includes(chatStatus)} onClick={() => { setQuery(""); setRun(null); setChatError(""); setChatStatus("pending"); }}>清空</button>
                {run && ["queued", "running", "cancelling"].includes(run.status) && (
                  <button type="button" disabled={run.status === "cancelling"} onClick={() => void cancelRun()}>
                    {run.status === "cancelling" ? "正在取消" : "取消任务"}
                  </button>
                )}
                {run && ["failed", "cancelled"].includes(run.status) && <button type="button" onClick={() => void retryRun()}>重新运行</button>}
              </div>
            </form>
          )}
        </main>

        <aside className="home-rail">
          <section className="studio-panel status-panel">
            <div className="panel-head">
              <div>
                <p className="section-kicker">状态</p>
                <h2>{mode === "monitor" ? "监控任务" : "对话进度"}</h2>
              </div>
              <StatusBadge status={activeStatus} />
            </div>
            {mode === "chat" && <RunTimeline status={chatStatus} stages={run?.stages} />}
            {chatError && <ErrorNotice message={chatError} />}
            {monitorError && <ErrorNotice message={monitorError} />}
            {authIssue && (
              <div className="notice auth-required" role="status">
                <div>
                  <strong>需要重新登录</strong>
                  <p>任务失败可能和平台登录状态有关。去设置页更新账号后再试。</p>
                </div>
                <button type="button" onClick={() => onOpenSettings(authIssue === "all" ? undefined : authIssue)}>去设置</button>
              </div>
            )}
            {mode === "monitor" && monitorResult && <ResultSummary value={monitorResult} />}
            {mode === "monitor" && digest && <ResultSummary value={digest} title="监控摘要" />}
            {mode === "chat" && run && (
              <div className="result-list">
                <div><span>任务编号</span><strong>{run.run_id}</strong></div>
                <div><span>执行路线</span><strong>{routeLabel(run.route)}</strong></div>
                {run.status === "success" && <button type="button" onClick={onOpenReports}>查看报告</button>}
              </div>
            )}
          </section>

          {mode === "monitor" && (
            <section className="studio-panel saved-jobs compact-list">
              <div className="panel-head"><h2>已保存</h2><span className="env-pill">{jobs.length}</span></div>
              <div className="report-list">
                {jobs.length === 0 && <p className="muted">保存后会出现在这里。</p>}
                {jobs.map((job) => (
                  <button key={job.job_id || job.name} className={savedId === job.job_id ? "report-row active" : "report-row"} type="button" onClick={() => loadSavedJob(job)}>
                    <span><strong>{job.name}</strong><small>{job.keywords.join(", ")}</small></span>
                    <span className="env-pill">{job.allow_live ? "联网" : `${Math.round(job.interval_seconds / 60)} 分钟`}</span>
                  </button>
                ))}
              </div>
            </section>
          )}
          {mode === "chat" && (
            <section className="studio-panel saved-jobs compact-list">
              <div className="panel-head"><h2>最近任务</h2><span className="env-pill">{recentRuns.length}</span></div>
              <div className="report-list">
                {recentRuns.length === 0 && <p className="muted">任务创建后会保留在这里，刷新页面也能继续查看。</p>}
                {recentRuns.slice(0, 8).map((item) => (
                  <button
                    key={item.run_id}
                    className={run?.run_id === item.run_id ? "report-row active" : "report-row"}
                    type="button"
                    onClick={() => { setRun(item); setChatStatus(item.status); }}
                  >
                    <span><strong>{runBrief(item.query)}</strong><small>{routeLabel(item.route)} · {formatTime(item.created_at)}</small></span>
                    <StatusBadge status={item.status} />
                  </button>
                ))}
              </div>
            </section>
          )}
        </aside>
      </div>
    </section>
  );
}

function ResultSummary({ value, title = "运行结果" }: { value: Record<string, unknown>; title?: string }) {
  const entries = Object.entries(value)
    .filter(([, item]) => item !== null && item !== undefined && typeof item !== "object")
    .slice(0, 6);
  return (
    <section className="result-summary" aria-label={title}>
      <strong>{title}</strong>
      <dl>
        {entries.map(([key, item]) => (
          <div key={key}><dt>{humanize(key)}</dt><dd>{String(item)}</dd></div>
        ))}
      </dl>
      {entries.length === 0 && <p className="muted">运行已完成，详细产物可在报告页查看。</p>}
    </section>
  );
}

function humanize(value: string): string {
  return ({
    status: "状态",
    event_count: "事件数量",
    signal_count: "信号数量",
    record_count: "记录数量",
    next_step: "下一步",
    created_at: "创建时间",
  } as Record<string, string>)[value] || value.replaceAll("_", " ");
}

function routeLabel(route: string): string {
  return ({
    trend_report_path: "趋势分析",
    imitation_plan_path: "仿拍方案",
    reference_video_imitation_path: "参考视频分析",
    full_pipeline_path: "联网全流程",
    commercial_data_analysis_path: "商业数据分析",
  } as Record<string, string>)[route] || route || "规划中";
}

function formatTime(value: string): string {
  const timestamp = new Date(value);
  return Number.isNaN(timestamp.getTime()) ? "时间未知" : timestamp.toLocaleString();
}

function runBrief(query?: string): string {
  if (!query) return "分析任务";
  const brief = query.split("简报：").pop()?.trim() || query;
  return brief.length > 42 ? `${brief.slice(0, 42)}…` : brief;
}
