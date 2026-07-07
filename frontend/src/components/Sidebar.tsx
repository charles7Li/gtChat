import type { Page } from "../App";

const items: Array<{ id: Page; label: string; icon: string }> = [
  { id: "chat", label: "Chat", icon: "⌘" },
  { id: "monitor", label: "Tasks", icon: "◷" },
  { id: "uploads", label: "Assets", icon: "⇧" },
  { id: "reports", label: "Reports", icon: "▤" },
  { id: "settings", label: "Settings", icon: "⚙" },
];

export function Sidebar({ page, onChange }: { page: Page; onChange: (page: Page) => void }) {
  return (
    <nav className="sidebar" aria-label="Primary">
      <div className="mark">gt</div>
      <div className="nav-list">
        {items.map((item) => (
          <button key={item.id} className={page === item.id ? "nav-item active" : "nav-item"} onClick={() => onChange(item.id)}>
            <span aria-hidden="true">{item.icon}</span>
            {item.label}
          </button>
        ))}
      </div>
    </nav>
  );
}
