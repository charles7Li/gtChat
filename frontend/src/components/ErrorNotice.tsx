export function ErrorNotice({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return (
    <div className="notice error" role="alert">
      <div>
        <strong>需要处理</strong>
        <p>{message}</p>
      </div>
      {onRetry && <button type="button" onClick={onRetry}>重试</button>}
    </div>
  );
}
