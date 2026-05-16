"""Memory store tests."""

import tempfile
import unittest
from pathlib import Path

from oncall_app.memory.models import MemoryRecord, RawMemoryEvent
from oncall_app.memory.store import MemoryStore


class MemoryStoreTest(unittest.TestCase):
    """SQLite-backed memory persistence."""

    def test_event_round_trips_with_trace_payloads(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            store = MemoryStore(Path(temp_dir) / "memory.sqlite3")
            event = RawMemoryEvent(
                session_id="session-1",
                user_message="记住：支付服务负责人是小王。",
                assistant_answer="已记录。",
                tool_calls=[{"tool": "readFile", "fname": "sop-001.html"}],
                evidence=[{"file": "sop-001.html", "section": "升级", "text": "联系负责人"}],
                trace=[{"type": "memory_write", "message": "stored"}],
            )

            stored = store.add_event(event)
            loaded = store.get_event(stored.id)

            self.assertEqual(loaded.session_id, "session-1")
            self.assertEqual(loaded.user_message, event.user_message)
            self.assertEqual(loaded.tool_calls[0]["fname"], "sop-001.html")

    def test_l1_memory_round_trips_and_filters_by_layer(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            store = MemoryStore(Path(temp_dir) / "memory.sqlite3")
            record = MemoryRecord(
                layer="L1",
                kind="service_owner",
                content="支付服务负责人是小王。",
                summary="支付服务负责人：小王",
                tags=["支付服务", "负责人"],
                source_event_ids=["evt-1"],
                confidence=0.9,
                importance=0.8,
            )

            stored = store.upsert_memory(record)
            records = store.list_memories(layer="L1")

            self.assertEqual(records[0].id, stored.id)
            self.assertEqual(records[0].summary, "支付服务负责人：小王")
            self.assertEqual(records[0].tags, ["支付服务", "负责人"])

    def test_delete_marks_memory_inactive(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            store = MemoryStore(Path(temp_dir) / "memory.sqlite3")
            stored = store.upsert_memory(
                MemoryRecord(layer="L1", kind="preference", content="用户偏好中文回答。")
            )

            store.delete_memory(stored.id)

            self.assertEqual(store.list_memories(), [])
            self.assertIsNotNone(store.get_memory(stored.id, include_inactive=True).deleted_at)


if __name__ == "__main__":
    unittest.main()
