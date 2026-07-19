import { useState } from "react";
import Taro, { useDidShow, usePullDownRefresh } from "@tarojs/taro";
import { Button, Text, View } from "@tarojs/components";
import { api } from "../../api";
import { BottomNav } from "../../components/BottomNav";
import { EmptyState } from "../../components/EmptyState";
import { JobStatusBadge } from "../../components/JobStatus";
import type { MobileJob } from "../../types";

export default function JobsPage() {
  const [jobs, setJobs] = useState<MobileJob[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  async function load() {
    setError("");
    try { setJobs(await api.listJobs()); }
    catch (reason) { setError(reason instanceof Error ? reason.message : "加载失败"); }
    finally { setLoading(false); Taro.stopPullDownRefresh(); }
  }
  useDidShow(() => { void load(); });
  usePullDownRefresh(() => { void load(); });

  return (
    <View className="page page--with-nav enter-page">
      <View className="section-head section-head--top"><View><Text className="eyebrow">运行记录</Text><Text className="page-title">任务</Text></View><Button className="compact-action" onClick={() => Taro.navigateTo({ url: "/pages/create/index" })}>新建</Button></View>
      {loading && <Text className="muted">正在同步任务…</Text>}
      {error && <View className="inline-error"><Text>{error}</Text><Text onClick={() => void load()}>重试</Text></View>}
      {!loading && !error && jobs.length === 0 && <EmptyState title="没有运行记录" body="新建一个任务后，可以在这里跟踪进度和重试。" />}
      <View className="task-list task-list--full">
        {jobs.map((job) => (
          <View className="task-row pressable" key={job.id} onClick={() => Taro.navigateTo({ url: `/pages/job-detail/index?id=${job.id}` })}>
            <View className="task-row__main"><Text className="task-row__title">{job.query}</Text><Text className="task-row__meta">{routeLabel(job.route)} · {job.progress.percent}%</Text></View>
            <JobStatusBadge status={job.status} />
          </View>
        ))}
      </View>
      <BottomNav active="jobs" />
    </View>
  );
}

function routeLabel(route: string) {
  return ({ trend_report_path: "趋势分析", imitation_plan_path: "拍摄方案", hotspot_auto_analysis_path: "热点判断" } as Record<string, string>)[route] || "分析任务";
}

