export function SettingsPage({ apiBase, onApiBaseChange }: { apiBase: string; onApiBaseChange: (value: string) => void }) {
  return (
    <section className="content-grid">
      <div className="panel narrow">
        <h2>Runtime</h2>
        <label>
          API profile
          <select value={apiBase} onChange={(event) => onApiBaseChange(event.target.value)}>
            <option value="local">local</option>
            <option value="proxy">proxy</option>
          </select>
        </label>
        <p className="hint">前端默认使用同源 `/api`，Vite dev server 会代理到本地 FastAPI。</p>
      </div>
    </section>
  );
}
