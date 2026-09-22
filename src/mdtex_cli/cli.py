from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO

from mdtex_cli import __version__


_ANSI_STYLE = rb"(?:\x1b\[[0-9;]*m)"
_HEADING = re.compile(
    rb"^(?P<quote>(?:"
    + _ANSI_STYLE
    + rb"*\xe2\x94\x82"
    + _ANSI_STYLE
    + rb"* ?)*)(?P<style>"
    + _ANSI_STYLE
    + rb"+)#{1,6} "
)
_FOREGROUND_COLOR = re.compile(rb"\x1b\[(?:3[0-7]|9[0-7]|38;[0-9;]+)m")


def hide_heading_markers(line: bytes) -> bytes:
    """Remove mdansi's visual ATX markers from colored, bold headings."""
    match = _HEADING.match(line)
    if match is None:
        return line
    style = match.group("style")
    if b"\x1b[1m" not in style or _FOREGROUND_COLOR.search(style) is None:
        return line
    return match.group("quote") + style + line[match.end() :]


@dataclass(frozen=True)
class RenderOptions:
    width: int
    italic: bool = True
    ascii_only: bool = False
    theme: str | None = None
    color: str = "always"
    line_numbers: bool = False
    no_wrap: bool = False
    no_highlight: bool = False
    no_code_wrap: bool = False
    table_border: str = "unicode"
    no_truncate: bool = False
    plain: bool = False


def terminal_width() -> int:
    return shutil.get_terminal_size(fallback=(80, 24)).columns


def termtex_command(executable: str, options: RenderOptions) -> list[str]:
    command = [executable, "-md", "-width", str(options.width)]
    if options.italic:
        command.append("-italic")
    if options.ascii_only:
        command.append("-ascii")
    return command


def mdansi_command(executable: str, options: RenderOptions) -> list[str]:
    command = [
        executable,
        "--width",
        str(options.width),
        "--color",
        options.color,
        "--table-border",
        options.table_border,
    ]
    if options.theme is not None:
        command.extend(["--theme", options.theme])
    if options.line_numbers:
        command.append("--line-numbers")
    if options.no_wrap:
        command.append("--no-wrap")
    if options.no_highlight:
        command.append("--no-highlight")
    if options.no_code_wrap:
        command.append("--no-code-wrap")
    if options.no_truncate:
        command.append("--no-truncate")
    if options.plain:
        command.append("--plain")
    return command


def find_dependencies() -> tuple[str, str]:
    termtex = shutil.which("termtex")
    mdansi = shutil.which("mdansi")
    missing = [
        name
        for name, path in (("termtex", termtex), ("mdansi", mdansi))
        if path is None
    ]
    if missing:
        names = ", ".join(missing)
        raise RuntimeError(
            f"Missing required executable(s): {names}. "
            "See https://github.com/lucaspon/md-cli#install"
        )
    return termtex, mdansi


def render(
    source: BinaryIO,
    output: BinaryIO,
    options: RenderOptions,
    termtex: str,
    mdansi: str,
) -> int:
    termtex_process = subprocess.Popen(
        termtex_command(termtex, options),
        stdin=source,
        stdout=subprocess.PIPE,
    )
    assert termtex_process.stdout is not None

    try:
        mdansi_process = subprocess.Popen(
            mdansi_command(mdansi, options),
            stdin=termtex_process.stdout,
            stdout=subprocess.PIPE,
        )
    except BaseException:
        termtex_process.terminate()
        termtex_process.wait()
        raise
    finally:
        termtex_process.stdout.close()

    try:
        assert mdansi_process.stdout is not None
        for line in mdansi_process.stdout:
            output.write(hide_heading_markers(line))
        output.flush()
        mdansi_exit_code = mdansi_process.wait()
        termtex_exit_code = termtex_process.wait()
    except (BrokenPipeError, KeyboardInterrupt) as error:
        mdansi_process.terminate()
        termtex_process.terminate()
        mdansi_process.wait()
        termtex_process.wait()
        return 0 if isinstance(error, BrokenPipeError) else 130
    finally:
        if mdansi_process.stdout is not None:
            mdansi_process.stdout.close()

    return mdansi_exit_code or termtex_exit_code


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="md",
        description="Render Markdown and LaTeX in the terminal.",
    )
    parser.add_argument(
        "file", nargs="?", help="Markdown file; omit or use - for stdin"
    )
    parser.add_argument("-w", "--width", type=int, help="output width in columns")
    parser.add_argument("-t", "--theme", help="mdansi color theme")
    parser.add_argument(
        "--color",
        choices=("always", "never", "auto"),
        default="always",
        help="color output mode (default: always; auto honors NO_COLOR and TTY detection)",
    )
    parser.add_argument(
        "--table-border",
        choices=("unicode", "ascii", "none"),
        default="unicode",
        help="table border style (default: unicode)",
    )
    parser.add_argument(
        "-n", "--line-numbers", action="store_true", help="show code line numbers"
    )
    parser.add_argument(
        "--no-italic", action="store_true", help="disable mathematical italic Unicode"
    )
    parser.add_argument(
        "--ascii", action="store_true", help="restrict math output to ASCII"
    )
    parser.add_argument("--no-wrap", action="store_true", help="disable prose wrapping")
    parser.add_argument(
        "--no-highlight", action="store_true", help="disable syntax highlighting"
    )
    parser.add_argument(
        "--no-code-wrap", action="store_true", help="disable code wrapping"
    )
    parser.add_argument(
        "--no-truncate", action="store_true", help="disable table-cell truncation"
    )
    parser.add_argument("--plain", action="store_true", help="strip ANSI styling")
    parser.add_argument(
        "--doctor", action="store_true", help="check external dependencies and exit"
    )
    parser.add_argument(
        "-V", "--version", action="version", version=f"%(prog)s {__version__}"
    )
    return parser


def options_from_args(args: argparse.Namespace) -> RenderOptions:
    width = args.width if args.width is not None else terminal_width()
    if width < 20:
        raise ValueError("width must be at least 20 columns")
    return RenderOptions(
        width=width,
        italic=not args.no_italic,
        ascii_only=args.ascii,
        theme=args.theme,
        color=args.color,
        line_numbers=args.line_numbers,
        no_wrap=args.no_wrap,
        no_highlight=args.no_highlight,
        no_code_wrap=args.no_code_wrap,
        table_border=args.table_border,
        no_truncate=args.no_truncate,
        plain=args.plain,
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if not args.doctor:
        try:
            options = options_from_args(args)
        except ValueError as error:
            parser.error(str(error))

        if args.file not in (None, "-"):
            path = Path(args.file).expanduser()
            if not path.is_file():
                parser.error(f"not a readable file: {path}")

    try:
        termtex, mdansi = find_dependencies()
    except RuntimeError as error:
        parser.exit(127, f"md: {error}\n")

    if args.doctor:
        print(f"termtex: {termtex}")
        print(f"mdansi: {mdansi}")
        return 0

    if args.file in (None, "-"):
        return render(sys.stdin.buffer, sys.stdout.buffer, options, termtex, mdansi)

    try:
        with path.open("rb") as source:
            return render(source, sys.stdout.buffer, options, termtex, mdansi)
    except OSError as error:
        parser.exit(2, f"md: {error}\n")
