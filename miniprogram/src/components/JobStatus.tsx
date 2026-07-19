import { Text, View } from "@tarojs/components";
import type { JobStatus } from "../types";

const labels: Record<JobStatus, string> = {
  queued: "等待中",
  running: "分析中",
  succeeded: "已完成",
  failed: "失败",
  cancelled: "已取消"
};

export function JobStatusBadge({ status }: { status: JobStatus }) {
  return <Text className={`status status--${status}`}>{labels[status]}</Text>;
}

export function JobProgress({ stage, percent }: { stage: string; percent: number }) {
  return (
    <View className="progress">
      <View className="progress__head"><Text>{stageLabel(stage)}</Text><Text>{percent}%</Text></View>
      <View className="progress__track"><View className="progress__fill" style={{ width: `${percent}%` }} /></View>
    </View>
  );
}

function stageLabel(stage: string) {
  const labels: Record<string, string> = {
    queued: "等待执行",
    starting: "准备分析",
    trend_analyze: "识别趋势",
    pattern_extract: "提取内容模式",
    imitation_plan: "生成执行方案",
    report: "整理报告",
    completed: "分析完成",
    failed: "运行失败"
  };
  return labels[stage] || "正在处理";
}

