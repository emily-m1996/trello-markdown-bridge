import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from kanbanbridge.cli import main


class DryRunTests(unittest.TestCase):
    def test_dry_run_leaves_output_file_untouched(self):
        with tempfile.TemporaryDirectory() as tmp:
            input_path = Path(tmp) / "board.json"
            output_path = Path(tmp) / "board.md"
            input_path.write_text(
                json.dumps(
                    {
                        "name": "Board",
                        "lists": [{"id": "l1", "name": "To Do", "closed": False}],
                        "cards": [
                            {"id": "c1", "name": "Card", "idList": "l1", "closed": False},
                        ],
                    }
                ),
                encoding="utf-8",
            )

            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                exit_code = main([str(input_path), str(output_path), "--dry-run"])

            self.assertEqual(exit_code, 0)
            self.assertFalse(output_path.exists())
            self.assertIn("dry run OK", stdout.getvalue())
            self.assertIn("1 list(s), 1 card(s)", stdout.getvalue())
            self.assertIn("0 warnings", stdout.getvalue())

    def test_dry_run_lists_lenient_warnings(self):
        with tempfile.TemporaryDirectory() as tmp:
            input_path = Path(tmp) / "messy.json"
            output_path = Path(tmp) / "board.md"
            input_path.write_text(
                json.dumps(
                    {
                        "name": "Board",
                        "lists": [{"id": "l1", "name": "To Do", "closed": False}],
                        "cards": [
                            {"id": "c1", "name": "Orphan card", "idList": "missing-list", "closed": False},
                        ],
                    }
                ),
                encoding="utf-8",
            )

            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                exit_code = main([str(input_path), str(output_path), "--dry-run", "--lenient"])

            self.assertEqual(exit_code, 0)
            self.assertFalse(output_path.exists())
            output = stdout.getvalue()
            self.assertIn("1 warning(s):", output)
            self.assertIn("Orphan card", output)
            self.assertIn("Unsorted", output)

    def test_dry_run_still_fails_in_strict_mode(self):
        with tempfile.TemporaryDirectory() as tmp:
            input_path = Path(tmp) / "messy.json"
            output_path = Path(tmp) / "board.md"
            input_path.write_text(
                json.dumps(
                    {
                        "name": "Board",
                        "lists": [{"id": "l1", "name": "To Do", "closed": False}],
                        "cards": [
                            {"id": "c1", "name": "Orphan card", "idList": "missing-list", "closed": False},
                        ],
                    }
                ),
                encoding="utf-8",
            )

            stderr = io.StringIO()
            with contextlib.redirect_stderr(stderr):
                exit_code = main([str(input_path), str(output_path), "--dry-run"])

            self.assertEqual(exit_code, 1)
            self.assertFalse(output_path.exists())
            self.assertIn("unknown list id", stderr.getvalue())


if __name__ == "__main__":
    unittest.main()
