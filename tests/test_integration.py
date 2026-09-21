from __future__ import annotations

import os
import shutil
import stat
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path


class PipelineIntegrationTests(unittest.TestCase):
    def test_file_flows_through_both_renderers(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            bin_dir = root / "bin"
            bin_dir.mkdir()
            self._write_executable(
                bin_dir / "termtex",
                """
                import sys
                assert sys.argv[1:] == ["-md", "-width", "88", "-italic"]
                sys.stdout.buffer.write(sys.stdin.buffer.read().replace(b"$x^2$", "x²".encode()))
                """,
            )
            self._write_executable(
                bin_dir / "mdansi",
                """
                import sys
                assert sys.argv[1:] == ["--width", "88", "--color", "never", "--table-border", "unicode"]
                sys.stdout.buffer.write(b"rendered:\\n" + sys.stdin.buffer.read())
                """,
            )
            markdown = root / "document.md"
            markdown.write_text("# Math\n\n$x^2$\n", encoding="utf-8")
            environment = os.environ.copy()
            environment["PATH"] = f"{bin_dir}{os.pathsep}{environment['PATH']}"

            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "mdtex_cli",
                    "--width",
                    "88",
                    "--color",
                    "never",
                    str(markdown),
                ],
                check=False,
                capture_output=True,
                env=environment,
            )

            self.assertEqual(result.returncode, 0, result.stderr.decode())
            self.assertEqual(result.stdout.decode(), "rendered:\n# Math\n\nx²\n")

    @unittest.skipUnless(
        shutil.which("termtex") and shutil.which("mdansi"), "renderers not installed"
    )
    def test_standard_input_with_real_renderers(self) -> None:
        result = subprocess.run(
            [sys.executable, "-m", "mdtex_cli", "--width", "80", "--plain"],
            input=b"# Formula\n\nInline $x^2$.\n",
            capture_output=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr.decode())
        self.assertIn("Inline 𝑥².", result.stdout.decode())

    def test_missing_file_reports_error(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            missing_path = Path(directory) / "missing.md"
            result = subprocess.run(
                [sys.executable, "-m", "mdtex_cli", str(missing_path)],
                capture_output=True,
                check=False,
            )
        self.assertEqual(result.returncode, 2)
        self.assertIn("not a readable file:", result.stderr.decode())

    def test_downstream_failure_is_propagated(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._write_executable(
                root / "termtex",
                """
                import sys
                sys.stdout.buffer.write(sys.stdin.buffer.read())
                """,
            )
            self._write_executable(root / "mdansi", "import sys\nsys.exit(7)\n")
            environment = os.environ.copy()
            environment["PATH"] = f"{root}{os.pathsep}{environment['PATH']}"
            result = subprocess.run(
                [sys.executable, "-m", "mdtex_cli", "--width", "80"],
                input=b"# Heading\n",
                capture_output=True,
                check=False,
                env=environment,
            )
            self.assertEqual(result.returncode, 7, result.stderr.decode())

    @staticmethod
    def _write_executable(path: Path, body: str) -> None:
        script = f"#!{sys.executable}\n{textwrap.dedent(body).lstrip()}"
        path.write_text(script, encoding="utf-8")
        path.chmod(path.stat().st_mode | stat.S_IXUSR)


if __name__ == "__main__":
    unittest.main()
