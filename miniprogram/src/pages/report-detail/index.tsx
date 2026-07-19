import { useEffect, useState } from "react";
import { useRouter } from "@tarojs/taro";
import { Text, View } from "@tarojs/components";
import { api } from "../../api";
import { MarkdownView } from "../../components/MarkdownView";
import type { MobileReport } from "../../types";

export default function ReportDetailPage() {
  const { params } = useRouter();
  const [report, setReport] = useState<MobileReport | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!params.id) return;
    api.getReport(params.id).then(setReport).catch((reason) => setError(reason instanceof Error ? reason.message : "报告加载失败"));
  }, [params.id]);

  if (error) return <View className="page"><View className="inline-error"><Text>{error}</Text></View></View>;
  if (!report) return <View className="page"><Text className="muted">正在整理报告…</Text></View>;

  return (
    <View className="page report-page enter-page">
      <Text className="eyebrow">{formatDate(report.created_at)}</Text>
      <Text className="page-title report-title">{report.title}</Text>
      {report.summary && <Text className="report-lead">{report.summary}</Text>}
      <View className="hairline" />
      <MarkdownView markdown={report.markdown || "报告内容为空。"} />
      <View className="ai-note"><Text>AI 辅助生成</Text><Text>请结合原始素材与业务判断复核后使用。</Text></View>
    </View>
  );
}

function formatDate(value: string) {
  const date = new Date(value);
  return `${date.getFullYear()}年${date.getMonth() + 1}月${date.getDate()}日`;
}

