import type { RunStatus } from "../types";

const steps: RunStatus[] = ["pending", "running", "success"];

export function RunTimeline({ status }: { status: RunStatus }) {
  return (
    <ol className="timeline">
      {steps.map((step) => (
        <li key={step} className={step === status || (status === "failed" && step === "running") ? "current" : ""}>
          <span />
          {step}
        </li>
      ))}
      {status === "failed" && (
        <li className="current failed">
          <span />
          failed
        </li>
      )}
    </ol>
  );
}
