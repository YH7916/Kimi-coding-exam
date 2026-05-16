"""Memory evaluation case tests."""

import unittest

from oncall_app.evaluation.cases import MEMORY_CASES


class MemoryEvalCaseTest(unittest.TestCase):
    """Memory evaluation cases are explicit and replayable."""

    def test_memory_cases_include_write_and_recall(self):
        self.assertTrue(MEMORY_CASES)
        case = MEMORY_CASES[0]
        self.assertIn("write", case)
        self.assertIn("recall", case)
        self.assertIn("expected_memory", case)


if __name__ == "__main__":
    unittest.main()
