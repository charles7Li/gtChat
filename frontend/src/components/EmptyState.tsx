export function EmptyState({ title, action }: { title: string; action: string }) {
  return (
    <div className="empty">
      <strong>{title}</strong>
      <span>{action}</span>
    </div>
  );
}
