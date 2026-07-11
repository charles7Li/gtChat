type BriefBuilderProps = {
  taskType: string;
  outputTarget: string;
  sourceContext: string;
  allowLive: boolean;
  onTaskTypeChange: (value: string) => void;
  onOutputTargetChange: (value: string) => void;
  onSourceContextChange: (value: string) => void;
  onAllowLiveChange: (value: boolean) => void;
};

const taskTypes = ["趋势分析", "仿写方案", "拆解参考视频", "热点判断"];
const outputTargets = ["策略报告", "拍摄简报", "证据包", "监控任务"];
const sourceContexts = ["本地结果", "上传素材", "抖音/小红书来源", "商业化导出"];

export function BriefBuilder({
  taskType,
  outputTarget,
  sourceContext,
  allowLive,
  onTaskTypeChange,
  onOutputTargetChange,
  onSourceContextChange,
  onAllowLiveChange,
}: BriefBuilderProps) {
  return (
    <div className="brief-builder" aria-label="简报构建器">
      <div className="field-group">
        <label>
          任务
          <select value={taskType} onChange={(event) => onTaskTypeChange(event.target.value)}>
            {taskTypes.map((item) => <option key={item}>{item}</option>)}
          </select>
        </label>
        <label>
          输出
          <select value={outputTarget} onChange={(event) => onOutputTargetChange(event.target.value)}>
            {outputTargets.map((item) => <option key={item}>{item}</option>)}
          </select>
        </label>
      </div>
      <label>
        来源
        <select value={sourceContext} onChange={(event) => onSourceContextChange(event.target.value)}>
          {sourceContexts.map((item) => <option key={item}>{item}</option>)}
        </select>
      </label>
      <label className="toggle-line">
        <input type="checkbox" checked={allowLive} onChange={(event) => onAllowLiveChange(event.target.checked)} />
        <span>
          允许联网
          <small>{allowLive ? "可能访问外部服务" : "优先使用本地数据"}</small>
        </span>
      </label>
    </div>
  );
}
