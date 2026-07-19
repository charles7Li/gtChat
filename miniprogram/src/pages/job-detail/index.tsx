import { useEffect, useState } from "react";
import Taro, { useRouter } from "@tarojs/taro";
import { Button, Text, View } from "@tarojs/components";
import { api } from "../../api";
import { JobProgress, JobStatusBadge } from "../../components/JobStatus";
import type { MobileJob } from "../../types";

export default function JobDetailPage() {
  const { params } = useRouter();
  const jobId = params.id || "";
  const [job, setJob] = useState<MobileJob | null>(null);
  const [error, setError] = useState("");
  const [working, setWorking] = useState(false);

  useEffect(() => {
    let active = true;
    let timer: ReturnType<typeof setTimeout> | undefined;
    async function load() {
      try {
        const next = await api.getJob(jobId);
        if (!active) return;
        setJob(next);
        setError("");
        if (["queued", "running"].includes(next.status)) timer = setTimeout(load, 3000);
      } catch (reason) {
        if (active) setError(reason instanceof Error ? reason.message : "任务加载失败");
      }
    }
    if (jobId) void load();
    return () => { active = false; if (timer) clearTimeout(timer); };
  }, [jobId]);

  async function cancel() {
    setWorking(true);
    try { setJob(await api.cancelJob(jobId)); }
    catch (reason) { setError(reason instanceof Error ? reason.message : "取消失败"); }
    finally { setWorking(false); }
  }

  async function retry() {
    setWorking(true);
    try { setJob(await api.retryJob(jobId)); }
    catch (reason) { setError(reason instanceof Error ? reason.message : "重试失败"); }
    finally { setWorking(false); }
  }

  if (!job && !error) return <View className="page"><Text className="muted">正在读取任务…</Text></View>;
  if (!job) return <View className="page"><View className="inline-error"><Text>{error}</Text></View></View>;

  return (
    <View className="page enter-page">
      <View className="detail-head"><Text className="eyebrow">任务详情</Text><JobStatusBadge status={job.status} /></View>
      <Text className="page-title page-title--query">{job.query}</Text>
      <JobProgress stage={job.progress.stage} percent={job.progress.percent} />
      <View className="detail-list">
        <View><Text>任务类型</Text><Text>{routeLabel(job.route)}</Text></View>
        <View><Text>任务编号</Text><Text selectable>{job.id}</Text></View>
      </View>
      {job.error_message && <View className="inline-error inline-error--stack"><Text>{job.error_code || "运行失败"}</Text><Text>{job.error_message}</Text></View>}
      <View className="action-stack">
        {job.status === "succeeded" && job.report_id && <Button className="primary-action" onClick={() => Taro.redirectTo({ url: `/pages/report-detail/index?id=${job.report_id}` })}>查看报告</Button>}
        {["queued", "running"].includes(job.status) && <Button className="secondary-action" disabled={working} onClick={() => void cancel()}>取消任务</Button>}
        {["failed", "cancelled"].includes(job.status) && <Button className="primary-action" disabled={working} onClick={() => void retry()}>重新运行</Button>}
      </View>
      <Text className="privacy-note">任务在服务端后台运行，离开此页不会中断。运行中取消会在安全检查点停止。</Text>
    </View>
  );
}

function routeLabel(route: string) {
  return ({ trend_report_path: "趋势分析", imitation_plan_path: "拍摄方案", hotspot_auto_analysis_path: "热点判断" } as Record<string, string>)[route] || "分析任务";
}

