# On-Call Copilot 零基础自举学习手册

这份文档的目标不是让你背术语，而是让你能做到三件事：

1. 能从零讲清楚这个系统是干什么的。
2. 能沿着源码解释一次完整请求的执行路径。
3. 能自己改一个小功能、写测试、跑质量门，并知道为什么这样改。

如果你能完成文末的自举练习，就可以比较稳地面对面试官追问。

## 0. 先建立全局图

这个项目是一个 On-Call SOP Copilot。用户问线上故障怎么处理，系统从 `data/` 里的 SOP HTML 文档中检索相关内容，然后给出答案。

题目分三层：

- v1: 关键词搜索。用户输入 `OOM`，系统返回包含 OOM 的 SOP。
- v2: 语义搜索。用户输入 `服务器挂了`，即使原文不完全这么写，也能找到后端和 SRE SOP。
- v3: On-Call Agent。用户输入问题，Agent 只能通过 `readFile(fname)` 读取 SOP 文件，然后基于 SOP 回答。

一句话总述：

```text
Phase 1 是 BM25 lexical retrieval，Phase 2 是 SiliconFlow embedding + BM25/RRF hybrid retrieval，Phase 3 是 OpenAI-compatible Chat Completions tool-calling Agent。
```

你先记住这张数据流：

```text
SOP HTML
  -> HTML parser 过滤 script/style，提取 visible text 和 sections
  -> v1 BM25 keyword index
  -> v2 chunk embedding + vector store + RRF hybrid search
  -> v3 Agent 读取 sop-index.json，再调用 readFile(fname)
  -> evidence extraction
  -> Chat Completions 生成答案
  -> frontend 展示 tool calls、evidence、answer
```

## 1. 你需要掌握的最小基础知识

### 1.1 HTTP 和 API

HTTP 可以先理解成浏览器或前端和后端说话的协议。

本项目主要接口：

```text
GET  /health
GET  /v1
GET  /v1/search?q=OOM
POST /v1/documents
GET  /v2
GET  /v2/search?q=服务器挂了
GET  /v3
POST /v3/chat
```

`GET` 通常用于获取数据，`POST` 通常用于提交数据。

例子：

```text
GET /v1/search?q=OOM
```

意思是：向后端请求 v1 搜索，查询词是 `OOM`。

返回 JSON：

```json
{
  "query": "OOM",
  "results": [
    {
      "id": "sop-001",
      "title": "后端服务 On-Call SOP",
      "snippet": "...OutOfMemoryError...",
      "score": 1.23
    }
  ]
}
```

面试时你要能说：

```text
前端只是调用 HTTP API；真正的检索、Agent、LLM 调用都在后端模块里。
```

### 1.2 FastAPI 和路由

FastAPI 是 Python Web 框架。它负责把 HTTP 请求映射到 Python 函数。

关键文件：

```text
app.py
oncall_app/api/app_factory.py
oncall_app/api/router.py
oncall_app/api/schemas.py
```

你要看懂这条链：

```text
app.py
  -> create_app()
  -> include_router(router)
  -> /v1/search 调用 v1_search()
  -> v1_search() 调用 runtime.service.keyword_search()
```

这个项目刻意让 route 很薄。

薄 route 的意思是：

```text
route 只负责 HTTP 参数和响应格式，不把 BM25、Embedding、Agent 逻辑写在 route 里。
```

这样面试官看源码时，会觉得模块边界清楚。

### 1.3 前后端分离

前端文件：

```text
frontend/index.html
frontend/app.js
frontend/styles.css
```

后端文件：

```text
oncall_app/api/
oncall_app/documents/
oncall_app/retrieval/
oncall_app/agent/
oncall_app/llm/
```

前端做三件事：

1. 渲染输入框和结果区域。
2. 调用 `/v1/search`、`/v2/search`、`/v3/chat`。
3. 展示搜索结果、工具调用、证据和最终答案。

前端不做检索，不做 Agent，不拿 API key。

## 2. 文档解析层：为什么不能直接搜 HTML 全文

题目里有一个坑：

```text
GET /v1/search?q=replication
```

期望返回空，因为 `replication` 只出现在 `<script>` 标签里。

如果你用普通字符串搜索整个 HTML，就会误命中。

