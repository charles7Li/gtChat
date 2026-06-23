请基于当前项目实现一个简单版 Planner-driven Multi-Agent Workflow，不要做复杂 Supervisor，不要引入外部 memory 框架，不要大改现有 Collector / Cleaner / Storage / Output 结构。

## 目标

在现有 LangGraph 管道基础上，增加：

1. PlanAgent：解析用户输入，生成结构化执行计划。
2. IntentRouter：根据 PlanAgent 的 route 字段选择执行路径。
3. TrendAnalyzerAgent：分析热门趋势。
4. PatternExtractorAgent：提取爆款内容套路。
5. ImitationPlannerAgent：生成可仿拍选题方案。
6. ReviewAgent：对生成方案打分并给修改建议。
7. ReportWriterAgent：生成最终 Markdown 报告。
8. agent_trace.json：记录本次选择了哪些 agent、走了什么路径、最终评分是多少。

第一版只支持 3 条 route：

- `trend_report_path`：趋势分析报告
- `imitation_plan_path`：仿拍选题策划
- `full_pipeline_path`：采集、分析、仿拍、评审、报告完整流程

## 不做的事情

第一版暂时不要做：

- 不做全局 SupervisorAgent
- 不做多轮 Agent 自由对话
- 不接 Mem0 / Letta / memU / ReMe
- 不做复杂长期记忆
- 不做图片 OCR / 视频下载
- 不做抖音采集接入
- 不重构现有小红书 Playwright 采集脚本

## 推荐目录结构

在现有项目中新增或修改以下模块：

```text
app/
  agents/
    __init__.py
    plan_agent.py
    trend_analyzer_agent.py
    pattern_extractor_agent.py
    imitation_planner_agent.py
    review_agent.py
    report_writer_agent.py

  schemas/
    __init__.py
    plan.py
    analysis.py
    report.py

  workflow/
    router.py
    graph.py

  memory/
    __init__.py
    simple_memory.py

  utils/
    count_parser.py
    time_parser.py
    json_loader.py
```

如果项目中已有同名目录或已有 graph 文件，请在现有结构上扩展，不要重复造入口。

## State 设计

请定义一个统一的 LangGraph state，大致包含：

```python
{
    "user_query": str,
    "plan": dict,
    "route": str,

    "keyword": str,
    "platform": str,
    "time_filter": str,
    "sort": str,
    "deep_limit": int,

    "raw_items": list,
    "clean_items": list,

    "trend_analysis": dict,
    "pattern_analysis": dict,
    "imitation_plans": list,
    "review_result": dict,

    "final_report": str,
    "agent_trace": dict,
    "errors": list
}
```

## PlanAgent

PlanAgent 接收 `user_query`，输出结构化 plan。

输出格式示例：

```json
{
  "task_type": "trend_analysis_and_imitation_planning",
  "route": "full_pipeline_path",
  "platform": "xiaohongshu",
  "keyword": "宠物",
  "time_filter": "一周内",
  "sort": "popularity_descending",
  "deep_limit": 10,
  "need_collection": true,
  "need_trend_analysis": true,
  "need_pattern_extraction": true,
  "need_imitation_planning": true,
  "need_review": true,
  "output_format": "markdown_report"
}
```

PlanAgent 第一版可以用规则实现，不一定必须调用 LLM。

规则建议：

- 用户输入包含“趋势 / 分析 / 最近 / 什么火” → `trend_report_path`
- 用户输入包含“仿拍 / 选题 / 策划 / 参考爆款” → `imitation_plan_path`
- 用户输入包含“从采集到 / 全流程 / 生成脚本 / 完整” → `full_pipeline_path`
- 没有明确关键词时默认 keyword 为“宠物”
- 默认 platform 为 `xiaohongshu`
- 默认 time_filter 为“一周内”
- 默认 sort 为 `popularity_descending`
- 默认 deep_limit 为 10

## Router

Router 只读取 `state["route"]`，不要直接读用户原话。

支持：

```python
if route == "trend_report_path":
    return "trend_report_path"

if route == "imitation_plan_path":
    return "imitation_plan_path"

if route == "full_pipeline_path":
    return "full_pipeline_path"
```

如果 route 不合法，默认走 `trend_report_path`。

## 三条路径

### 1. trend_report_path

```text
PlanAgent
  -> MemoryLoadNode
  -> CollectorNode or LoadLatestSearchResultsNode
  -> CleanerNode
  -> TrendAnalyzerAgent
  -> PatternExtractorAgent
  -> ReportWriterAgent
  -> TraceWriterNode
```

### 2. imitation_plan_path

```text
PlanAgent
  -> MemoryLoadNode
  -> LoadLatestSearchResultsNode
  -> CleanerNode
  -> TrendAnalyzerAgent
  -> PatternExtractorAgent
  -> ImitationPlannerAgent
  -> ReviewAgent
  -> ReportWriterAgent
  -> TraceWriterNode
```

### 3. full_pipeline_path

```text
PlanAgent
  -> MemoryLoadNode
  -> CollectorNode
  -> CleanerNode
  -> StorageNode
  -> TrendAnalyzerAgent
  -> PatternExtractorAgent
  -> ImitationPlannerAgent
  -> ReviewAgent
  -> ReportWriterAgent
  -> MemoryWriteNode
  -> TraceWriterNode
```

## Collector 接入要求

