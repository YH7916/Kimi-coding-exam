# On-Call Assistant

这是题目一的实现：一个基于部门 On-Call SOP 文档的 Web 助手，包含关键词搜索、语义检索和带工具调用过程展示的 Agent 对话。

## 已实现功能

| 阶段 | 路由 | 实现 |
| ---- | ---- | ---- |
| Phase 1 | `/v1`、`/v1/search`、`/v1/documents` | 解析 HTML 可见文本，使用 BM25/关键词检索，忽略 `script` 等不可见内容 |
| Phase 2 | `/v2`、`/v2/search` | SOP section chunking + embedding vector store + BM25/RRF hybrid retrieval；无密钥时自动使用离线 semantic fallback |
| Phase 3 | `/v3`、`/v3/chat`、`/v3/chat/stream` | OpenAI-compatible Chat Completions tool-calling Agent，只通过 `readFile(fname)` 读取 SOP，并在前端展示流式工具调用、证据和引用 |
| Phase 4 | `/v3/memory`、`/v3/memory/search` | L0-L3 layered memory，支持流式/非流式写入、L1 原子事实、L2 事故场景、L3 偏好画像、冲突覆盖、过期隐藏、删除和离线 memory eval |

前端是纯静态页面，由 FastAPI 托管，三个阶段共享同一个产品化界面，可以在顶部切换 `v1 Search`、`v2 RAG` 和 `v3 Agent`。

## 目录结构

```text
question-1/
├── app.py                    # FastAPI 启动入口
├── data/                     # 10 份 demo SOP HTML
├── frontend/                 # 静态前端页面和 ES module 组件
├── oncall_app/
│   ├── api/                  # 路由、schema、静态文件托管
│   ├── agent/                # tool-calling loop、readFile 工具、证据抽取
│   ├── documents/            # HTML 解析、SOP repository、section 抽取
│   ├── evaluation/           # README 验收用 evaluation cases 和 metrics
│   ├── llm/                  # OpenAI-compatible embedding/chat clients
│   ├── memory/               # L0 raw events、L1/L2/L3 memories、SQLite store、recall
│   └── retrieval/            # BM25、chunking、vector store、hybrid retrieval
├── scripts/evaluate.py       # 离线验收脚本
├── tests/                    # 单元测试、API 测试、检索测试、集成 smoke test
├── requirements.txt
├── requirements-dev.txt
├── package.json
└── pyproject.toml
```

仓库根目录还包含：

- `prompt/`：AI 交互过程导出的 Markdown，已脱敏。
- `screenshot/`：最终效果截图。
- `李宇晗简历.pdf`：个人简历。

## 快速启动

```powershell
cd question-1
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt -r requirements-dev.txt
npm install
python app.py
```

打开页面：

- `http://127.0.0.1:8000/v1`
- `http://127.0.0.1:8000/v2`
- `http://127.0.0.1:8000/v3`

## 离线验收

默认测试不访问外部网络，未配置真实模型密钥时会自动使用 deterministic fallback。

```powershell
cd question-1
python scripts/evaluate.py
python -m unittest
npm run lint:frontend
```

本地最近一次验证结果：

- `python scripts/evaluate.py`：24 cases；v1 hit@5 = 1.00，v2 hit@3 = 1.00，v3 tool files = 1.00，v3 evidence = 1.00，v3 keywords = 1.00，memory recall@1 = 1.00，memory rejection = 1.00，memory conflict = 1.00。
- `python -m unittest`：104 个测试通过，2 个真实 provider 测试默认跳过。
- `npm run lint:frontend`：通过。

## API 说明

### Phase 1

```text
POST /v1/documents
{ "id": "sop-001", "html": "<html>...</html>" }
→ 201 { "id": "sop-001", "title": "后端服务 On-Call SOP" }

GET /v1/search?q=OOM
→ 200 { "query": "OOM", "results": [...] }
```

典型验收：

- `GET /v1/search?q=OOM` 返回 `sop-001`
- `GET /v1/search?q=故障` 返回多个 SOP
- `GET /v1/search?q=replication` 返回空，因为该词只在 script 中
- `GET /v1/search?q=CDN` 返回 `sop-003` 和 `sop-010`

