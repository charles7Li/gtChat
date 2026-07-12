import { useEffect, useState } from "react";
import { api, type LoginState, type Platform } from "../api";
import type { ThemeId } from "../types";

const platforms: { id: Platform; name: string; hint: string }[] = [
  { id: "xiaohongshu", name: "小红书", hint: "保存后，采集、搜索和详情任务会复用这份登录状态。" },
  { id: "douyin", name: "抖音", hint: "保存后，榜单、搜索与详情任务会复用这份登录状态。" },
];

const themes: Array<{ id: ThemeId; name: string; mood: string; swatches: string[] }> = [
  { id: "ragdoll", name: "布偶猫", mood: "默认主题，奶白底色配灰蓝重点色，柔和但有辨识度。", swatches: ["#f4f6f8", "#dfe9ee", "#4d9fbd", "#4a3c35"] },
  { id: "siamese", name: "暹罗猫", mood: "更冷静利落，适合长时间看监控和信号。", swatches: ["#f7f5ef", "#d8d2c7", "#2f3b42", "#5a8aa0"] },
  { id: "calico", name: "三花猫", mood: "白底、橘棕和墨黑的组合，适合创作和对话场景。", swatches: ["#faf7f1", "#df8a45", "#2d2925", "#d59aa4"] },
  { id: "tabby", name: "狸花猫", mood: "灰褐和墨绿灰更稳，适合报告、证据和研究感。", swatches: ["#f1f2ec", "#a49a83", "#334239", "#6f7a63"] },
];

type SettingsPageProps = {
  apiBase: string;
  theme: ThemeId;
  onApiBaseChange: (value: string) => void;
  onThemeChange: (value: ThemeId) => void;
};

export function SettingsPage({ apiBase, theme, onApiBaseChange, onThemeChange }: SettingsPageProps) {
  const [states, setStates] = useState<Partial<Record<Platform, LoginState>>>({});
  const [cookieText, setCookieText] = useState<Record<Platform, string>>({ xiaohongshu: "", douyin: "" });
  const [saving, setSaving] = useState<Platform | null>(null);
  const [message, setMessage] = useState<Record<Platform, string>>({ xiaohongshu: "", douyin: "" });

  useEffect(() => {
    api.authStatus()
      .then(setStates)
      .catch(() => setMessage((current) => ({ ...current, xiaohongshu: "无法读取登录状态，请确认本地 API 已启动。" })));
  }, []);

  async function save(platform: Platform) {
    try {
      const parsed: unknown = JSON.parse(cookieText[platform]);
      if (!Array.isArray(parsed) || parsed.length === 0) throw new Error("请粘贴非空的 Cookie JSON 数组。");
      setSaving(platform);
      setMessage((current) => ({ ...current, [platform]: "" }));
      const state = await api.saveAuthState(platform, parsed as Record<string, unknown>[]);
      setStates((current) => ({ ...current, [platform]: state }));
      setCookieText((current) => ({ ...current, [platform]: "" }));
      setMessage((current) => ({ ...current, [platform]: "登录状态已保存到本机。" }));
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
          <p className="section-kicker">偏好</p>
          <h2>界面主题</h2>
          <p>主题只改变工作台的颜色气质，不改变功能结构。默认使用布偶猫主题。</p>
        </div>
        <div className="theme-grid" role="radiogroup" aria-label="界面主题">
          {themes.map((item) => (
            <button
              key={item.id}
              type="button"
              className={theme === item.id ? "theme-option active" : "theme-option"}
              onClick={() => onThemeChange(item.id)}
              role="radio"
              aria-checked={theme === item.id}
            >
              <span className="theme-swatches" aria-hidden="true">
                {item.swatches.map((color) => <span key={color} style={{ background: color }} />)}
              </span>
              <span>
                <strong>{item.name}</strong>
                <small>{item.mood}</small>
              </span>
            </button>
          ))}
        </div>
      </div>

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
          <div><dt>联网采集</dt><dd>默认关闭，运行时单独授权。</dd></div>
          <div><dt>凭证存储</dt><dd>仅保存在当前设备的本地 profile 目录。</dd></div>
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
                    placeholder='[{"name":"sessionid","value":"...","domain":".example.com","path":"/"}]'
                    spellCheck={false}
                  />
                </label>
                <div className="auth-actions">
                  <button className="primary" type="button" onClick={() => save(platform.id)} disabled={saving !== null || !cookieText[platform.id].trim()}>
                    {saving === platform.id ? "正在保存" : "保存登录状态"}
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
