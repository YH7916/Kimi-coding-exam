# Kimi Coding Exam - Question 1

本仓库提交的是题目一：On-Call 助手。

## 目录说明

- `question-1/`：On-Call 助手源码、前端页面、测试和题目 README。
- `prompt/`：AI 交互过程导出的 prompt Markdown，已对密钥和 token 做脱敏处理。
- `screenshot/`：最终产物效果截图。
- `李宇晗简历.pdf`：个人简历。
- `.git/`：完整 Git 提交历史。

本提交不包含 `question-2/`、`docs/`、`.env`、缓存目录、虚拟环境或依赖安装目录。

## 运行方式

```powershell
cd question-1
python app.py
```

打开：

- `http://127.0.0.1:8000/v1`
- `http://127.0.0.1:8000/v2`
- `http://127.0.0.1:8000/v3`

## 验证方式

```powershell
cd question-1
python scripts/evaluate.py
python -m unittest
npm run lint:frontend
```

默认测试不会访问外部网络；未配置真实 API Key 时会使用离线 fallback。
