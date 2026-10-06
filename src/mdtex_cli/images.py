"""Local images over Kitty/iTerm graphics protocols, with readable fallbacks."""

from __future__ import annotations

import base64
import math
import os
import shutil
import struct
import subprocess
from pathlib import Path
from typing import BinaryIO
from urllib.parse import unquote, urlsplit

from mdtex_cli.document import Image


def image_protocol(mode: str, output: BinaryIO, plain: bool = False) -> str | None:
    if plain or mode == "never":
        return None
    if mode != "auto":
        return mode
    if not output.isatty() or os.environ.get("TMUX") or os.environ.get("STY"):
        return None
    program = os.environ.get("TERM_PROGRAM", "").lower()
    term = os.environ.get("TERM", "").lower()
    if program in ("ghostty", "kitty") or term in ("xterm-kitty", "xterm-ghostty"):
        return "kitty"
    if program == "iterm.app":
        return "iterm"
    return None


def local_image_path(target: str, base_dir: Path) -> Path | None:
    url = urlsplit(target)
    if url.scheme and url.scheme != "file":
        return None
    if url.scheme == "file" and url.netloc not in ("", "localhost"):
        return None
    value = unquote(url.path) if url.scheme else unquote(target)
    path = Path(value).expanduser()
    return path if path.is_absolute() else base_dir / path


def png_data(path: Path, width: int) -> bytes:
    if not path.is_file():
        raise ValueError("file not found")
    if path.suffix.lower() == ".png":
        if path.stat().st_size > 32 * 1024 * 1024:
            raise ValueError("image exceeds 32 MiB")
        data = path.read_bytes()
    else:
        if path.suffix.lower() == ".pdf":
            tool = shutil.which("pdftoppm")
            if tool is None:
                raise ValueError("PDF preview needs pdftoppm (install poppler)")
            command = [
                tool,
                "-f",
                "1",
                "-l",
                "1",
                "-singlefile",
                "-scale-to",
                str(width * 16),
                "-png",
                str(path),
            ]
        else:
            tool = shutil.which("magick")
            if tool is None:
                raise ValueError("this format needs ImageMagick; PNG works directly")
            command = [
                tool,
                str(path) + "[0]",
                "-resize",
                f"{width * 16}x{width * 16}>",
                "png:-",
            ]
        result = subprocess.run(command, capture_output=True, timeout=30, check=False)
        if result.returncode:
            raise ValueError("image conversion failed")
        data = result.stdout
    if len(data) < 24 or data[:8] != b"\x89PNG\r\n\x1a\n" or data[12:16] != b"IHDR":
        raise ValueError("invalid PNG image")
    if len(data) > 32 * 1024 * 1024:
        raise ValueError("image exceeds 32 MiB")
    return data


def image_size(data: bytes, width: int, output: BinaryIO) -> tuple[int, int]:
    """Fit image to terminal cells, retaining the PNG's aspect ratio."""
    pixels_w, pixels_h = struct.unpack(">II", data[16:24])
    if not pixels_w or not pixels_h:
        raise ValueError("invalid image dimensions")
    size = shutil.get_terminal_size(fallback=(width, 24))
    cell_w, cell_h = 8.0, 16.0
    try:
        # TIOCGWINSZ includes pixel dimensions on terminals that provide them.
        import fcntl
        import termios

        rows, cols, xpixels, ypixels = struct.unpack(
            "HHHH", fcntl.ioctl(output.fileno(), termios.TIOCGWINSZ, b"\0" * 8)
        )
        if rows and cols:
            size = os.terminal_size((cols, rows))
        if rows and cols and xpixels and ypixels:
            cell_w, cell_h = xpixels / cols, ypixels / rows
    except (ImportError, OSError, ValueError):
        pass
    columns = min(width, size.columns)
    rows = max(1, math.ceil(columns * cell_w * pixels_h / pixels_w / cell_h))
    max_rows = max(1, size.lines - 4)
    if rows > max_rows:
        rows = max_rows
        columns = max(
            1, min(columns, round(rows * cell_h * pixels_w / pixels_h / cell_w))
        )
    return columns, rows


def write_graphics(data: bytes, output: BinaryIO, protocol: str, width: int) -> None:
    columns, rows = image_size(data, width, output)
    encoded = base64.b64encode(data)
    if protocol == "kitty":
        # Reserve space first so the placement fits even near the screen bottom.
        output.write(b"\n" * rows + f"\x1b[{rows}A\r".encode())
        for index in range(0, len(encoded), 4096):
            chunk = encoded[index : index + 4096]
            more = int(index + 4096 < len(encoded))
            control = f"a=T,f=100,q=2,C=1,c={columns},r={rows}," if index == 0 else ""
            output.write(f"\x1b_G{control}m={more};".encode() + chunk + b"\x1b\\")
        output.write(f"\x1b[{rows}B\r\n".encode())
    else:
        output.write(
            f"\x1b]1337;MultipartFile=inline=1;size={len(data)};width={columns};height={rows};preserveAspectRatio=1\a".encode()
        )
        for index in range(0, len(encoded), 4096):
            output.write(b"\x1b]1337;FilePart=" + encoded[index : index + 4096] + b"\a")
        output.write(b"\x1b]1337;FileEnd\a\n")


def write_image(
    image: Image, output: BinaryIO, protocol: str | None, width: int, base_dir: Path
) -> None:
    # Strip control characters from labels and paths before terminal output.
    label = "".join(c for c in image.alt if c.isprintable()) or "Image"
    target = "".join(c for c in image.target if c.isprintable())
    output.write(f"[image: {label}] ({target})\n".encode())
    if protocol is None:
        return
    try:
        path = local_image_path(image.target, base_dir)
        if path is None:
            raise ValueError("remote images are not fetched")
        data = png_data(path, width)
        write_graphics(data, output, protocol, width)
    except (OSError, ValueError, subprocess.TimeoutExpired) as error:
        message = (
            "image conversion timed out"
            if isinstance(error, subprocess.TimeoutExpired)
            else str(error)
        )
        output.write(f"  Preview unavailable: {message}\n".encode())
    output.flush()
