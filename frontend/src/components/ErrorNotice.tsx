export function ErrorNotice({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return (
    <div className="notice error" role="alert">
      <span>{message}</span>
      {onRetry && <button onClick={onRetry}>Retry</button>}
    </div>
  );
}
