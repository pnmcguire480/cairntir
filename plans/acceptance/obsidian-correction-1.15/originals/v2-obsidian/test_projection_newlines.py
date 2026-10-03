"""Public regression frozen before the shared projection newline repair."""

import tempfile
import unittest
from pathlib import Path

from cairntir.obsidian import _upsert_generated


class ProjectionNewlinesAcceptance(unittest.TestCase):
    def test_refresh_preserves_mixed_newline_bytes_outside_generated_block(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            path = root / "note.md"
            begin = b"<!-- cairntir:generated:begin -->"
            end = b"<!-- cairntir:generated:end -->"
            prefix = "# Human café\r\n\nA prefix with LF.\n".encode()
            suffix = "\r\n\n## My Notes\r\nMixed lines\nKeep café.\r\n".encode()
            path.write_bytes(prefix + begin + b"\r\nold generated\r\n" + end + suffix)
            _upsert_generated(path, "new generated\nsecond line", title="Unused", root=root)
            result = path.read_bytes()
            self.assertEqual(result.split(begin)[0], prefix)
            self.assertEqual(result.split(end)[1], suffix)
            self.assertIn(b"new generated", result)
            self.assertEqual(result.count(begin), 1)
            self.assertEqual(result.count(end), 1)


if __name__ == "__main__":
    unittest.main()
