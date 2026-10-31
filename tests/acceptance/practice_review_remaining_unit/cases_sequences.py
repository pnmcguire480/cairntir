"""Public immutable receipt sequence contract, independent of runtime stores."""

import unittest

from cairntir import procedures as api


class ReceiptSequences(unittest.TestCase):
    def test_observation_receipt_detaches_caller_source_hash_sequence(self):
        source_hashes = ["1" * 64]
        observation = api.PracticeObservation(
            "event", "2024-02-29", "simulated", None, None, None, None, None, None, [1]
        )
        receipt = api.PracticeObservationReceipt(
            2, 3, 3, "2" * 64, observation, None, source_hashes, "3" * 64
        )
        source_hashes.append("4" * 64)
        self.assertIs(type(receipt.evidence_sha256), tuple)
        self.assertEqual(receipt.evidence_sha256, ("1" * 64,))