### Phase 2

```text
GET /v2/search?q=服务器挂了
→ 200 { "query": "服务器挂了", "results": [...] }
```

典型验收：

- `服务器挂了`：后端服务和 SRE SOP 靠前
- `黑客攻击`：安全团队 SOP 靠前
- `机器学习模型出问题`：AI & 算法 SOP 靠前

### Phase 3

```text
GET /v3
POST /v3/chat
```

Agent 约束：

- 只有一个工具：`readFile(fname: string) -> string`
- 工具只能读取 `data/` 下的直接文件名
- 禁止目录遍历、子目录、通配符和列目录
- 前端展示工具调用过程、SOP 证据和引用章节

典型验收：

- `数据库主从延迟超过30秒怎么处理？` 读取 `sop-002.html`
- `服务 OOM 了怎么办？` 读取 `sop-001.html`
- `P0 故障的响应流程是什么？` 综合多个 SOP
- `怀疑有人入侵了系统` 读取 `sop-005.html`
- `推荐结果质量下降了` 读取 `sop-008.html`

### Phase 4

```text
POST /v3/chat 或 /v3/chat/stream
{ "message": "记住：支付服务负责人是小王，升级群是 #pay-oncall。" }
→ 200 / SSE done；完成后写入 L0 raw event 并抽取 L1 atomic memory

POST /v3/chat 或 /v3/chat/stream
{ "message": "支付服务报警应该找谁？" }
→ 200 / SSE memory event；返回 memory_hits，例如 { "summary": "支付服务负责人是小王..." }

GET /v3/memory
GET /v3/memory/search?q=支付服务
DELETE /v3/memory/{memory_id}
```

记忆边界：

- L0 raw events：每轮完成的用户消息、答案、tool calls、evidence 和 trace，用于 provenance。
- L1 atomic memories：显式“记住”类事实、服务负责人、升级群等结构化服务上下文；同一 dedupe key 的新事实会覆盖旧事实并保留来源链。
- L2 scene memories：从包含 tool/evidence 的完成交互中抽取事故场景摘要，用于追溯“上次类似事故怎么处理”。
- L3 profile：从稳定回答偏好中抽取长期画像，召回时优先作为非 SOP 上下文注入。
- `expires_at`、soft delete 和 active filter 支持过期隐藏与手动删除。
- Memory context 不是 SOP 证据；事故处理动作仍以 RAG 候选和 `readFile` 读取到的 SOP 为准。

评测方法参考 Anthropic 的 Agent eval 思路：优先使用可重复的确定性 grader，同时检查 outcome、tool trace 和 evidence，而不是只看最终自然语言答案。

## 真实模型配置

项目使用 OpenAI-compatible 协议。不要把真实 API Key 写入仓库。

```powershell
$env:ONCALL_EMBEDDING_BASE_URL="https://api.siliconflow.cn/v1"
$env:ONCALL_EMBEDDING_API_KEY="..."
$env:ONCALL_EMBEDDING_MODEL="Qwen/Qwen3-Embedding-0.6B"

$env:ONCALL_CHAT_BASE_URL="http://127.0.0.1:8080/v1"
$env:ONCALL_CHAT_API_KEY="..."
$env:ONCALL_CHAT_MODEL="gpt-5.4"
```

也可以使用兼容变量：

```powershell
$env:OPENAI_BASE_URL="http://127.0.0.1:8080/v1"
$env:OPENAI_API_KEY="..."
$env:OPENAI_MODEL="gpt-5.4"
```

真实 provider smoke test 是 opt-in：

```powershell
$env:ONCALL_RUN_INTEGRATION="1"
python -m unittest tests.integration.test_real_providers -v
```

## 安全与提交说明

- `.env`、`.cache/`、`.venv/`、`node_modules/`、`docs/`、`output/`、`AGENTS.md` 均不进入最终提交包。
- `prompt/` 中曾出现的密钥形态字符串已替换为 `***REDACTED***`。
- `question-1/.env.example` 是示例配置，可以保留。