所以系统要做 HTML 解析：

```text
HTML 原文
  -> BeautifulSoup
  -> 移除 script/style
  -> 提取 title
  -> 提取 body visible text
  -> 解码 HTML entity
  -> 抽取 h1/h2/h3 sections
```

关键文件：

```text
oncall_app/documents/parser.py
oncall_app/documents/sections.py
oncall_app/documents/repository.py
oncall_app/documents/manifest.py
```

你要能讲：

```text
搜索系统不能直接索引 HTML 字符串，而要索引用户可见文本。这样才能避免 script/style 噪声，也能正确处理 &amp; 这种 HTML entity。
```

`q=&` 也是坑。

URL 里：

```text
/v1/search?q=&
```

服务端拿到的 `q` 可能是空字符串。项目里专门把这个 README 行为归一化为字面量 `&`。

关键代码在：

```text
oncall_app/api/router.py
_normalize_query()
```

## 3. v1：BM25 关键词搜索

### 3.1 关键词搜索是什么

关键词搜索，也叫 lexical retrieval。它主要看词面是否出现。

例子：

```text
query: OOM
document: Java 服务出现 OutOfMemoryError 后...
```

这个应该命中。

### 3.2 为什么不是简单 `if query in text`

简单包含搜索只能告诉你有没有出现，不能很好排序。

BM25 会考虑：

- 查询词在文档中出现多少次。
- 文档整体长度。
- 一个词是不是太常见。

不需要背公式。你只要会讲：

```text
BM25 是经典关键词排序算法，比 substring search 更适合搜索场景，因为它能给相关文档打分并排序。
```

关键文件：

```text
oncall_app/retrieval/tokenize.py
oncall_app/retrieval/bm25.py
oncall_app/retrieval/service.py
```

执行路径：

```text
GET /v1/search?q=OOM
  -> router.v1_search()
  -> RetrievalService.keyword_search("OOM")
  -> tokenize(query)
  -> BM25Index.rank(query_tokens)
  -> SearchResult(id, title, snippet, score)
```

### 3.3 中文为什么要分词

英文可以按空格切：

```text
service oom incident
```

中文没有天然空格：

```text
数据库主从延迟超过30秒
```

所以项目用了 jieba，同时保留技术 token，比如：

```text
OOM
K8s
CDN
&
```

面试可以说：

```text
中文 SOP 搜索不能只按空格切词，所以我用 jieba 做中文分词，并额外保留英文技术词和符号 token。
```

## 4. v2：Embedding、向量搜索和 Hybrid RAG

### 4.1 Embedding 是什么

Embedding 就是把文本变成一串数字，也就是向量。

你可以这样理解：

```text
"服务器挂了" -> [0.12, -0.08, 0.44, ...]
"服务不可用" -> [0.10, -0.06, 0.41, ...]
"前端白屏"   -> [-0.30, 0.50, 0.02, ...]
```

语义相近的文本，向量距离更近。

所以 v2 能处理：

```text
用户说: 服务器挂了
SOP 写: 后端服务超时、K8s 故障、监控告警
```

虽然字面不完全一致，但语义相关。

### 4.2 为什么要 chunk

如果把整篇 SOP 直接变成一个向量，粒度太粗。

一篇 SOP 可能同时包含：

- OOM
- 服务超时
- 降级策略
- 故障分级

所以项目按 section/chunk 切分，再做 embedding。

关键文件：

```text
oncall_app/retrieval/chunking.py
oncall_app/retrieval/vector_store.py
oncall_app/retrieval/embeddings.py
```

你要能讲：

```text
chunking 的目的是提高召回精度，让一个查询命中具体段落，而不是整篇大文档的平均语义。
```

### 4.3 SiliconFlow 如何接入

真实 embedding provider：

```text
SiliconFlow
model: Qwen/Qwen3-Embedding-0.6B
```

环境变量：

```powershell
$env:ONCALL_EMBEDDING_BASE_URL="https://api.siliconflow.cn/v1"
$env:ONCALL_EMBEDDING_API_KEY="..."
$env:ONCALL_EMBEDDING_MODEL="Qwen/Qwen3-Embedding-0.6B"
```

关键文件：

