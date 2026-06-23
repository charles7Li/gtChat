# gtChat Planner Workflow

一个简单版 Planner-driven Multi-Agent Workflow，用规则驱动的 agent 管道完成小红书内容趋势分析、爆款模式提取、仿拍选题生成、方案评审和 Markdown 报告输出。

第一版刻意保持轻量：不做复杂 Supervisor，不引入外部 memory 框架，不重构现有采集脚本。

## 功能

- `PlanAgent`：解析用户输入，生成结构化执行计划
- `IntentRouter`：根据 `route` 选择执行路径
- `TrendAnalyzerAgent`：统计热门主题、情绪、痛点和内容类型分布
- `PatternExtractorAgent`：提取标题、正文、视觉和互动套路
- `ImitationPlannerAgent`：生成 3 个可仿拍选题方案
- `ReviewAgent`：对仿拍方案打分并给出修改建议
- `ReportWriterAgent`：输出最终 Markdown 报告、manifest 和 agent trace
- `SimpleMemory`：用本地文件保存轻量趋势、模式和评审反馈

## 路由

当前支持 3 条执行路径：

- `trend_report_path`：趋势分析报告
- `imitation_plan_path`：仿拍选题策划
- `full_pipeline_path`：采集、分析、仿拍、评审、报告完整流程

## 项目结构

```text
app/
  agents/      # 各类规则版 agent
  memory/      # 轻量文件记忆
  schemas/     # 计划、分析、报告结构
  utils/       # 计数、时间、JSON 加载工具
  workflow/    # 路由和节点式工作流
docs/
  plan.md      # 原始实现方案
tests/
  test_workflow.py
```

## 快速开始

安装测试依赖后运行：

```bash
python -m pytest tests -q
```

在 Python 中调用 workflow：

```python
from app.workflow import run_workflow

state = run_workflow("从采集到报告全做一遍")
print(state["report_path"])
```

默认输出目录：

```text
outputs/final_package/
  trend_report.md
  manifest.json
  agent_trace.json
```

## 设计文档

完整实现方案见 [docs/plan.md](docs/plan.md)。
