# Development Log

## Baseline

最小版本已经满足 README 的三阶段接口：`/v1` 做关键词搜索，`/v2` 做语义搜索，`/v3` 做 On-Call 问答，并提供一个简单前端。但 baseline 的主要问题是实现偏集中，v2/v3 缺少真实 provider 边界，也缺少可解释的 Agent trace 和系统级评测。

## Limitations Found

- HTML 搜索必须只看 visible text，否则 `replication` 会被 `<script>` 误命中。
- `q=&` 不是空查询，而是 README 对 URL 解码和 HTML entity 的检查。
- 纯关键词不能稳定解决 `/v2/search?q=服务器挂了` 这种语义查询。
- Agent 不能列目录，所以 v3 必须先有文件级索引，再通过 `readFile(fname)` 读取候选 SOP。
- 面试展示不能只靠口头说“能跑”，需要 tests、lint、evaluation script 和 architecture docs。

## Production-Grade Upgrade Decisions

- 后端改为 FastAPI app factory + router，route 只做薄封装。
- 前端独立到 `frontend/`，后端只 serve static shell。
- 文档层抽成 `oncall_app/documents/`，统一负责 HTML 解析、section 结构和 manifest。
- v1 使用 BM25，避免朴素 substring search 的排序和召回问题。
- v2 使用 chunk Embedding + vector store + BM25/RRF hybrid retrieval；真实 API 使用 SiliconFlow `Qwen/Qwen3-Embedding-0.6B`。
- v3 使用 OpenAI Chat Completions-compatible tool calling，只有一个 `readFile` 工具。
- 单元测试用 fake/local clients，真实 provider tests 通过 `ONCALL_RUN_INTEGRATION=1` opt-in。
- 增加 `scripts/evaluate.py`，把 README 验收 case 转成 hit@k、MRR、tool-file accuracy、keyword coverage。

## Rejected Alternatives

- 没有直接用 LangChain：题目重点是让面试官看懂 Agent 如何选文件、调工具、处理 observation；黑盒框架会削弱解释力。
- 没有把所有 SOP 一次塞进 prompt：这不符合“只能 readFile、不能 ls”的约束，也无法 scale 到题目暗示的 100 份文档。
- 没有把 chain-of-thought 展示给用户：产品上展示 tool trace 和 evidence 更稳定，也更安全。
- 没有让普通测试调用真实 API：真实调用会受网络、额度和密钥影响，默认测试必须可复现。

## Current Interview Story

一句话讲法：Phase 1 是可解释 lexical retrieval，Phase 2 是 hybrid RAG retrieval，Phase 3 是基于同一套检索和 SOP 文件约束的 tool-calling Agent。这个项目的重点不是堆框架，而是把 README 的隐藏约束做成工程边界、测试和评测指标。