```text
oncall_app/llm/config.py
oncall_app/llm/openai_compat.py
oncall_app/llm/embedding_client.py
oncall_app/api/router.py
```

生产路径：

```text
SearchRuntime
  -> embedding_config_from_env()
  -> create_embedding_client(config)
  -> EmbeddingCache(".cache/embeddings.sqlite3")
  -> RetrievalService.from_documents(..., embedding_client, embedding_cache)
  -> VectorStore.from_chunks(...)
```

如果没有 key：

```text
自动退回 semantic_fallback_search
```

这保证没网也能 demo 和跑测试。

### 4.4 为什么要缓存 embedding

Embedding API 有成本和延迟。

SOP 文档不经常变，所以同一段文本不应该每次启动都重新请求 API。

项目用 SQLite 缓存：

```text
.cache/embeddings.sqlite3
```

缓存 key 包含：

```text
model + text hash
```

这样换模型后不会误用旧向量。

### 4.5 为什么要 Hybrid Search

只用 BM25 的问题：

```text
语义弱。用户说“服务器挂了”，文档可能写“服务不可用”。
```

只用向量的风险：

```text
精确词可能丢，比如 CDN、OOM、K8s 这种技术词。
```

所以项目用了 hybrid retrieval：

```text
BM25 results + Vector results -> RRF fusion -> final ranking
```

RRF 是 Reciprocal Rank Fusion。

你不需要背数学，只要会讲：

```text
RRF 根据多个排序列表中的名次融合结果。如果一个文档同时被 BM25 和向量检索排得靠前，它会被提升。
```

关键文件：

```text
oncall_app/retrieval/hybrid.py
oncall_app/retrieval/service.py
```

v2 完整路径：

```text
GET /v2/search?q=黑客攻击
  -> router.v2_search()
  -> RetrievalService.semantic_search()
  -> keyword_search()
  -> vector_search()
  -> rrf_fuse()
  -> SearchResult[]
```

## 5. v3：Tool-Calling Agent

### 5.1 Agent 是什么

在这个项目里，Agent 不是一个玄学概念。

它就是：

```text
LLM + 工具 + 循环控制 + 观察结果 + 最终回答
```

用户问：

```text
服务 OOM 了怎么办？
```

Agent 不应该凭空回答。它要先读 SOP。

### 5.2 为什么只有 readFile 一个工具

题目明确限制：

```text
Agent 只有一个工具: readFile(fname)
Agent 不能列目录
Agent 不能 glob
```

所以它不能：

```text
ls data/
glob("*.html")
```

它只能：

```text
readFile("sop-001.html")
```

### 5.3 Agent 怎么知道文件名

项目启动时会生成：

```text
data/sop-index.json
```

这个文件包含每个 SOP 的：

- file name
- doc id
- title
- topics

Agent 先读 `sop-index.json`，再决定读哪个 SOP。

执行路径：

```text
POST /v3/chat
  -> OnCallAssistant.chat(message)
  -> repository.write_manifest("sop-index.json")
  -> readFile("sop-index.json")
  -> Chat Completions decides tool calls
  -> readFile("sop-001.html")
  -> evidence extraction
  -> final answer
```

关键文件：

```text
oncall_app/agent/assistant.py
oncall_app/agent/prompts.py
oncall_app/agent/tools.py
oncall_app/agent/evidence.py
oncall_app/agent/synthesizer.py
```

### 5.4 Chat Completions tool calling

Chat Completions 是 OpenAI 兼容 API。

普通聊天只传：

```json
{
  "model": "gpt-5.4",
  "messages": [...]
}
```

工具调用会额外传：

```json
{
  "tools": [
    {
      "type": "function",
      "function": {
        "name": "readFile",
        "parameters": {
          "type": "object",
          "properties": {
            "fname": { "type": "string" }
          }
        }
      }
    }
  ]
}
```

模型返回：

```json
{
  "tool_calls": [
    {
      "function": {
        "name": "readFile",
        "arguments": "{\"fname\":\"sop-001.html\"}"
      }
    }
  ]
}
```

后端执行工具，再把结果作为 observation 放回 messages。

### 5.5 readFile 沙箱

`readFile` 必须安全。

允许：

```text
sop-001.html
sop-index.json
```

