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

const defaultRule = { min_heat_score: 80, min_growth_rate: 0, min_rank: 100, min_engagement: 0, required_sources: [] };

export function HomePage({ onOpenReports, onOpenSettings }: { onOpenReports: () => void; onOpenSettings: () => void }) {
  const [mode, setMode] = useState<HomeMode>("monitor");
  const [authStates, setAuthStates] = useState<Partial<Record<Platform, LoginState>>>({});
  const [authIssue, setAuthIssue] = useState<Platform | "all" | null>(null);

  const [platform, setPlatform] = useState<MonitorPlatform>("douyin_hot_board");
  const [keywords, setKeywords] = useState("pet");
  const [intervalSeconds, setIntervalSeconds] = useState(3600);
  const [jobs, setJobs] = useState<MonitorJob[]>([]);
  const [savedId, setSavedId] = useState("");
  const [monitorStatus, setMonitorStatus] = useState<RunStatus>("pending");
  const [monitorResult, setMonitorResult] = useState<Record<string, unknown> | null>(null);
  const [monitorError, setMonitorError] = useState("");

  const [query, setQuery] = useState("帮我找出宠物内容里最值得跟进的角度，并整理成可执行的拍摄方案。");
  const [taskType, setTaskType] = useState("趋势分析");
  const [outputTarget, setOutputTarget] = useState("策略报告");
  const [sourceContext, setSourceContext] = useState("本地结果");
  const [allowLive, setAllowLive] = useState(false);
  const [chatStatus, setChatStatus] = useState<RunStatus>("pending");
  const [run, setRun] = useState<ChatRun | null>(null);
  const [chatError, setChatError] = useState("");

  const selectedPlatform = useMemo(
    () => platformOptions.find((item) => item.value === platform) || platformOptions[0],
    [platform],
  );
  const activeStatus = mode === "monitor" ? monitorStatus : chatStatus;

  useEffect(() => {
    void api.authStatus().then(setAuthStates).catch(() => setAuthIssue("all"));
    void api.listJobs().then(setJobs).catch(() => setJobs([]));
  }, []);

  function buildJob(): MonitorJob {
    const terms = keywords.split(",").map((item) => item.trim()).filter(Boolean);
    return {
      name: `${selectedPlatform.label} · ${terms[0] || "热点"}检查`,
      enabled: true,
      platforms: [platform],
      keywords: terms.length ? terms : ["pet"],
      interval_seconds: intervalSeconds,
      allow_live: false,
      output_dir: "outputs/hotspot",
      rule: defaultRule,
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

  async function submitChat(event: FormEvent) {
    event.preventDefault();
    const brief = `任务：${taskType}。输出：${outputTarget}。来源：${sourceContext}。简报：${query}`;
    setChatStatus("running");
    setChatError("");
    setAuthIssue(null);
    try {
      setRun(await api.runChat(brief, allowLive));
      setChatStatus("success");
    } catch (error) {
      const message = error instanceof Error ? error.message : "运行失败";
      setChatStatus("failed");
      setChatError(message);
      markAuthIssue(message);
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
          {platformOptions.map((item) => (
            <button key={item.auth} type="button" className="platform-login-button compact-auth" onClick={onOpenSettings}>
              <span className={authIssue === "all" || authIssue === item.auth || authStates[item.auth]?.status === "invalid" ? "login-light needs-auth" : "login-light"} aria-hidden="true" />
              <span>
                <strong>{item.auth === "douyin" ? "抖音" : "小红书"}</strong>
                <small>{authIssue === "all" || authIssue === item.auth || authStates[item.auth]?.status === "invalid" ? "需重登" : authStates[item.auth]?.status === "saved" ? "已登录" : "未登录"}</small>
              </span>
            </button>
          ))}
        </div>
      </section>

      <div className="home-grid">
        <main className="home-primary">
          {mode === "monitor" ? (
            <form className="studio-panel monitor-form compact-monitor" onSubmit={saveMonitor}>
              <div className="panel-intro compact">
                <p className="section-kicker">定时任务</p>
                <h2>监控一个关键词</h2>
                <p>只选平台、关键词和频率。阈值、路径和联网策略先用系统默认。</p>
              </div>
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
              <div className="actions command-row">
                <button className="primary" disabled={monitorStatus === "running" || !keywords.trim()}>保存任务</button>
                <button type="button" disabled={monitorStatus === "running" || !keywords.trim()} onClick={() => void runMonitorOnce()}>运行一次</button>
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
                <button className="primary" disabled={chatStatus === "running" || !query.trim()}>
                  {chatStatus === "running" ? "运行中" : "开始分析"}
                </button>
                <button type="button" onClick={() => { setQuery(""); setRun(null); setChatError(""); setChatStatus("pending"); }}>清空</button>
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
            {mode === "chat" && <RunTimeline status={chatStatus} />}
            {chatError && <ErrorNotice message={chatError} />}
            {monitorError && <ErrorNotice message={monitorError} />}
            {authIssue && (
              <div className="notice auth-required" role="status">
                <div>
                  <strong>需要重新登录</strong>
                  <p>任务失败可能和平台登录状态有关。去设置页更新账号后再试。</p>
                </div>
                <button type="button" onClick={onOpenSettings}>去设置</button>
              </div>
            )}
            {mode === "monitor" && monitorResult && <pre className="json-preview">{JSON.stringify(monitorResult, null, 2)}</pre>}
            {mode === "chat" && run && (
              <div className="result-list">
                <div><span>报告</span><strong>{run.report_path || "等待中"}</strong></div>
                <button type="button" onClick={onOpenReports}>查看报告</button>
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
                    <span className="env-pill">{Math.round(job.interval_seconds / 60)} 分钟</span>
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
