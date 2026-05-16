"""Memory retrieval tests."""

import tempfile
import unittest
from pathlib import Path

from oncall_app.memory.models import MemoryRecord
from oncall_app.memory.retrieval import MemoryRetriever
from oncall_app.memory.store import MemoryStore


class MemoryRetrievalTest(unittest.TestCase):
    """Recall relevant non-SOP memories."""

    def test_search_prefers_relevant_service_owner(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            store = MemoryStore(Path(temp_dir) / "memory.sqlite3")
            store.upsert_memory(
                MemoryRecord(
                    layer="L1",
                    kind="service_owner",
                    content="支付服务负责人是小王，升级群是 #pay-oncall。",
                    summary="支付服务负责人：小王；升级群：#pay-oncall",
                    tags=["支付服务", "负责人"],
                    importance=0.9,
                )
            )
            store.upsert_memory(
                MemoryRecord(
                    layer="L1",
                    kind="service_owner",
                    content="推荐服务负责人是小李。",
                    summary="推荐服务负责人：小李",
                    tags=["推荐服务"],
                    importance=0.7,
                )
            )

            hits = MemoryRetriever(store).search("支付服务报警应该找谁？", limit=2)

            self.assertEqual(hits[0].record.summary, "支付服务负责人：小王；升级群：#pay-oncall")
            self.assertGreater(hits[0].score, hits[1].score)

    def test_l3_profile_is_loaded_separately(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            store = MemoryStore(Path(temp_dir) / "memory.sqlite3")
            store.upsert_memory(
                MemoryRecord(layer="L3", kind="profile", content="用户偏好中文、短答案。")
            )

            profile = MemoryRetriever(store).load_profile(limit=3)

            self.assertEqual(profile[0].record.layer, "L3")


if __name__ == "__main__":
    unittest.main()