拒绝：

```text
../README.md
data/sop-001.html
*.html
sop-[001].html
```

关键文件：

```text
oncall_app/documents/repository.py
oncall_app/agent/tools.py
```

面试可以说：

```text
Agent 工具必须有沙箱，否则 prompt injection 可能诱导模型读取越权文件。
```

### 5.6 Trace 和 Chain-of-Thought 的区别

这个项目前端展示：

- 收到问题
- 调用了哪些工具
- 读取了哪些文件
- 抽取了哪些 evidence
- 最终答案

它不展示模型隐藏推理。

你可以讲：

```text
我展示的是可审计行为 trace，而不是 chain-of-thought。产品上这样更稳定，也更安全。
```

## 6. 真实 API 配置

### 6.1 v2 Embedding

```powershell
$env:ONCALL_EMBEDDING_BASE_URL="https://api.siliconflow.cn/v1"
$env:ONCALL_EMBEDDING_API_KEY="..."
$env:ONCALL_EMBEDDING_MODEL="Qwen/Qwen3-Embedding-0.6B"
```

### 6.2 v3 Chat

如果本地 OpenAI 反代是：

```toml
base_url = "http://127.0.0.1:8080"
wire_api = "responses"
```

项目里当前使用 Chat Completions tool-calling，所以 app 配置要用：

```powershell
$env:ONCALL_CHAT_BASE_URL="http://127.0.0.1:8080/v1"
$env:ONCALL_CHAT_API_KEY="..."
$env:ONCALL_CHAT_MODEL="gpt-5.4"
```

注意：

```text
不要把 API key 写进代码或提交到 Git。
```

## 7. 测试、Lint 和评测

这个项目不是只靠手动点页面。

常用命令：

```powershell
python -m unittest discover -v
python -m pylint app.py oncall_app tests
python -m ruff check .
python -m mypy oncall_app
python scripts/evaluate.py
```

各自作用：

- `unittest`: 验证行为。
- `pylint`: 检查代码质量和风格。
- `ruff`: 快速 lint，检查 import、常见 bug。
- `mypy`: 类型检查。
- `scripts/evaluate.py`: 把 README 验收转成指标。

评测指标：

- `hit@k`: 前 k 个结果里有没有目标文档。
- `MRR`: 正确文档排得越靠前分越高。
- `tool-file accuracy`: v3 是否读取了期望 SOP 文件。
- `keyword coverage`: v3 答案是否包含关键处理点。

## 8. 从一个请求走读源码

### 8.1 v1 OOM 请求

请求：

```text
GET /v1/search?q=OOM
```

源码路径：

```text
oncall_app/api/router.py
  -> v1_search()
  -> _normalize_query()
  -> runtime.service.keyword_search()

oncall_app/retrieval/service.py
  -> tokenize(query)
  -> BM25Index.rank()
  -> _make_snippet()
  -> SearchResult

oncall_app/api/schemas.py
  -> search_response()
```

你要能回答：

```text
为什么 sop-001 排第一？
因为 sop-001 的可见文本中包含 OOM/OutOfMemoryError，BM25 对相关 token 打分更高。
```

### 8.2 v2 黑客攻击请求

请求：

```text
GET /v2/search?q=黑客攻击
```

源码路径：

```text
router.v2_search()
  -> RetrievalService.semantic_search()
  -> keyword_search()
  -> _vector_search()
  -> rrf_fuse()
```

你要能回答：

```text
为什么 sop-005 靠前？
因为安全 SOP 的 section chunk 在 embedding 空间里和“黑客攻击”更接近，同时 BM25 也能命中安全、攻击、入侵等词，RRF 融合后排到前面。
```

### 8.3 v3 OOM 请求

请求：

```text
POST /v3/chat
{ "message": "服务 OOM 了怎么办？" }
```

源码路径：

```text
router.v3_chat()
  -> runtime.assistant.chat()
  -> write_manifest("sop-index.json")
  -> readFile("sop-index.json")
  -> Chat Completions tool call
  -> readFile("sop-001.html")
  -> EvidenceExtractor.extract()
  -> chat_response()
```

你要能回答：

```text
Agent 为什么先读 sop-index.json？
因为题目禁止 ls/glob，Agent 不能列目录，只能通过一个已知索引文件了解可读 SOP 文件。
```

