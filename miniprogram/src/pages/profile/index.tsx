import { useState } from "react";
import Taro from "@tarojs/taro";
import { Button, Text, View } from "@tarojs/components";
import { api, ensureSession } from "../../api";
import { BottomNav } from "../../components/BottomNav";

export default function ProfilePage() {
  const [working, setWorking] = useState(false);
  const [message, setMessage] = useState("");

  async function subscribe() {
    if (!MOCHI_TASK_TEMPLATE_ID) {
      setMessage("管理员尚未配置订阅消息模板。");
      return;
    }
    setWorking(true);
    try {
      await ensureSession();
      const requestSubscribe = Taro.requestSubscribeMessage as unknown as (
        options: { tmplIds: string[] }
      ) => Promise<Record<string, string>>;
      const result = await requestSubscribe({ tmplIds: [MOCHI_TASK_TEMPLATE_ID] });
      const granted = result[MOCHI_TASK_TEMPLATE_ID] === "accept";
      await api.saveSubscription(granted);
      setMessage(granted ? "任务完成提醒已开启。" : "你暂未授权任务完成提醒。");
    } catch (reason) {
      setMessage(reason instanceof Error ? reason.message : "设置失败");
    } finally {
      setWorking(false);
    }
  }

  async function deleteAccount() {
    const confirmed = await Taro.showModal({ title: "注销账号", content: "账号、任务、上传素材和报告将被删除，且无法恢复。", confirmText: "确认注销", confirmColor: "#a84632" });
    if (!confirmed.confirm) return;
    setWorking(true);
    try {
      await api.deleteAccount();
      setMessage("账号数据已删除。再次使用时会创建新账号。");
    } catch (reason) {
      setMessage(reason instanceof Error ? reason.message : "注销失败");
    } finally {
      setWorking(false);
    }
  }

  async function exportData() {
    setWorking(true);
    try {
      const exported = await api.exportData();
      const filePath = `${Taro.env.USER_DATA_PATH}/mochi-scout-data-${Date.now()}.json`;
      await writeTextFile(filePath, JSON.stringify(exported, null, 2));
      await Taro.shareFileMessage({ filePath, fileName: "mochi-scout-data.json" });
      setMessage("数据导出文件已生成。");
    } catch (reason) {
      setMessage(reason instanceof Error ? reason.message : "导出失败");
    } finally {
      setWorking(false);
    }
  }

  async function deleteData() {
    const confirmed = await Taro.showModal({ title: "删除业务数据", content: "任务、上传素材和报告将被删除，登录账号和授权设置会保留。", confirmText: "确认删除", confirmColor: "#a84632" });
    if (!confirmed.confirm) return;
    setWorking(true);
    try {
      await api.deleteData();
      setMessage("任务、素材和报告已删除。");
    } catch (reason) {
      setMessage(reason instanceof Error ? reason.message : "删除失败");
    } finally {
      setWorking(false);
    }
  }

  return (
    <View className="page page--with-nav enter-page">
      <View className="profile-head"><Text className="brand-seal brand-seal--large">麻薯</Text><View><Text className="page-title">我的</Text><Text className="page-copy">管理提醒、隐私和账号数据。</Text></View></View>
      <View className="settings-group">
        <View className="setting-row pressable" onClick={() => void subscribe()}><View><Text>任务完成提醒</Text><Text className="field-hint">每次提醒都需要微信授权</Text></View><Text>›</Text></View>
        <View className="setting-row"><View><Text>数据使用</Text><Text className="field-hint">仅用于完成你主动创建的分析任务</Text></View></View>
        <View className="setting-row"><View><Text>AI 内容说明</Text><Text className="field-hint">结果由 AI 辅助生成，发布前需人工复核</Text></View></View>
        <View className="setting-row pressable" onClick={() => void exportData()}><View><Text>导出我的数据</Text><Text className="field-hint">生成 JSON 文件并转发保存</Text></View><Text>›</Text></View>
        <View className="setting-row pressable" onClick={() => void deleteData()}><View><Text>删除任务与报告</Text><Text className="field-hint">保留账号，删除全部业务数据</Text></View><Text>›</Text></View>
      </View>
      {message && <View className="notice"><Text>{message}</Text></View>}
      <View className="legal-links">
        <Text onClick={() => Taro.navigateTo({ url: "/pages/legal/index?doc=terms" })}>用户协议</Text>
        <Text onClick={() => Taro.navigateTo({ url: "/pages/legal/index?doc=privacy" })}>隐私保护指引</Text>
        <Text onClick={() => Taro.navigateTo({ url: "/pages/legal/index?doc=support" })}>客服与反馈</Text>
      </View>
      <Button className="danger-action" disabled={working} onClick={() => void deleteAccount()}>注销账号并删除数据</Button>
      <Text className="filing-note">备案号待正式主体备案后填写</Text>
      <BottomNav active="profile" />
    </View>
  );
}

function writeTextFile(filePath: string, data: string): Promise<void> {
  return new Promise((resolve, reject) => {
    Taro.getFileSystemManager().writeFile({
      filePath,
      data,
      encoding: "utf8",
      success: () => resolve(),
      fail: (reason) => reject(new Error(reason.errMsg || "无法生成导出文件"))
    });
  });
}
