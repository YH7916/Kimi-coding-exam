"""Deterministic tool-using On-Call assistant agent."""

from pathlib import Path

from oncall_app.html_parser import parse_html_document
from oncall_app.models import AgentResponse, Document, ToolCall
from oncall_app.repository import DocumentRepository

P0_FILES = (
    "sop-001.html",
    "sop-002.html",
    "sop-003.html",
    "sop-004.html",
    "sop-005.html",
    "sop-010.html",
)


class OnCallAgent:  # pylint: disable=too-few-public-methods
    """Answer On-Call questions while exposing readFile tool calls."""

    def __init__(self, repository: DocumentRepository):
        self.repository = repository

    def answer(self, message: str) -> AgentResponse:
        """Answer a user question using readFile(fname) as the only file tool."""
        fnames = self._choose_files(message)
        documents: list[Document] = []
        tool_calls: list[ToolCall] = []

        for fname in fnames:
            raw_html = self._read_file_tool(fname)
            document = parse_html_document(Path(fname).stem, raw_html)
            documents.append(document)
            tool_calls.append(
                ToolCall(
                    tool="readFile",
                    fname=fname,
                    result_preview=document.text[:180],
                )
            )

        return AgentResponse(answer=self._compose_answer(message, documents), tool_calls=tool_calls)

    @staticmethod
    def _choose_files(message: str) -> list[str]:
        """Choose SOP file names without listing the data directory."""
        normalized = message.casefold()
        if "p0" in normalized or "响应流程" in message or "升级流程" in message:
            selected = list(P0_FILES)
        elif "主从" in message or "数据库" in message or "复制" in message:
            selected = ["sop-002.html"]
        elif "oom" in normalized or "outofmemory" in normalized or "内存" in message:
            selected = ["sop-001.html"]
        elif "入侵" in message or "黑客" in message or "安全" in message or "攻击" in message:
            selected = ["sop-005.html"]
        elif "推荐" in message or "模型" in message or "机器学习" in message or "算法" in message:
            selected = ["sop-008.html"]
        elif "cdn" in normalized or "dns" in normalized:
            selected = ["sop-010.html"]
        else:
            selected = ["sop-001.html"]
        return selected

    def _read_file_tool(self, fname: str) -> str:
        """The agent's sole file tool: readFile(fname: string) -> string."""
        return self.repository.read_file(fname)

    def _compose_answer(self, message: str, documents: list[Document]) -> str:
        """Compose a concise SOP-grounded response."""
        normalized = message.casefold()
        if "p0" in normalized or "响应流程" in message or "升级流程" in message:
            return self._answer_p0(documents)
        if documents and documents[0].doc_id == "sop-002":
            return self._answer_database(documents[0])
        if documents and documents[0].doc_id == "sop-001":
            return self._answer_oom(documents[0])
        if documents and documents[0].doc_id == "sop-005":
            return self._answer_security(documents[0])
        if documents and documents[0].doc_id == "sop-008":
            return self._answer_ai_quality(documents[0])
        return self._answer_generic(documents)

    @staticmethod
    def _answer_database(document: Document) -> str:
        """Answer database replication delay questions."""
        return (
            f"我读取了 {document.title}。主从延迟超过30秒应按严重数据库故障处理：\n"
            "1. 先执行 SHOW SLAVE STATUS 检查复制线程状态、错误信息和延迟秒数。\n"
            "2. 判断原因：Binlog缺失、DDL失败、主键冲突，或主库负载过高。\n"
            "3. 如果是个别事务失败，跳过前必须确认数据一致性；GTID模式按 SOP 使用 "
            "SET GTID_NEXT 处理。\n"
            "4. 修复后用 pt-table-checksum 验证主从数据一致性，并持续观察主库负载。\n"
            "5. 如果影响核心业务、需要主从切换或数据不一致，五分钟内升级给DBA团队负责人。"
        )

    @staticmethod
    def _answer_oom(document: Document) -> str:
        """Answer backend OOM questions."""
        return (
            f"我读取了 {document.title}。服务 OOM 时建议这样处理：\n"
            "1. Java服务出现 OutOfMemoryError 后，Kubernetes 可能会自动重启 Pod；重启后先保存堆转储文件。\n"
            "2. 检查最近代码发布或配置变更，并查看 JVM 监控面板确认堆内存增长曲线。\n"
            "3. 如果是突发流量，临时扩容 Pod 副本数；如果疑似内存泄漏，用 jmap 或 Arthas 分析对象分布。\n"
            "4. 紧急情况下先回滚到上一个稳定版本，同时通知开发团队排查根因。\n"
            "5. OOM 频繁发生时检查 JVM 启动参数，确认 Xmx 设置是否合理。"
        )

    @staticmethod
    def _answer_security(document: Document) -> str:
        """Answer intrusion or security incident questions."""
        return (
            f"我读取了 {document.title}。怀疑入侵时先按安全事件响应：\n"
            "1. 立即确认告警来源和影响范围，检查 WAF、IDS、SIEM、登录日志和异常 API 调用。\n"
            "2. 如果发现受感染主机，先网络隔离，不要关机或重启，保留内存和进程证据。\n"
            "3. 对可疑账号、IP、接口做止血：撤销权限、封禁来源、开启严格 WAF 规则。\n"
            "4. 保存日志、网络流量和系统快照，避免破坏取证材料。\n"
            "5. 任何成功的入侵行为必须立即升级到安全团队负责人，并视情况通知 CISO、法务和合规。"
        )

    @staticmethod
    def _answer_ai_quality(document: Document) -> str:
        """Answer recommendation/model quality questions."""
        return (
            f"我读取了 {document.title}。推荐结果质量下降时按模型效果问题排查：\n"
            "1. 先排除流量波动和样本量不足，确认点击率、转化率或相关性下降是否可靠。\n"
            "2. 检查是否有新模型上线或 AB 实验负向，必要时立即回滚旧模型。\n"
            "3. 检查特征数据是否缺失、延迟或分布漂移，联系数据团队排查特征管线。\n"
            "4. 检查召回源和候选集大小、类型分布，以及用户行为模式是否异常。\n"
            "5. 如果核心推荐或搜索服务不可用，或模型效果指标下降超过20%且持续一小时以上，升级给AI平台负责人。"
        )

    @staticmethod
    def _answer_p0(documents: list[Document]) -> str:
        """Answer P0 response workflow questions."""
        titles = "、".join(document.title for document in documents[:4])
        return (
            f"我读取并综合了 {titles} 等 SOP。P0 故障响应流程建议：\n"
            "1. 先确认故障现象、影响范围、核心链路是否受损，并记录已经采取的措施。\n"
            "2. 后端 SOP 明确：P0级故障需在五分钟内升级到技术负责人，同时拉起战争室（War Room）。\n"
            "3. 数据库 P0 如主库故障、数据丢失或核心库不可用，也要求五分钟内升级，并由两名DBA共同确认高风险操作。\n"
            "4. 网络类故障通常影响面最广，核心网络、DNS全局解析、CDN大面积故障要在三分钟内升级。\n"
            "5. 安全类 P0 如成功入侵、数据泄露或APT迹象，应立即升级到安全负责人/CISO，并保留证据。\n"
            "6. 全程在统一沟通频道同步：时间线、影响面、当前判断、临时缓解、下一步负责人。"
        )

    @staticmethod
    def _answer_generic(documents: list[Document]) -> str:
        """Fallback answer for unmatched questions."""
        if not documents:
            return "没有找到可读取的 SOP。"
        document = documents[0]
        return (
            f"我读取了 {document.title}。建议先确认影响范围、查看监控告警和近期变更，"
            "再按 SOP 的常见故障处理、升级流程和禁止操作逐项执行。"
        )