## 9. 面试讲法模板

### 9.1 30 秒版本

```text
这是一个 On-Call SOP Copilot。v1 用 BM25 做 HTML 可见文本关键词搜索，解决 OOM、CDN 这类精确检索；v2 接入 SiliconFlow 的 Qwen embedding，把 SOP 按 section chunk 建向量索引，再和 BM25 用 RRF 做 hybrid retrieval；v3 使用 OpenAI-compatible Chat Completions tool calling，Agent 只能通过 readFile(fname) 读取 SOP，并把工具调用、证据和答案展示给前端。整体上前后端分离，路由和实现分离，真实 API 通过 env 接入，测试里用 fake/local client 保证可复现。
```

### 9.2 被问“你用了 AI 写代码，怎么证明你懂”

```text
AI 主要帮我生成样板和重复性代码，但关键设计是我自己控制的：比如 HTML 只索引 visible text，v2 用 BM25 + vector 的 hybrid retrieval，v3 不用 LangChain 而是手写 tool-calling loop，readFile 做 direct filename 沙箱，最后把 README 验收转成 evaluation harness。我的判断标准不是代码能不能生成，而是能不能解释每个边界为什么存在。
```

### 9.3 被问“为什么不用 LangChain”

```text
这道题面试官会看 Agent 如何选文件、如何调用工具、如何处理 observation。LangChain 会隐藏很多细节，不利于讲清楚。我这里手写了一个很小的 tool-calling loop，逻辑更透明，也更贴合题目的 readFile 约束。
```

### 9.4 被问“v2 为什么不是纯向量”

```text
纯向量召回语义强，但对 OOM、CDN、K8s 这种技术 token 不一定稳定；BM25 对精确词强，但对“服务器挂了”这种表达弱。所以我做 hybrid retrieval，用 RRF 融合两路排序。
```

### 9.5 被问“这个系统怎么 scale 到 100 份 SOP”

```text
文档层按文件加载，检索层按 chunk 建索引，embedding 有 SQLite cache。100 份文档在这个架构下只是更多 chunk，不需要改业务逻辑。更大规模时可以把本地 vector store 换成 Qdrant、Milvus 或 pgvector。
```

## 10. 自举练习路线

下面这些练习按顺序做。每做完一个，你就会更像项目真正的 owner。

### Level 1: 跑起来

目标：知道系统怎么启动、怎么验证。

命令：

```powershell
python -m unittest discover -v
python scripts/evaluate.py
python -m uvicorn app:app --host 127.0.0.1 --port 8001
```

浏览器打开：

```text
http://127.0.0.1:8001/v1
http://127.0.0.1:8001/v2
http://127.0.0.1:8001/v3
```

你要能解释：

```text
为什么 /v1、/v2、/v3 都返回同一个 frontend shell？
```

答案：

```text
因为前端是单页静态页面，根据 pathname 决定渲染搜索或聊天 UI。
```

### Level 2: 读懂 v1

目标：从 `GET /v1/search?q=OOM` 走到 BM25。

阅读顺序：

```text
oncall_app/api/router.py
oncall_app/retrieval/service.py
oncall_app/retrieval/tokenize.py
oncall_app/retrieval/bm25.py
tests/retrieval/test_bm25_search.py
```

练习：

```text
增加一个测试：搜索 "DDoS" 应该命中 sop-010。
```

完成后跑：

```powershell
python -m unittest tests.retrieval.test_bm25_search -v
```

### Level 3: 读懂 v2

目标：知道 embedding、chunk、vector store、RRF 怎么串起来。

阅读顺序：

```text
oncall_app/retrieval/chunking.py
oncall_app/retrieval/vector_store.py
oncall_app/retrieval/embeddings.py
oncall_app/retrieval/hybrid.py
oncall_app/retrieval/service.py
tests/retrieval/test_vector_retrieval.py
tests/retrieval/test_hybrid_retrieval.py
```

练习：

```text
解释为什么 "服务器挂了" 的 top two 是 sop-001 和 sop-004。
```

再做一个代码练习：

```text
给 RetrievalService.semantic_search 增加一个参数 limit=5 的测试，确认结果数量不超过 5。
```