第一版不要重写现有小红书采集脚本。

可以先通过 subprocess 调用现有脚本：

```text
python C:\Users\Charles\.xiaohongshu-cli\playwright_search.py --keyword "{keyword}" --sort popularity_descending --time-filter "一周内" --deep --deep-limit 10
```

执行完成后，从 `C:\Users\Charles\.xiaohongshu-cli\search_results\` 中读取最新的 `search_*_deep_*.json`。

如果当前环境无法运行 Playwright，则提供 `LoadLatestSearchResultsNode`，直接读取最新 JSON 文件，保证 workflow 可以测试。

## CleanerNode 增强

第一版至少做这些清洗：

1. 把 `liked_count` 从 `"4.8万"` 转换为 `48000`
2. 把 `collected_count`、`comment_count` 转成 int
3. 把 Unix 毫秒时间戳转成可读日期
4. 过滤没有 title 且没有 body_text 的内容
5. 给每条 note 生成统一结构：

```json
{
  "id": "...",
  "title": "...",
  "body_text": "...",
  "tags": [],
  "metrics": {
    "liked_count": 48000,
    "collected_count": 1942,
    "comment_count": 4976
  },
  "content_type": "image_note",
  "image_count": 10,
  "author": "...",
  "url": "..."
}
```

## TrendAnalyzerAgent

输入：`clean_items`

输出：

```json
{
  "top_topics": [],
  "hot_emotions": [],
  "audience_pain_points": [],
  "high_engagement_reasons": [],
  "content_type_distribution": {},
  "summary": "..."
}
```

第一版可以先用 LLM，也可以先用规则统计：

- 高频标题关键词
- 高频 tags
- 点赞最高的前 5 条
- 评论高的内容特点
- 图文 / 视频数量分布

## PatternExtractorAgent

输入：`clean_items` + `trend_analysis`

输出：

```json
{
  "title_patterns": [],
  "opening_patterns": [],
  "body_patterns": [],
  "visual_patterns": [],
  "interaction_patterns": [],
  "replicable_templates": []
}
```

重点提取：

- 标题钩子
- 正文开头方式
- 情绪触发点
- 评论互动方式
- 可复用内容模板

## ImitationPlannerAgent

输入：`trend_analysis` + `pattern_analysis`

输出 3-5 个可仿拍方案：

```json
[
  {
    "idea_title": "...",
    "reference_pattern": "...",
    "shooting_scene": "...",
    "content_structure": [],
    "differentiation_point": "...",
    "required_props": [],
    "estimated_difficulty": "low / medium / high"
  }
]
```

要求：

- 不要直接复刻原笔记
- 必须说明参考了什么内容模式
- 必须给出差异化角度
- 必须给出拍摄场景和执行建议

## ReviewAgent

输入：`imitation_plans`

输出：

```json
{
  "overall_score": 86,
  "scores": {
    "trend_relevance": 90,
    "platform_fit": 85,
    "shooting_feasibility": 88,
    "originality": 80,
    "conversion_potential": 78
  },
  "best_plan_index": 0,
  "issues": [],
  "revision_suggestions": []
}
```

如果总分低于 75，第一版不必自动重写，只需要在报告里提示“建议修改”。

## ReportWriterAgent

输出 Markdown，文件名：

```text
outputs/final_package/trend_report.md
```

报告结构：

```markdown
# 小红书内容趋势分析报告

## 1. 本次任务

## 2. 数据概览

## 3. 热门趋势总结

## 4. 爆款内容套路

## 5. 可仿拍选题方案

## 6. ReviewAgent 评分

## 7. 后续建议
```

同时输出：

```text
outputs/final_package/manifest.json
outputs/final_package/agent_trace.json
```

## agent_trace.json

格式示例：

```json
{
  "user_query": "...",
  "route": "full_pipeline_path",
  "selected_agents": [
    "TrendAnalyzerAgent",
    "PatternExtractorAgent",
    "ImitationPlannerAgent",
    "ReviewAgent",
    "ReportWriterAgent"
  ],
  "execution_path": [
    "plan",
    "collect",
    "clean",
    "store",
    "trend_analyze",
    "pattern_extract",
    "imitation_plan",
    "review",
    "report"
  ],
  "final_score": 86,
  "created_at": "..."
}
```

## SimpleMemory 第一版

先做轻量文件记忆，不接外部框架。

新增：

```text
memory/
  trend_memory.md
  pattern_memory.md
  review_feedback.jsonl
```

MemoryLoadNode 读取已有 md/jsonl 内容，放到 state["memory_context"]。

MemoryWriteNode 在 full_pipeline_path 结束后追加：

- 本次关键词
- 趋势摘要
- 爆款模式摘要
- 最佳仿拍方案
- ReviewAgent 评分

## 测试要求

请新增或更新 pytest：

1. PlanAgent 能把“分析宠物赛道趋势”路由到 `trend_report_path`
2. PlanAgent 能把“生成仿拍选题”路由到 `imitation_plan_path`
3. PlanAgent 能把“从采集到报告全做一遍”路由到 `full_pipeline_path`
4. Cleaner 能正确解析 `"4.8万"` 为 `48000`
5. Router 能根据 route 返回正确路径
6. ReportWriter 能生成 `trend_report.md`
7. TraceWriter 能生成 `agent_trace.json`

最后运行：

```text
python -m pytest tests -q
```

确保原有测试不破坏。