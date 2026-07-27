import { Button, Text, View } from "@tarojs/components";
import { useRouter } from "@tarojs/taro";

const documents = {
  terms: {
    title: "用户协议",
    sections: [
      ["服务范围", "麻薯侦察为用户主动提交的素材和分析目标提供 AI 辅助研究报告。结果仅供参考，用户在发布、投放或作出商业决策前应自行复核。"],
      ["使用规则", "不得上传违法、侵权、含恶意代码或无权处理的内容；不得利用服务规避平台规则、批量骚扰或从事其他违法活动。"],
      ["账号与费用", "用户应妥善保管微信账号。任务可能调用第三方模型并产生计算成本；正式收费方案上线前会另行明确展示并征得同意。"],
      ["责任边界", "服务可能因网络、第三方平台或模型限制发生延迟和错误。我们会提供重试、取消和数据删除能力，但不保证 AI 结果绝对准确。"]
    ]
  },
  privacy: {
    title: "隐私保护指引",
    sections: [
      ["收集的信息", "登录时处理微信 OpenID；完成任务时处理用户输入、上传素材、任务状态和报告。服务端仅保存 OpenID 加密值及用于唯一索引的不可逆摘要。"],
      ["使用目的", "上述信息仅用于身份识别、素材分析、报告生成、任务通知、安全审核、故障排查和履行用户主动提出的数据删除请求。"],
      ["共享与存储", "素材可能按最小必要原则发送给所选模型、对象存储和内容安全供应商。正式版本会在本页列明供应商、处理地域和保存期限。"],
      ["用户权利", "用户可在“我的”页面撤回订阅、删除业务数据或注销账号。注销会删除在线主存储中的账号、任务、素材和报告；备份最长清除周期以正式隐私政策为准。"],
      ["权限说明", "相册、摄像头和订阅消息仅在用户主动上传或开启提醒时申请。拒绝后仍可使用不依赖对应权限的功能。"]
    ]
  },
  support: {
    title: "客服与反馈",
    sections: [
      ["问题反馈", "请说明任务编号、发生时间和问题现象。不要发送微信登录 code、access token、平台 Cookie 或其他敏感凭证。"],
      ["数据与账号", "如无法通过“我的”页面完成数据删除或账号注销，可通过下方微信客服提交请求。正式发布前将在此补充运营主体、工作时间和联系邮箱。"]
    ]
  }
} as const;

export default function LegalPage() {
  const { params } = useRouter();
  const key = params.doc === "privacy" || params.doc === "support" ? params.doc : "terms";
  const document = documents[key];
  return (
    <View className="page enter-page">
      <Text className="eyebrow">Mochi Scout</Text>
      <Text className="page-title">{document.title}</Text>
      <Text className="page-copy">当前为上线准备版本，正式主体信息、版本号与生效日期将在提审前补齐。</Text>
      <View className="settings-group">
        {document.sections.map(([title, body]) => (
          <View className="setting-row" key={title}>
            <View><Text>{title}</Text><Text className="field-hint">{body}</Text></View>
          </View>
        ))}
      </View>
      {key === "support" && <Button className="primary-action" openType="contact">联系微信客服</Button>}
    </View>
  );
}
