import { useEffect, useState } from "react";
import { Sidebar } from "./components/Sidebar";
import { ChatPage } from "./pages/ChatPage";
import { MonitorPage } from "./pages/MonitorPage";
import { ReportsPage } from "./pages/ReportsPage";
import { SettingsPage } from "./pages/SettingsPage";
import { UploadPage } from "./pages/UploadPage";

export type Page = "chat" | "monitor" | "uploads" | "reports" | "settings";

const titles: Record<Page, string> = {
  chat: "Agent Chat",
  monitor: "定时任务",
  uploads: "素材上传",
  reports: "报告库",
  settings: "设置",
};

export default function App() {
  const [page, setPage] = useState<Page>("chat");
  const [apiBase, setApiBase] = useState("local");

  useEffect(() => {
    document.title = `${titles[page]} · gtChat`;
  }, [page]);

  return (
    <div className="app-shell">
      <Sidebar page={page} onChange={setPage} />
      <main className="workspace">
        <header className="topbar">
          <div>
            <p className="product-name">gtChat</p>
            <h1>{titles[page]}</h1>
          </div>
          <span className="env-pill">{apiBase}</span>
        </header>
        {page === "chat" && <ChatPage onOpenReports={() => setPage("reports")} />}
        {page === "monitor" && <MonitorPage />}
        {page === "uploads" && <UploadPage onOpenReports={() => setPage("reports")} />}
        {page === "reports" && <ReportsPage />}
        {page === "settings" && <SettingsPage apiBase={apiBase} onApiBaseChange={setApiBase} />}
      </main>
    </div>
  );
}
