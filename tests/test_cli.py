from __future__ import annotations

import unittest
from unittest.mock import patch

from mdtex_cli.cli import (
    RenderOptions,
    build_parser,
    find_dependencies,
    hide_heading_markers,
    mdansi_command,
    options_from_args,
    termtex_command,
)


class CommandTests(unittest.TestCase):
    def test_headings_use_rich_output_by_default(self) -> None:
        args = build_parser().parse_args([])
        options = options_from_args(args)
        self.assertEqual(options.color, "always")
        self.assertEqual(mdansi_command("mdansi", options)[3:5], ["--color", "always"])

    def test_termtex_defaults(self) -> None:
        options = RenderOptions(width=100)
        self.assertEqual(
            termtex_command("/bin/termtex", options),
            ["/bin/termtex", "-md", "-width", "100", "-italic"],
        )

    def test_termtex_ascii_without_italics(self) -> None:
        options = RenderOptions(width=80, italic=False, ascii_only=True)
        self.assertEqual(
            termtex_command("termtex", options),
            ["termtex", "-md", "-width", "80", "-ascii"],
        )

    def test_mdansi_options(self) -> None:
        options = RenderOptions(
            width=120,
            theme="dracula",
            color="always",
            line_numbers=True,
            no_wrap=True,
            no_highlight=True,
            no_code_wrap=True,
            table_border="ascii",
            no_truncate=True,
            plain=True,
        )
        self.assertEqual(
            mdansi_command("mdansi", options),
            [
                "mdansi",
                "--width",
                "120",
                "--color",
                "always",
                "--table-border",
                "ascii",
                "--theme",
                "dracula",
                "--line-numbers",
                "--no-wrap",
                "--no-highlight",
                "--no-code-wrap",
                "--no-truncate",
                "--plain",
            ],
        )

    def test_width_must_be_usable(self) -> None:
        args = build_parser().parse_args(["--width", "10"])
        with self.assertRaisesRegex(ValueError, "at least 20"):
            options_from_args(args)

    def test_only_styled_headings_lose_markers(self) -> None:
        cases = {
            b"\x1b[33m\x1b[1m# Heading\x1b[0m\n": b"\x1b[33m\x1b[1mHeading\x1b[0m\n",
            b"\x1b[35m\x1b[1m\x1b[2m###### Six\x1b[0m\n": b"\x1b[35m\x1b[1m\x1b[2mSix\x1b[0m\n",
            "\x1b[90m│\x1b[0m \x1b[33m\x1b[1m# Quoted\x1b[0m\n".encode(): "\x1b[90m│\x1b[0m \x1b[33m\x1b[1mQuoted\x1b[0m\n".encode(),
            b"\x1b[1m# Bold paragraph\x1b[0m\n": b"\x1b[1m# Bold paragraph\x1b[0m\n",
            b"# Escaped literal\n": b"# Escaped literal\n",
            "\x1b[2m│ \x1b[0m# code\n".encode(): "\x1b[2m│ \x1b[0m# code\n".encode(),
        }
        for source, expected in cases.items():
            with self.subTest(source=source):
                self.assertEqual(hide_heading_markers(source), expected)


class DependencyTests(unittest.TestCase):
    def test_missing_dependencies_are_reported_together(self) -> None:
        with (
            patch("mdtex_cli.cli.shutil.which", return_value=None),
            self.assertRaisesRegex(RuntimeError, "termtex, mdansi"),
        ):
            find_dependencies()

    def test_dependency_paths_are_returned(self) -> None:
        paths = {"termtex": "/tools/termtex", "mdansi": "/tools/mdansi"}
        with patch("mdtex_cli.cli.shutil.which", side_effect=paths.get):
            self.assertEqual(find_dependencies(), ("/tools/termtex", "/tools/mdansi"))


if __name__ == "__main__":
    unittest.main()
