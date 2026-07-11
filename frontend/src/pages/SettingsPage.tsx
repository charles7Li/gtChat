import { useEffect, useState } from "react";
import { api, type LoginState, type Platform } from "../api";

const platforms: { id: Platform; name: string; hint: string }[] = [
  { id: "xiaohongshu", name: "小红书", hint: "保存后，采集器会在新的浏览器会话中自动载入。" },
  { id: "douyin", name: "抖音", hint: "保存后，搜索、详情与热榜接口会复用这份登录态。" },
];

export function SettingsPage({ apiBase, onApiBaseChange }: { apiBase: string; onApiBaseChange: (value: string) => void }) {
  const [states, setStates] = useState<Partial<Record<Platform, LoginState>>>({});
  const [cookieText, setCookieText] = useState<Record<Platform, string>>({ xiaohongshu: "", douyin: "" });
  const [saving, setSaving] = useState<Platform | null>(null);
  const [message, setMessage] = useState<Record<Platform, string>>({ xiaohongshu: "", douyin: "" });

  useEffect(() => {
    api.authStatus().then(setStates).catch(() => setMessage((current) => ({ ...current, xiaohongshu: "无法读取登录状态，请确认本地 API 已启动。" })));
  }, []);

  async function save(platform: Platform) {
    try {
      const parsed: unknown = JSON.parse(cookieText[platform]);
      if (!Array.isArray(parsed) || parsed.length === 0) throw new Error("请粘贴非空的 Cookie JSON 数组。 ");
      setSaving(platform);
      setMessage((current) => ({ ...current, [platform]: "" }));
      const state = await api.saveAuthState(platform, parsed as Record<string, unknown>[]);
      setStates((current) => ({ ...current, [platform]: state }));
      setCookieText((current) => ({ ...current, [platform]: "" }));
      setMessage((current) => ({ ...current, [platform]: "登录态已安全保存到本机。" }));
    } catch (error) {
      setMessage((current) => ({ ...current, [platform]: error instanceof Error ? error.message : "保存失败" }));
    } finally {
      setSaving(null);
    }
  }

  return (
    <section className="settings-layout">
      <div className="studio-panel settings-panel">
        <div className="panel-intro compact">
          <p className="section-kicker">运行</p>
          <h2>本地优先</h2>
        </div>
        <label>
          API 模式
          <select value={apiBase} onChange={(event) => onApiBaseChange(event.target.value)}>
            <option value="local">local</option>
            <option value="proxy">proxy</option>
          </select>
        </label>
        <dl className="settings-list">
          <div><dt>默认接口</dt><dd>/api</dd></div>
          <div><dt>联网采集</dt><dd>默认关闭，运行时单独授权</dd></div>
          <div><dt>凭证存储</dt><dd>仅保存在当前设备的 .profiles 目录</dd></div>
        </dl>
      </div>

      <div className="studio-panel auth-panel">
        <div className="panel-intro compact">
          <p className="section-kicker">采集账号</p>
          <h2>平台登录状态</h2>
          <p>从浏览器导出 Cookie JSON 数组并粘贴保存。凭证不会在状态查询中返回。</p>
        </div>
        <div className="auth-platforms">
          {platforms.map((platform) => {
            const state = states[platform.id];
            const isSaved = state?.status === "saved";
            return (
              <section className="auth-platform" key={platform.id}>
                <div className="auth-platform-head">
                  <div><h3>{platform.name}</h3><p>{platform.hint}</p></div>
                  <span className={`status ${isSaved ? "status-success" : "status-unknown"}`}>
                    {isSaved ? `已保存 · ${state.cookie_count} 项` : state?.status === "invalid" ? "数据无效" : "未登录"}
                  </span>
                </div>
                <label>
                  Cookie JSON
                  <textarea
                    rows={4}
                    value={cookieText[platform.id]}
                    onChange={(event) => setCookieText((current) => ({ ...current, [platform.id]: event.target.value }))}
                    placeholder='[{"name":"sessionid","value":"…","domain":".example.com","path":"/"}]'
                    spellCheck={false}
                  />
                </label>
                <div className="auth-actions">
                  <button className="primary" onClick={() => save(platform.id)} disabled={saving !== null || !cookieText[platform.id].trim()}>
                    {saving === platform.id ? "正在保存…" : "保存登录态"}
                  </button>
                  {message[platform.id] && <p className="auth-message" role="status">{message[platform.id]}</p>}
                </div>
              </section>
            );
          })}
        </div>
      </div>
    </section>
  );
}
