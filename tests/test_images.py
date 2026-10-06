from __future__ import annotations

import base64
import io
import os
import re
import struct
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from mdtex_cli.document import Image
from mdtex_cli.images import (
    image_protocol,
    image_size,
    local_image_path,
    png_data,
    write_graphics,
    write_image,
)

# Valid 1x1 PNG; tests can exercise framing without an image library.
PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aRZkAAAAASUVORK5CYII="
)


class TerminalOutput(io.BytesIO):
    def isatty(self) -> bool:
        return True


class ImageTests(unittest.TestCase):
    def test_auto_detection_requires_supported_tty(self) -> None:
        for environment, expected in (
            ({"TERM_PROGRAM": "ghostty"}, "kitty"),
            ({"TERM": "xterm-kitty"}, "kitty"),
            ({"TERM_PROGRAM": "iTerm.app"}, "iterm"),
            ({"TERM_PROGRAM": "Apple_Terminal"}, None),
            ({"TERM_PROGRAM": "ghostty", "TMUX": "/tmp/tmux"}, None),
            ({"TERM": "xterm-kitty", "STY": "screen"}, None),
        ):
            with (
                self.subTest(environment=environment),
                patch.dict(os.environ, environment, clear=True),
            ):
                self.assertEqual(image_protocol("auto", TerminalOutput()), expected)
                self.assertIsNone(image_protocol("auto", io.BytesIO()))
        self.assertEqual(image_protocol("kitty", io.BytesIO()), "kitty")
        self.assertIsNone(image_protocol("kitty", TerminalOutput(), plain=True))
        self.assertIsNone(image_protocol("never", TerminalOutput()))

    def test_local_paths_resolve_relative_to_document(self) -> None:
        root = Path("/docs")
        self.assertEqual(
            local_image_path("../charts/a%20b.pdf", root), root / "../charts/a b.pdf"
        )
        self.assertEqual(
            local_image_path("file:///tmp/chart.png", root), Path("/tmp/chart.png")
        )
        self.assertIsNone(local_image_path("https://example.com/chart.png", root))
        self.assertIsNone(local_image_path("file://remote/chart.png", root))

    def test_kitty_payload_is_chunked_and_decodes_to_original_image(self) -> None:
        data = PNG + b"x" * 10000
        output = io.BytesIO()
        with patch(
            "mdtex_cli.images.shutil.get_terminal_size",
            return_value=os.terminal_size((80, 24)),
        ):
            write_graphics(data, output, "kitty", 80)
        frames = re.findall(rb"\x1b_G([^;]+);(.*?)\x1b\\", output.getvalue())
        self.assertGreater(len(frames), 1)
        self.assertIn(b"a=T,f=100,q=2,C=1,c=40,r=20", frames[0][0])
        self.assertTrue(all(len(payload) <= 4096 for _, payload in frames))
        self.assertIn(b"m=1", frames[0][0])
        self.assertEqual(frames[-1][0], b"m=0")
        self.assertEqual(
            base64.b64decode(b"".join(payload for _, payload in frames)), data
        )

    def test_iterm_multipart_is_inline_and_round_trips(self) -> None:
        output = io.BytesIO()
        write_graphics(PNG, output, "iterm", 80)
        self.assertIn(b"MultipartFile=inline=1", output.getvalue())
        self.assertIn(b"preserveAspectRatio=1", output.getvalue())
        chunks = re.findall(rb"FilePart=(.*?)\x07", output.getvalue())
        self.assertEqual(base64.b64decode(b"".join(chunks)), PNG)
        self.assertTrue(output.getvalue().endswith(b"FileEnd\x07\n"))

    def test_size_fits_terminal_and_rejects_zero_dimensions(self) -> None:
        data = PNG[:16] + struct.pack(">II", 1600, 100) + PNG[24:]
        with patch(
            "mdtex_cli.images.shutil.get_terminal_size",
            return_value=os.terminal_size((80, 24)),
        ):
            self.assertEqual(image_size(data, 100, io.BytesIO()), (80, 3))
        data = PNG[:16] + b"\0" * 8 + PNG[24:]
        with self.assertRaisesRegex(ValueError, "dimensions"):
            image_size(data, 80, io.BytesIO())

    def test_png_needs_no_converter(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "a.png"
            path.write_bytes(PNG)
            with patch("mdtex_cli.images.subprocess.run") as run:
                self.assertEqual(png_data(path, 80), PNG)
                run.assert_not_called()

    def test_pdf_converter_uses_first_page_and_absolute_file_argument(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "chart with spaces.pdf"
            path.touch()
            with (
                patch("mdtex_cli.images.shutil.which", return_value="/tools/pdftoppm"),
                patch(
                    "mdtex_cli.images.subprocess.run",
                    return_value=subprocess.CompletedProcess([], 0, PNG, b""),
                ) as run,
            ):
                self.assertEqual(png_data(path, 80), PNG)
                self.assertEqual(
                    run.call_args.args[0],
                    [
                        "/tools/pdftoppm",
                        "-f",
                        "1",
                        "-l",
                        "1",
                        "-singlefile",
                        "-scale-to",
                        "1280",
                        "-png",
                        str(path),
                    ],
                )

    def test_missing_converter_gives_actionable_fallback(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "chart.pdf").touch()
            output = io.BytesIO()
            with patch("mdtex_cli.images.shutil.which", return_value=None):
                write_image(Image("Chart", "chart.pdf"), output, "kitty", 80, root)
            self.assertIn(b"[image: Chart] (chart.pdf)", output.getvalue())
            self.assertIn(b"install poppler", output.getvalue())
            self.assertNotIn(b"\x1b_G", output.getvalue())

    def test_text_mode_does_not_read_or_convert_images(self) -> None:
        output = io.BytesIO()
        with patch("mdtex_cli.images.png_data") as convert:
            write_image(Image("Chart", "missing.pdf"), output, None, 80, Path.cwd())
            convert.assert_not_called()
        self.assertEqual(output.getvalue(), b"[image: Chart] (missing.pdf)\n")

    def test_bad_missing_and_remote_images_keep_document_readable(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "bad.png").write_bytes(b"invalid")
            for target, message in (
                ("bad.png", "invalid PNG"),
                ("missing.png", "file not found"),
                ("https://example.com/a.png", "remote images are not fetched"),
            ):
                with self.subTest(target=target):
                    output = io.BytesIO()
                    write_image(Image("Chart\x1b", target), output, "kitty", 80, root)
                    self.assertIn(message.encode(), output.getvalue())
                    self.assertNotIn(b"\x1b", output.getvalue())


if __name__ == "__main__":
    unittest.main()
