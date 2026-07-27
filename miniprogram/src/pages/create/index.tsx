import { useState } from "react";
import Taro from "@tarojs/taro";
import { Button, Picker, Text, Textarea, View } from "@tarojs/components";
import { api } from "../../api";
import type { UploadAsset } from "../../types";

const routes = [
  { value: "trend_report_path", label: "趋势分析", hint: "从已有数据中识别值得跟进的内容方向" },
  { value: "imitation_plan_path", label: "拍摄方案", hint: "把内容模式整理成可执行的拍摄简报" },
  { value: "reference_video_imitation_path", label: "参考视频分析", hint: "上传一个参考视频，拆解结构并生成可执行仿拍方案" },
  { value: "hotspot_auto_analysis_path", label: "热点判断", hint: "判断一个信号是否值得快速跟进" }
];
const LEGAL_VERSION = "2026-07-20";

export default function CreatePage() {
  const [routeIndex, setRouteIndex] = useState(0);
  const [query, setQuery] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");
  const [assets, setAssets] = useState<UploadAsset[]>([]);
  const [uploading, setUploading] = useState(false);
  const [legalAccepted, setLegalAccepted] = useState(false);
  const selected = routes[routeIndex];

  async function submit() {
    if (!query.trim()) return;
    if (!legalAccepted) {
      setError("请先阅读并同意用户协议与隐私保护指引。");
      return;
    }
    if (selected.value === "reference_video_imitation_path" && !assets.some((asset) => asset.file_type === "video")) {
      setError("参考视频分析需要先上传一个视频素材。");
      return;
    }
    setSubmitting(true);
    setError("");
    try {
      await api.saveLegalConsent(true, LEGAL_VERSION);
      const job = await api.createJob({ query: query.trim(), route: selected.value, asset_ids: assets.map((asset) => asset.id) });
      await Taro.redirectTo({ url: `/pages/job-detail/index?id=${job.id}` });
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "任务创建失败");
    } finally {
      setSubmitting(false);
    }
  }

  async function chooseMedia() {
    try {
      await requirePrivacyAuthorization();
      const result = await Taro.chooseMedia({ count: 1, mediaType: ["image", "video"], sourceType: ["album", "camera"] });
      const file = result.tempFiles[0];
      const extension = file.fileType === "video" ? "mp4" : "jpg";
      await upload({ path: file.tempFilePath, name: `素材-${Date.now()}.${extension}`, size: file.size, type: file.fileType === "video" ? "video/mp4" : "image/jpeg" });
    } catch (reason) {
      if ((reason as { errMsg?: string })?.errMsg?.includes("cancel")) return;
      setError(reason instanceof Error ? reason.message : "素材选择失败");
    }
  }

  async function chooseFile() {
    try {
      await requirePrivacyAuthorization();
      const result = await Taro.chooseMessageFile({ count: 1, type: "file", extension: ["csv", "json"] });
      const file = result.tempFiles[0];
      await upload({ path: file.path, name: file.name, size: file.size });
    } catch (reason) {
      if ((reason as { errMsg?: string })?.errMsg?.includes("cancel")) return;
      setError(reason instanceof Error ? reason.message : "文件选择失败");
    }
  }

  async function upload(file: { path: string; name: string; size: number; type?: string }) {
    setUploading(true);
    setError("");
    try {
      const uploaded = await api.uploadLocalFile(file);
      setAssets((current) => [...current, uploaded]);
    }
    catch (reason) { setError(reason instanceof Error ? reason.message : "上传失败"); }
    finally { setUploading(false); }
  }

  return (
    <View className="page enter-page">
      <View className="page-intro"><Text className="eyebrow">新建任务</Text><Text className="page-title">先说清问题，再开始分析。</Text><Text className="page-copy">小程序暂时只使用已有数据和上传素材，不会读取你的平台登录状态。</Text></View>
      <View className="form-block">
        <Text className="field-label">任务类型</Text>
        <Picker mode="selector" range={routes.map((item) => item.label)} value={routeIndex} onChange={(event) => setRouteIndex(Number(event.detail.value))}>
          <View className="picker-field pressable"><View><Text>{selected.label}</Text><Text className="field-hint">{selected.hint}</Text></View><Text>⌄</Text></View>
        </Picker>
      </View>
      <View className="form-block">
        <Text className="field-label">参考素材（可选）</Text>
        <View className="upload-actions">
          <Button className="upload-action" disabled={uploading || assets.length >= 3} onClick={() => void chooseMedia()}>图片 / 视频</Button>
          <Button className="upload-action" disabled={uploading || assets.length >= 3} onClick={() => void chooseFile()}>CSV / JSON</Button>
        </View>
        {uploading && <Text className="field-hint">正在上传素材，请勿离开…</Text>}
        <View className="asset-list">
          {assets.map((asset) => <View key={asset.id}><Text>{asset.filename}</Text><Text onClick={() => setAssets((current) => current.filter((item) => item.id !== asset.id))}>移除</Text></View>)}
        </View>
      </View>
      <View className="form-block">
        <Text className="field-label">你想判断什么</Text>
        <Textarea className="query-input" maxlength={4000} value={query} onInput={(event) => setQuery(event.detail.value)} placeholder="例如：分析宠物用品内容里最近值得跟进的三个角度，并给出拍摄建议。" />
        <Text className="input-count">{query.length}/4000</Text>
      </View>
      {error && <View className="inline-error"><Text>{error}</Text></View>}
      <View className="privacy-note pressable" onClick={() => setLegalAccepted((current) => !current)}>
        <Text>{legalAccepted ? "☑" : "☐"} 我已阅读并同意</Text>
        <Text onClick={(event) => { event.stopPropagation(); void Taro.navigateTo({ url: "/pages/legal/index?doc=terms" }); }}>《用户协议》</Text>
        <Text>与</Text>
        <Text onClick={(event) => { event.stopPropagation(); void Taro.navigateTo({ url: "/pages/legal/index?doc=privacy" }); }}>《隐私保护指引》</Text>
      </View>
      <Button className="primary-action pressable" disabled={!query.trim() || !legalAccepted || submitting || uploading} loading={submitting} onClick={() => void submit()}>{submitting ? "正在创建" : "开始分析"}</Button>
      <Text className="privacy-note">提交即表示你确认素材拥有合法使用权限。任务结果由 AI 辅助生成，请在发布前人工复核。</Text>
    </View>
  );
}

function requirePrivacyAuthorization(): Promise<void> {
  return new Promise((resolve, reject) => {
    Taro.requirePrivacyAuthorize({
      success: () => resolve(),
      fail: (reason) => reject(new Error(reason.errMsg || "需要同意隐私保护指引后才能选择素材"))
    });
  });
}
