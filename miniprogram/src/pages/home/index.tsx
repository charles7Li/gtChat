import { useState } from "react";
import Taro, { useDidShow, usePullDownRefresh } from "@tarojs/taro";
import { Button, Text, View } from "@tarojs/components";
import { api } from "../../api";
import { BottomNav } from "../../components/BottomNav";
import { EmptyState } from "../../components/EmptyState";
import { JobStatusBadge } from "../../components/JobStatus";
import type { MobileJob } from "../../types";

export default function HomePage() {
  const [jobs, setJobs] = useState<MobileJob[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  async function load() {
    setError("");
    try {
      setJobs((await api.listJobs()).slice(0, 3));
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "加载失败");
    } finally {
      setLoading(false);
      Taro.stopPullDownRefresh();
    }
  }

  useDidShow(() => { void load(); });
  usePullDownRefresh(() => { void load(); });

  return (
    <View className="page page--with-nav enter-page">
      <View className="brand-head">
        <View><Text className="brand">Mochi Scout</Text><Text className="brand-sub">移动研究台</Text></View>
        <Text className="brand-seal">麻薯</Text>
      </View>
      <View className="home-intro">
        <Text className="eyebrow">今天要研究什么</Text>
        <Text className="display-title">把一个内容问题，整理成可执行的下一步。</Text>
        <Button className="primary-action pressable" onClick={() => Taro.navigateTo({ url: "/pages/create/index" })}>新建分析任务</Button>
      </View>
      <View className="section-head">
        <Text className="section-title">最近任务</Text>
        <Text className="section-link" onClick={() => Taro.reLaunch({ url: "/pages/jobs/index" })}>查看全部</Text>
      </View>
      {loading && <Text className="muted">正在同步任务…</Text>}
      {error && <View className="inline-error"><Text>{error}</Text><Text onClick={() => void load()}>重试</Text></View>}
      {!loading && !error && jobs.length === 0 && <EmptyState title="还没有任务" body="从一个具体问题开始，任务会在后台完成。" />}
      <View className="task-list">
        {jobs.map((job) => (
          <View className="task-row pressable" key={job.id} onClick={() => Taro.navigateTo({ url: `/pages/job-detail/index?id=${job.id}` })}>
            <View className="task-row__main"><Text className="task-row__title">{job.query}</Text><Text className="task-row__meta">{formatTime(job.created_at)} · {job.progress.percent}%</Text></View>
            <JobStatusBadge status={job.status} />
          </View>
        ))}
      </View>
      <BottomNav active="home" />
    </View>
  );
}

function formatTime(value: string) {
  const date = new Date(value);
  return `${date.getMonth() + 1}月${date.getDate()}日 ${String(date.getHours()).padStart(2, "0")}:${String(date.getMinutes()).padStart(2, "0")}`;
}

