import { useState } from "react";
import Taro, { useDidShow, usePullDownRefresh } from "@tarojs/taro";
import { Text, View } from "@tarojs/components";
import { api } from "../../api";
import { BottomNav } from "../../components/BottomNav";
import { EmptyState } from "../../components/EmptyState";
import type { MobileReport } from "../../types";

export default function ReportsPage() {
  const [reports, setReports] = useState<MobileReport[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  async function load() {
    setError("");
    try { setReports(await api.listReports()); }
    catch (reason) { setError(reason instanceof Error ? reason.message : "加载失败"); }
    finally { setLoading(false); Taro.stopPullDownRefresh(); }
  }
  useDidShow(() => { void load(); });
  usePullDownRefresh(() => { void load(); });

  return (
    <View className="page page--with-nav enter-page">
      <View className="page-intro page-intro--compact"><Text className="eyebrow">知识沉淀</Text><Text className="page-title">报告</Text><Text className="page-copy">任务完成后，结论会整理到这里。原始 trace 只在管理端保留。</Text></View>
      {loading && <Text className="muted">正在同步报告…</Text>}
      {error && <View className="inline-error"><Text>{error}</Text><Text onClick={() => void load()}>重试</Text></View>}
      {!loading && !error && reports.length === 0 && <EmptyState title="还没有报告" body="完成一次分析后，这里会出现可阅读的结论。" />}
      <View className="report-list">
        {reports.map((report) => (
          <View className="report-row pressable" key={report.id} onClick={() => Taro.navigateTo({ url: `/pages/report-detail/index?id=${report.id}` })}>
            <Text className="report-row__date">{formatDate(report.created_at)}</Text>
            <Text className="report-row__title">{report.title}</Text>
            <Text className="report-row__summary">{report.summary || "分析报告"}</Text>
          </View>
        ))}
      </View>
      <BottomNav active="reports" />
    </View>
  );
}

function formatDate(value: string) {
  const date = new Date(value);
  return `${date.getFullYear()}.${String(date.getMonth() + 1).padStart(2, "0")}.${String(date.getDate()).padStart(2, "0")}`;
}

