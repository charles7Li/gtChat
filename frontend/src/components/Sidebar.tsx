import type { Page } from "../App";

const items: Array<{ id: Page; label: string; detail: string; icon: string }> = [
  { id: "chat", label: "简报", detail: "生成任务", icon: "简" },
  { id: "uploads", label: "素材", detail: "视频与数据", icon: "素" },
  { id: "reports", label: "报告", detail: "阅读器", icon: "报" },
  { id: "monitor", label: "信号", detail: "本地检查", icon: "信" },
  { id: "settings", label: "设置", detail: "运行环境", icon: "设" },
];

export function Sidebar({ page, onChange }: { page: Page; onChange: (page: Page) => void }) {
  return (
    <nav className="sidebar" aria-label="主导航">
      <button className="brand-lockup" type="button" onClick={() => onChange("chat")} aria-label="打开简报">
        <span className="logo-placeholder" aria-hidden="true" />
        <span>
          <strong>Mochi Scout</strong>
          <small>创作者情报室</small>
        </span>
      </button>
      <div className="nav-list">
        {items.map((item) => (
          <button key={item.id} className={page === item.id ? "nav-item active" : "nav-item"} onClick={() => onChange(item.id)}>
            <span className="nav-icon" aria-hidden="true">{item.icon}</span>
            <span>
              <strong>{item.label}</strong>
              <small>{item.detail}</small>
            </span>
          </button>
        ))}
      </div>
      <div className="sidebar-footer">
        <span className="signal-dot" aria-hidden="true" />
        <span>本地优先</span>
      </div>
    </nav>
  );
}
