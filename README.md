<p align="center">
  <img src="https://img.shields.io/badge/python-3.11+-blue" alt="Python 3.11+">
  <img src="https://img.shields.io/badge/framework-LangGraph-green" alt="LangGraph">
  <img src="https://img.shields.io/badge/license-MIT-lightgrey" alt="License">
</p>

# gtChat

> Planner-driven multi-agent workflow for content commerce — from trend discovery to viral-ready briefs.

gtChat is a LangGraph-based agent pipeline that automates content strategy workflows: collect trending posts from Xiaohongshu and Douyin, analyze patterns, generate imitation briefs, review quality, and produce structured reports — all traceable and evaluable.

## Features

- **Multi-route workflow** — 6 execution paths: trend report, imitation planning, full pipeline, reference video analysis, commercial data import, and hotspot auto-analysis
- **Multi-source data** — Xiaohongshu (Playwright browser), Douyin search/hot-board (HTTP API), Chanmama export import, local video analysis
- **Planner-driven routing** — natural language input → keyword extraction → route selection → full agent pipeline
- **LLM-backed agents** with rule-based fallback — works without API keys, upgrades with `LLM_ENABLE=true`
- **Unified trace pipeline** — every node records timing, LLM events, warnings, and errors to `agent_trace.json`
- **Skill registry** — extensible local skill system with function and file-import adapters
- **Monitor + notifications** — scheduled hotspot detection, judge/research sub-agents, webhook push
- **Eval framework** — trace exporter, eval datasets, and automated eval runner
- **Windows-friendly** — tested on Windows 11, Chromium auto-detection, PowerShell env support

## Installation

```bash
git clone https://github.com/your-org/gtChat.git
cd gtChat

pip install -e .
pip install langgraph pydantic

# Optional: LLM support
pip install langchain langchain-openai

# Optional: Playwright for XHS collection
pip install playwright
playwright install chromium
```

## Quick Start

```bash
# Run tests (no network, no API keys required)
python -m pytest tests -q

# Trend analysis from cached data
python -m app.cli "宠物用品趋势分析"

# Imitation planning
python -m app.cli "策划猫粮仿拍选题"

# Full pipeline (collect → analyze → plan → report)
python -m app.cli "从采集到报告全做一遍"

# Analyze a reference video
python -m app.cli "基于参考视频 path=C:\video.mp4 生成仿拍"
```

Output lands in `outputs/<run_id>/`:
- `trend_report.md` — full analysis report
- `manifest.json` — run metadata and source provenance
- `agent_trace.json` — per-node timing, LLM events, performance summary

## Routes

gtChat uses a keyword-based planner to select one of six routes:

| Route | Trigger | Description |
| --- | --- | --- |
| `trend_report_path` | 趋势, 分析, 报告 | Load cached data → trend & pattern analysis → report |
| `imitation_plan_path` | 仿拍, 选题, 策划 | Load → clean → trend → pattern → imitation plans → review → report |
| `full_pipeline_path` | 从采集到, 全流程 | Live collect → clean → analyze → plan → review → report |
| `reference_video_imitation_path` | 参考视频, video brief | Local video analysis → pattern extraction → imitation → report |
| `commercial_data_analysis_path` | commercial, chanmama, 蝉妈妈 | Import commercial exports → normalize → analyze → report |
| `hotspot_auto_analysis_path` | hotspot, 热点自动 | Load hotspot signals → content analysis → imitation → report |

Route definitions: [`pipeline_defs/`](pipeline_defs/)

## Data Sources

| Platform | Capability | Method |
| --- | --- | --- |
| Xiaohongshu | Search, detail, filter by sort/time | Playwright browser + persistent profile |
| Douyin | Search, detail, hot board, keyword import | HTTP API with cookie auth |
| Chanmama | Creator/ product export import | CSV/JSON folder scan |
| Local video | Scene detection, transcription, keyframes | `app/video/` analysis pipeline |

### Xiaohongshu Login

```bash
# Opens browser → scan QR → press Enter → profile saved
python -m app.collectors.xiaohongshu_minimal --login

# Search
python -m app.collectors.xiaohongshu_minimal --keyword "猫粮" --limit 20
```

### Douyin Setup

```bash
# Check auth status
python -m app.collectors.douyin_minimal --check-login

# Requires endpoints:
#   DOUYIN_SEARCH_ENDPOINT, DOUYIN_DETAIL_ENDPOINT, DOUYIN_HOT_BOARD_ENDPOINT
python -m app.collectors.douyin_minimal --hot-board --limit 20
```

## LLM Configuration

```bash
# Enable LLM agents (optional — rule-based fallback works without it)
export LLM_ENABLE=true
export LLM_BASE_URL=https://api.openai.com/v1
export LLM_API_KEY=your_key
export LLM_MODEL=gpt-4.1-mini
```

Or use the PackyAPI preset:
```bash
export LLM_ENABLE=true
export LLM_PRESET=packyapi
export PACKY_API_KEY=your_key
export LLM_MODEL=gpt-4.1-mini
```

## Live Checks

```bash
# Dry-run: validate config without network calls
python -m app.live_checks

# Live: test douyin endpoints + notification webhook
python -m app.live_checks --allow-live --keyword "猫粮"
```

## Monitor

```bash
# Single detection → judge → research tick
python -m app.monitor run --once

# Watch mode (every N seconds)
python -m app.monitor run --interval 600
```

## Evals

```bash
# Export workflow traces to eval dataset
python -m evals.exporters.local_trace_exporter --input outputs/

# Run eval report
python -m evals.runners.run_deepeval_from_trace --dataset evals/datasets/workflow_eval_cases.jsonl
```

## Architecture

```
User Query
    │
    ▼
PlanAgent ──► Router ──► Node Pipeline ──► Report + Trace
    │              │
    │    ┌─────────┼─────────┐
    │    │         │         │
    ▼    ▼         ▼         ▼
 Collect → Clean → Trend → Pattern → Imitation → Review → Report
(XHS/DY)   │                            │            │
           │                            │            │
     Data Quality              Evidence Pack    Agent Trace
                                            (timing, LLM, perf)
```

Every node runs through `run_node()` — a unified hook pipeline:
- `before`: validate required state keys
- `run`: execute node logic
- `after`: warn on missing outputs
- `on_error`: record structured error

## Project Structure

```text
app/
  agents/          Plan, trend, pattern, imitation, review, report, judge, research
  cleaner/         Dedup, normalize, data quality stats
  collectors/      XHS (Playwright), Douyin (HTTP API)
  data_sources/    Chanmama CSV/JSON import hub
  llm/             Structured LLM calls with schema validation + rule fallback
  memory/          SimpleMemory (file), SQLiteMemory (keyword-indexed)
  monitor/         Auth gate, signal detection, research loop
  notifications/   Digest generation, webhook push
  queue/           SQLite job queue (enqueue / claim / done / failed)
  skills/          Registry + LocalFunction / FileImport adapters
  video/           Scene detection, frame sampling, transcription, local analysis
  workflow/        LangGraph graph, router, trace, evidence, performance, contracts

config/            Skill definitions
pipeline_defs/     Route manifests (*.yaml)
evals/             Trace exporter, eval runner, datasets
tests/             Workflow, collector, skill, memory, eval tests
outputs/           Reports, traces, manifests, video briefs
```

## License

MIT