### Level 4: 读懂 v3

目标：能完整讲清 Agent tool-calling loop。

阅读顺序：

```text
oncall_app/agent/prompts.py
oncall_app/agent/assistant.py
oncall_app/agent/tools.py
oncall_app/agent/evidence.py
oncall_app/api/router.py
tests/agent/test_tool_calling_agent.py
tests/api/test_agent_routes.py
```

练习：

```text
问 "怀疑有人入侵了系统"，确认 tool_calls 包含 sop-005.html。
```

命令：

```powershell
python -m unittest tests.agent.test_tool_calling_agent -v
```

### Level 5: 修改一个真实功能

目标：证明你不是只会读。

功能建议：

```text
给 /v3/chat 返回的 evidence 增加 doc_id 字段。
```

你需要改：

```text
oncall_app/agent/evidence.py
oncall_app/api/schemas.py
tests/agent/test_evidence.py
tests/api/test_agent_routes.py
frontend/app.js
```

流程：

```text
先写测试
跑测试确认失败
改实现
跑测试确认通过
跑 lint
提交 git
```

### Level 6: 讲给自己听

目标：能不看文档讲 5 分钟。

按这个顺序讲：

1. 题目要做什么。
2. v1 怎么做，为什么是 BM25。
3. v2 怎么做，为什么是 embedding + RRF。
4. v3 怎么做，为什么是 tool calling。
5. readFile 为什么要沙箱。
6. 真实 API 怎么接入。
7. 测试和 evaluation 怎么保证可靠。

讲完后用源码验证自己有没有讲错。

## 11. 常见追问和短答案

### 为什么 `replication` 返回空？

因为它只在 `<script>` 中出现，parser 会移除 script/style，只索引 visible text。

### 为什么 `q=&` 可以搜到？

因为 HTML entity 会被解析成真实 `&`，同时 route 对 README 的空 query 行为做了归一化。

### 为什么 v2 要真实 embedding？

因为语义搜索不能只靠关键词扩展。真实 embedding 能处理表达不同但语义相近的问题，例如“服务器挂了”和“服务不可用”。

### 为什么还保留 fallback？

为了测试和 demo 可复现。没有 key、没网、API 限流时，基本 README 验收仍然能跑。

### 为什么 Agent 不直接读所有文档？

题目约束 Agent 不能列目录，而且 100 份文档全塞 prompt 不可扩展。先读索引，再按需 readFile 更符合 Agentic RAG。

### 为什么不展示 chain-of-thought？

因为用户真正需要的是可审计证据：读了哪些文件、引用了哪些 section、答案是什么。隐藏推理不是稳定产品接口。

## 12. 最终自检清单

如果你能回答下面问题，说明你基本完成自举：

- `/v1/search?q=OOM` 从 route 到 BM25 的调用链是什么？
- 为什么不能直接全文搜索 HTML？
- BM25 相比 substring search 好在哪里？
- Embedding 是什么，为什么能处理语义查询？
- chunking 解决了什么问题？
- RRF 在 hybrid retrieval 里做什么？
- `.cache/embeddings.sqlite3` 为什么不能提交？
- Agent 为什么先读 `sop-index.json`？
- `readFile` 怎么防止路径穿越？
- v3 为什么用 Chat Completions tool calling？
- 真实 API key 为什么必须用 env？
- 单元测试为什么不能默认打真实 API？
- `scripts/evaluate.py` 的指标分别代表什么？

## 13. 你现在最该补的知识顺序

按这个顺序学，不要一上来钻数学：

1. HTTP API 和 FastAPI route。
2. HTML parsing 和 visible text。
3. BM25 的直觉。
4. Embedding 和 cosine similarity。
5. chunking 和 vector store。
6. Hybrid search 和 RRF。
7. RAG 和 Agent 的区别。
8. Chat Completions tool calling。
9. 测试、lint、mypy、evaluation。
10. 安全边界和 prompt injection 风险。

每天用 30 分钟：

```text
10 分钟读一段源码
10 分钟跑一个测试
10 分钟用自己的话复述
```

坚持三轮，你就能把这个项目从“AI 帮我写的”转化成“我能讲清楚、能维护、能继续扩展的项目”。
