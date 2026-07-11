export function EmptyState({ title, action }: { title: string; action: string }) {
  return (
    <div className="empty">
      <span className="logo-placeholder logo-placeholder-large quiet" aria-hidden="true" />
      <div>
        <strong>{title}</strong>
        <p>{action}</p>
      </div>
    </div>
  );
}
