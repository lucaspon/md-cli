from __future__ import annotations

import base64
import os
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path


class PipelineIntegrationTests(unittest.TestCase):
    @unittest.skipUnless(
        shutil.which("termtex") and shutil.which("mdansi"), "renderers not installed"
    )
    def test_wrapped_tables_keep_every_cell_and_respect_width(self) -> None:
        rows = [
            ["#", "Request", "Why it matters", "Priority", "Status"],
            [
                "1",
                "Hashed customer ID on every loan plus the sequence number for that customer.",
                "Measures loan rolling and borrower concentration without losing the final words.",
                "Critical",
                "Open",
            ],
            [
                "2",
                "Transaction-level payments with actual date, amount, and principal and interest split.",
                "Gives true payment timing and the cash flow schedule needed by the waterfall.",
                "High",
                "Open",
            ],
        ]
        source = "| " + " | ".join(rows[0]) + " |\n|---|---|---|---|---|\n"
        source += "\n".join("| " + " | ".join(row) + " |" for row in rows[1:]) + "\n"
        normalize = lambda value: "".join(value.split())
        for width in (40, 80, 120):
            for border in ("unicode", "ascii", "none"):
                with self.subTest(width=width, border=border):
                    result = subprocess.run(
                        [
                            sys.executable,
                            "-m",
                            "mdtex_cli",
                            "--width",
                            str(width),
                            "--table-border",
                            border,
                            "--plain",
                        ],
                        input=source.encode(),
                        capture_output=True,
                        check=False,
                    )
                    self.assertEqual(result.returncode, 0, result.stderr.decode())
                    output = result.stdout.decode()
                    self.assertNotIn("…", output)
                    self.assertTrue(
                        all(len(line) <= width for line in output.splitlines())
                    )
                    if border != "none":
                        actual: list[list[str]] = []
                        current = [""] * 5
                        vertical = "│" if border == "unicode" else "|"
                        for line in output.splitlines():
                            if line.startswith(vertical):
                                for index, cell in enumerate(
                                    line.split(vertical)[1:-1]
                                ):
                                    current[index] += normalize(cell)
                            elif any(current):
                                actual.append(current)
                                current = [""] * 5
                        self.assertEqual(
                            actual, [[normalize(cell) for cell in row] for row in rows]
                        )
                    else:
                        self.assertNotIn("│", output)
                        underline = next(
                            line
                            for line in output.splitlines()
                            if re.fullmatch(r"─+(?:  ─+)+", line)
                        )
                        spans = [
                            (match.start(), match.end())
                            for match in re.finditer(r"─+", underline)
                        ]
                        actual = []
                        current = [""] * 5
                        for line in output.splitlines():
                            if line == underline or not line.strip():
                                if any(current):
                                    actual.append(current)
                                    current = [""] * 5
                            else:
                                for index, (start, end) in enumerate(spans):
                                    current[index] += normalize(line[start:end])
                        if any(current):
                            actual.append(current)
                        self.assertEqual(
                            actual, [[normalize(cell) for cell in row] for row in rows]
                        )

        truncated = subprocess.run(
            [
                sys.executable,
                "-m",
                "mdtex_cli",
                "--width",
                "80",
                "--plain",
                "--no-table-wrap",
            ],
            input=source.encode(),
            capture_output=True,
            check=False,
        )
        self.assertEqual(truncated.returncode, 0, truncated.stderr.decode())
        self.assertIn("…", truncated.stdout.decode())
        unwrapped = subprocess.run(
            [
                sys.executable,
                "-m",
                "mdtex_cli",
                "--width",
                "80",
                "--plain",
                "--no-table-wrap",
                "--no-truncate",
            ],
            input=source.encode(),
            capture_output=True,
            check=False,
        )
        self.assertEqual(unwrapped.returncode, 0, unwrapped.stderr.decode())
        self.assertIn(rows[1][1], unwrapped.stdout.decode())

    @unittest.skipUnless(
        shutil.which("termtex") and shutil.which("mdansi"), "renderers not installed"
    )
    def test_latex_table_and_relative_image_with_real_renderers(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "chart.png").write_bytes(
                base64.b64decode(
                    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aRZkAAAAASUVORK5CYII="
                )
            )
            markdown = root / "document.md"
            markdown.write_text(
                r"""# Results

\begin{table}[H]
\caption{Fees}
\begin{tabular}{l r r}
\toprule
\textbf{Metric} & \textbf{Mean} & \textbf{P95} \\
\midrule
Total Fees & £59.9M & £61.0M \\
\bottomrule
\end{tabular}
\end{table}

\newpage
![Chart](chart.png){ width=95% }

After chart.
""",
                encoding="utf-8",
            )
            command = [sys.executable, "-m", "mdtex_cli", "--width", "80"]
            result = subprocess.run(
                command + ["--images", "kitty", str(markdown)],
                capture_output=True,
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr.decode())
            self.assertIn(b"\x1b_Ga=T", result.stdout)
            output = result.stdout.decode()
            self.assertIn("£59.9M", output)
            self.assertIn("£61.0M", output)
            self.assertIn("┌", output)
            self.assertLess(output.index("[image: Chart]"), output.index("\x1b_Ga=T"))
            self.assertLess(output.index("\x1b_Ga=T"), output.index("After chart."))
            self.assertNotIn(r"\begin{table}", output)
            self.assertNotIn(r"\newpage", output)
            self.assertNotIn("width=95%", output)
            self.assertNotIn("Preview unavailable", output)
            self.assertNotIn("MDI", output)

            plain = subprocess.run(
                command + ["--plain", "--images", "kitty", str(markdown)],
                capture_output=True,
                check=False,
            )
            self.assertEqual(plain.returncode, 0, plain.stderr.decode())
            self.assertIn(b"[image: Chart] (chart.png)", plain.stdout)
            self.assertNotIn(b"\x1b", plain.stdout)

            narrow = subprocess.run(
                command + ["--width", "20", str(markdown)],
                capture_output=True,
                check=False,
            )
            self.assertEqual(narrow.returncode, 0, narrow.stderr.decode())
            self.assertIn(b"[image: Chart] (chart.png)", narrow.stdout)
            self.assertNotIn(b"MDI", narrow.stdout)

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
                assert sys.argv[1:] == ["--width", "88", "--color", "never", "--table-border", "unicode", "--no-truncate"]
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

    @unittest.skipUnless(
        shutil.which("termtex") and shutil.which("mdansi"), "renderers not installed"
    )
    def test_every_heading_level_is_bold_by_default(self) -> None:
        markdown = "\n\n".join(
            f"{'#' * level} Level {level}" for level in range(1, 7)
        ).encode()
        environment = os.environ.copy()
        environment["NO_COLOR"] = "1"
        result = subprocess.run(
            [sys.executable, "-m", "mdtex_cli", "--width", "80"],
            input=markdown,
            capture_output=True,
            check=False,
            env=environment,
        )
        self.assertEqual(result.returncode, 0, result.stderr.decode())
        output_lines = result.stdout.decode().splitlines()
        for level in range(1, 7):
            heading = f"Level {level}"
            line = next(line for line in output_lines if heading in line)
            self.assertIn("\x1b[1m", line, f"heading level {level} lacks bold ANSI")
            self.assertNotIn("#", line, f"heading level {level} kept its marker")

        safety_result = subprocess.run(
            [sys.executable, "-m", "mdtex_cli", "--width", "80"],
            input=b"# Heading\n\n**# Bold paragraph**\n\n\\# Escaped\n\n```md\n# code\n```\n",
            capture_output=True,
            check=False,
            env=environment,
        )
        self.assertEqual(safety_result.returncode, 0, safety_result.stderr.decode())
        safety_output = re.sub(r"\x1b\[[0-9;]*m", "", safety_result.stdout.decode())
        self.assertIn("# Bold paragraph", safety_output)
        self.assertIn("# Escaped", safety_output)
        self.assertIn("# code", safety_output)
        self.assertNotIn("# Heading", safety_output)

        auto_result = subprocess.run(
            [sys.executable, "-m", "mdtex_cli", "--width", "80", "--color", "auto"],
            input=markdown,
            capture_output=True,
            check=False,
            env=environment,
        )
        self.assertEqual(auto_result.returncode, 0, auto_result.stderr.decode())
        self.assertNotIn(b"\x1b[", auto_result.stdout)

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
