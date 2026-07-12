import { FormEvent, useEffect, useMemo, useState } from "react";
import { api, type LoginState, type Platform } from "../api";
import { BriefBuilder } from "../components/BriefBuilder";
import { ErrorNotice } from "../components/ErrorNotice";
import { RunTimeline } from "../components/RunTimeline";
import { StatusBadge } from "../components/StatusBadge";
import type { ChatRun, MonitorJob, RunStatus } from "../types";

type HomeMode = "monitor" | "chat";

const platformMeta: Record<Platform, { label: string; taskHint: string }> = {
  xiaohongshu: { label: "小红书", taskHint: "小红书采集与搜索任务" },
  douyin: { label: "抖音", taskHint: "抖音榜单、搜索与详情任务" },
};

const initialJob: MonitorJob = {
  name: "宠物热点检查",
  enabled: true,
  platforms: ["douyin_hot_board"],
  keywords: ["pet"],
  interval_seconds: 3600,
  allow_live: false,
  output_dir: "outputs/hotspot",
  rule: { min_heat_score: 80, min_growth_rate: 0, min_rank: 100, min_engagement: 0, required_sources: [] },
};

export function HomePage({ onOpenReports }: { onOpenReports: () => void }) {
  const [mode, setMode] = useState<HomeMode>("monitor");
  const [authStates, setAuthStates] = useState<Partial<Record<Platform, LoginState>>>({});
  const [authMessage, setAuthMessage] = useState<Record<Platform, string>>({ xiaohongshu: "", douyin: "" });
  const [authPanel, setAuthPanel] = useState<Platform | null>(null);
  const [authCookies, setAuthCookies] = useState<Record<Platform, string>>({ xiaohongshu: "", douyin: "" });
  const [savingAuth, setSavingAuth] = useState<Platform | null>(null);
  const [authIssue, setAuthIssue] = useState<Platform | "all" | null>(null);

  const [query, setQuery] = useState("帮我找出宠物内容里最值得跟进的角度，并整理成可执行的拍摄方案。");
  const [taskType, setTaskType] = useState("趋势分析");
  const [outputTarget, setOutputTarget] = useState("策略报告");
  const [sourceContext, setSourceContext] = useState("本地结果");
  const [allowLive, setAllowLive] = useState(false);
  const [chatStatus, setChatStatus] = useState<RunStatus>("pending");
  const [run, setRun] = useState<ChatRun | null>(null);
  const [chatError, setChatError] = useState("");

  const [job, setJob] = useState<MonitorJob>(initialJob);
  const [jobs, setJobs] = useState<MonitorJob[]>([]);
  const [savedId, setSavedId] = useState("");
  const [monitorStatus, setMonitorStatus] = useState<RunStatus>("pending");
  const [monitorResult, setMonitorResult] = useState<Record<string, unknown> | null>(null);
  const [digest, setDigest] = useState<Record<string, unknown> | null>(null);
  const [monitorError, setMonitorError] = useState("");

  const activeStatus = mode === "monitor" ? monitorStatus : chatStatus;
  const savedAuthCount = useMemo(
    () => Object.values(authStates).filter((state) => state?.status === "saved").length,
    [authStates],
  );

  useEffect(() => {
    void refreshAuthStates();
    void api.listJobs().then(setJobs).catch(() => setJobs([]));
  }, []);

  async function refreshAuthStates() {
    try {
      setAuthStates(await api.authStatus());
    } catch {
      setAuthIssue("all");
    }
  }

  async function saveAuth(platform: Platform) {
    try {
      const parsed: unknown = JSON.parse(authCookies[platform]);
      if (!Array.isArray(parsed) || parsed.length === 0) throw new Error("请粘贴非空的 Cookie JSON 数组。");
      setSavingAuth(platform);
      setAuthMessage((current) => ({ ...current, [platform]: "" }));
      const state = await api.saveAuthState(platform, parsed as Record<string, unknown>[]);
      setAuthStates((current) => ({ ...current, [platform]: state }));
      setAuthCookies((current) => ({ ...current, [platform]: "" }));
      setAuthMessage((current) => ({ ...current, [platform]: "登录状态已保存。" }));
      setAuthIssue((current) => current === platform || current === "all" ? null : current);
      setAuthPanel(null);
    } catch (error) {
      setAuthMessage((current) => ({ ...current, [platform]: error instanceof Error ? error.message : "保存失败" }));
    } finally {
      setSavingAuth(null);
    }
  }

  async function submitChat(event: FormEvent) {
    event.preventDefault();
    await runChat();
  }

  async function runChat() {
    const composedBrief = `任务：${taskType}。输出：${outputTarget}。来源：${sourceContext}。简报：${query}`;
    setChatStatus("running");
    setChatError("");
    setAuthIssue(null);
    try {
      const result = await api.runChat(composedBrief, allowLive);
      setRun(result);
      setChatStatus("success");
    } catch (error) {
      const message = error instanceof Error ? error.message : "运行失败";
      setChatStatus("failed");
      setChatError(message);
      markAuthIssue(message);
    }
  }

  async function saveMonitor(event: FormEvent) {
    event.preventDefault();
    setMonitorStatus("running");
    setMonitorError("");
    try {
      const saved = await api.saveJob(job);
      setSavedId(saved.job_id || "");
      setJobs(await api.listJobs());
      setMonitorStatus("success");
    } catch (error) {
      const message = error instanceof Error ? error.message : "保存失败";
      setMonitorStatus("failed");
      setMonitorError(message);
      markAuthIssue(message);
    }
  }

  async function runMonitorOnce() {
    if (!savedId) return;
    setMonitorStatus("running");
    setMonitorError("");
    setAuthIssue(null);
    try {
      setMonitorResult(await api.runJob(savedId));
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
      const message = error instanceof Error ? error.message : "摘要刷新失败";
      setMonitorStatus("failed");
      setMonitorError(message);
      markAuthIssue(message);
    }
  }

  function markAuthIssue(message: string) {
    const lower = message.toLowerCase();
    if (!/(auth|login|cookie|session|401|403|登录|未授权|凭证|认证)/i.test(message)) return;
    if (lower.includes("xhs") || message.includes("小红书")) setAuthIssue("xiaohongshu");
    else if (message.includes("抖音") || lower.includes("douyin")) setAuthIssue("douyin");
    else setAuthIssue("all");
  }

  function loadSavedJob(saved: MonitorJob) {
    setSavedId(saved.job_id || "");
    setJob(saved);
    setMode("monitor");
  }

  return (
    <section className="home-workbench">
      <section className="home-control-strip" aria-label="首页功能切换与登录状态">
        <div className="mode-switch" role="tablist" aria-label="首页功能">
          <button type="button" role="tab" aria-selected={mode === "monitor"} className={mode === "monitor" ? "active" : ""} onClick={() => setMode("monitor")}>
            定时任务监控
          </button>
          <button type="button" role="tab" aria-selected={mode === "chat"} className={mode === "chat" ? "active" : ""} onClick={() => setMode("chat")}>
            对话任务
          </button>
        </div>
        <div className="auth-strip" aria-label="平台登录状态">
          {(["xiaohongshu", "douyin"] as Platform[]).map((platform) => (
            <PlatformLogin
              key={platform}
              platform={platform}
              state={authStates[platform]}
              message={authMessage[platform]}
              cookieText={authCookies[platform]}
              isOpen={authPanel === platform}
              saving={savingAuth === platform}
              hasIssue={authIssue === "all" || authIssue === platform || authStates[platform]?.status === "invalid"}
              onToggle={() => setAuthPanel((current) => current === platform ? null : platform)}
              onCookieChange={(value) => setAuthCookies((current) => ({ ...current, [platform]: value }))}
              onSave={() => void saveAuth(platform)}
            />
          ))}
        </div>
      </section>

      <div className="home-grid">
        <main className="home-primary">
          {mode === "monitor" ? (
            <form className="studio-panel monitor-form" onSubmit={saveMonitor}>
              <div className="panel-intro compact">
                <p className="section-kicker">定时任务</p>
                <h2>编辑监控规则</h2>
                <p>首页直接完成保存、手动运行和后续排查；需要外部平台时先看上方登录灯。</p>
              </div>
              <div className="field-group">
                <label>任务名<input value={job.name} onChange={(event) => setJob({ ...job, name: event.target.value })} /></label>
                <label>间隔秒数<input type="number" min="60" value={job.interval_seconds} onChange={(event) => setJob({ ...job, interval_seconds: Number(event.target.value) })} /></label>
              </div>
              <div className="field-group">
                <label>平台<input value={job.platforms.join(",")} onChange={(event) => setJob({ ...job, platforms: split(event.target.value) })} /></label>
                <label>关键词<input value={job.keywords.join(",")} onChange={(event) => setJob({ ...job, keywords: split(event.target.value) })} /></label>
              </div>
              <div className="threshold-grid">
                <label>热度<input type="number" value={job.rule.min_heat_score || 0} onChange={(event) => setJob({ ...job, rule: { ...job.rule, min_heat_score: Number(event.target.value) } })} /></label>
                <label>增长<input type="number" step="0.01" value={job.rule.min_growth_rate || 0} onChange={(event) => setJob({ ...job, rule: { ...job.rule, min_growth_rate: Number(event.target.value) } })} /></label>
                <label>排名<input type="number" min="1" value={job.rule.min_rank || 1} onChange={(event) => setJob({ ...job, rule: { ...job.rule, min_rank: Number(event.target.value) } })} /></label>
                <label>互动<input type="number" min="0" value={job.rule.min_engagement || 0} onChange={(event) => setJob({ ...job, rule: { ...job.rule, min_engagement: Number(event.target.value) } })} /></label>
              </div>
              <label>信号路径<input value={job.signals_path || ""} onChange={(event) => setJob({ ...job, signals_path: event.target.value || undefined })} /></label>
              <label className="toggle-line live-toggle">
                <input type="checkbox" checked={job.allow_live} onChange={(event) => setJob({ ...job, allow_live: event.target.checked })} />
                <span>
                  允许联网
                  <small>{job.allow_live ? "可能访问外部服务，需要平台登录可用" : "默认本地检查"}</small>
                </span>
              </label>
              <div className="actions command-row">
                <button className="primary" disabled={monitorStatus === "running"}>保存任务</button>
                <button type="button" disabled={monitorStatus === "running" || !savedId} onClick={() => void runMonitorOnce()}>运行一次</button>
                <button type="button" disabled={monitorStatus === "running"} onClick={() => void refreshDigest()}>刷新摘要</button>
              </div>
            </form>
          ) : (
            <form className="brief-panel" onSubmit={submitChat}>
              <div className="panel-intro compact">
                <p className="section-kicker">对话任务</p>
                <h2>把一句需求变成一次分析</h2>
                <p>对话入口保留原来的简报构建器；当来源选择外部平台或允许联网时，上方登录状态会成为运行前检查。</p>
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
                <h2>{mode === "monitor" ? "监控运行" : "对话进度"}</h2>
              </div>
              <StatusBadge status={activeStatus} />
            </div>
            {mode === "chat" && <RunTimeline status={chatStatus} />}
            {mode === "monitor" && (
              <dl className="mini-context status-dl">
                <div><dt>已保存任务</dt><dd>{savedId || "未保存"}</dd></div>
                <div><dt>平台登录</dt><dd>{savedAuthCount}/2 可用</dd></div>
                <div><dt>重新登录</dt><dd>{authIssue ? "需要处理" : "无"}</dd></div>
              </dl>
            )}
            {chatError && <ErrorNotice message={chatError} onRetry={() => void runChat()} />}
            {monitorError && <ErrorNotice message={monitorError} onRetry={() => void runMonitorOnce()} />}
            {authIssue && (
              <div className="notice auth-required" role="status">
                <div>
                  <strong>登录状态需要更新</strong>
                  <p>任务失败可能由平台登录过期导致。请在上方重新保存对应平台的登录状态。</p>
                </div>
              </div>
            )}
          </section>

          {mode === "chat" ? (
            <section className="studio-panel mini-context">
              <p className="section-kicker">当前任务</p>
              {run ? (
                <div className="result-list">
                  <div><span>路径</span><strong>{run.route || "等待中"}</strong></div>
                  <div><span>报告</span><strong>{run.report_path || "等待中"}</strong></div>
                  <div><span>记录</span><strong>{run.trace_path || "等待中"}</strong></div>
                  <button type="button" onClick={onOpenReports}>查看报告</button>
                </div>
              ) : (
                <dl>
                  <div><dt>任务</dt><dd>{taskType}</dd></div>
                  <div><dt>输出</dt><dd>{outputTarget}</dd></div>
                  <div><dt>来源</dt><dd>{sourceContext}</dd></div>
                </dl>
              )}
            </section>
          ) : (
            <section className="studio-panel saved-jobs compact-list">
              <div className="panel-head"><h2>已保存</h2><span className="env-pill">{jobs.length}</span></div>
              <div className="report-list">
                {jobs.length === 0 && <p className="muted">保存后会出现在这里，便于回到首页继续编辑。</p>}
                {jobs.map((saved) => (
                  <button key={saved.job_id || saved.name} className={savedId === saved.job_id ? "report-row active" : "report-row"} type="button" onClick={() => loadSavedJob(saved)}>
                    <span><strong>{saved.name}</strong><small>{saved.platforms.join(", ")} · {saved.keywords.join(", ")}</small></span>
                    <span className="env-pill">{saved.allow_live ? "联网" : "本地"}</span>
                  </button>
                ))}
              </div>
              {monitorResult && <pre className="json-preview">{JSON.stringify(monitorResult, null, 2)}</pre>}
              {digest && <pre className="json-preview">{JSON.stringify(digest, null, 2)}</pre>}
            </section>
          )}
        </aside>
      </div>
    </section>
  );
}

function PlatformLogin({
  platform,
  state,
  message,
  cookieText,
  isOpen,
  saving,
  hasIssue,
  onToggle,
  onCookieChange,
  onSave,
}: {
  platform: Platform;
  state?: LoginState;
  message: string;
  cookieText: string;
  isOpen: boolean;
  saving: boolean;
  hasIssue: boolean;
  onToggle: () => void;
  onCookieChange: (value: string) => void;
  onSave: () => void;
}) {
  const isSaved = state?.status === "saved";
  const meta = platformMeta[platform];
  const statusText = hasIssue ? "需重登" : isSaved ? "已登录" : "未登录";

  return (
    <div className={isOpen ? "platform-login open" : "platform-login"}>
      <button type="button" className={hasIssue ? "platform-login-button needs-auth" : "platform-login-button"} onClick={onToggle} aria-expanded={isOpen}>
        <span className="login-light" aria-hidden="true" />
        <span>
          <strong>{meta.label}</strong>
          <small>{statusText}</small>
        </span>
      </button>
      {isOpen && (
        <div className="login-editor">
          <p>{meta.taskHint} 会复用这里保存的登录状态。</p>
          <label>
            Cookie JSON
            <textarea
              rows={4}
              value={cookieText}
              onChange={(event) => onCookieChange(event.target.value)}
              placeholder='[{"name":"sessionid","value":"...","domain":".example.com","path":"/"}]'
              spellCheck={false}
            />
          </label>
          <div className="auth-actions">
            <button className="primary" type="button" disabled={saving || !cookieText.trim()} onClick={onSave}>
              {saving ? "保存中" : "保存登录状态"}
            </button>
            {message && <p className="auth-message" role="status">{message}</p>}
          </div>
        </div>
      )}
    </div>
  );
}

function split(value: string): string[] {
  return value.split(",").map((item) => item.trim()).filter(Boolean);
}
