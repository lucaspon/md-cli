"""Reflow mdansi's untruncated tables without losing text or terminal styles."""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterable, Iterator, Sequence
from dataclasses import dataclass

_SGR = r"\x1b\[[0-9;]*m"
_ESCAPE = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]|\x1b\][^\x1b\x07]*(?:\x07|\x1b\\)")
_TOKENS = re.compile(_ESCAPE.pattern + r"|.", re.DOTALL)
_TOP = re.compile(
    rf"(?P<prefix>.*?)(?P<style>(?:{_SGR})*)┌(?P<segments>─+(?:┬─+)*)┐(?P<reset>(?:{_SGR})*)\n?$"
)
_RESET = "\x1b[0m"
_CLOSE_LINK = "\x1b]8;;\x1b\\"


def plain(text: str) -> str:
    return _ESCAPE.sub("", text)


@dataclass
class Glyph:
    text: str
    width: int
    style: str
    link: str


def glyphs(text: str) -> list[Glyph]:
    result: list[Glyph] = []
    style = link = ""
    for match in _TOKENS.finditer(text):
        token = match[0]
        if token.startswith("\x1b["):
            if token.endswith("m"):
                if token in ("\x1b[m", _RESET):
                    style = ""
                elif token.startswith("\x1b[0;"):
                    style = token
                else:
                    style += token
            continue
        if token.startswith("\x1b]"):
            if token.startswith("\x1b]8;"):
                payload = token[4 : -1 if token.endswith("\x07") else -2]
                link = token if payload.partition(";")[2] else ""
            continue
        zero_width = unicodedata.category(token).startswith("M") or token == "\u200d"
        modifier = "\U0001f3fb" <= token <= "\U0001f3ff"
        regional = "\U0001f1e6" <= token <= "\U0001f1ff"
        width = (
            0
            if zero_width
            else (2 if unicodedata.east_asian_width(token) in "WF" else 1)
        )
        joins_previous = bool(result) and (
            zero_width
            or modifier
            or result[-1].text.endswith("\u200d")
            or (
                regional
                and len(result[-1].text) == 1
                and "\U0001f1e6" <= result[-1].text <= "\U0001f1ff"
            )
        )
        if joins_previous:
            result[-1].text += token
            result[-1].width = max(result[-1].width, width)
            if token in ("\ufe0f", "\u20e3") or regional:
                result[-1].width = 2
        else:
            result.append(Glyph(token, width, style, link))
    return result


def visible_width(text: str) -> int:
    return sum(g.width for g in glyphs(text))


def styled_text(units: Sequence[Glyph]) -> str:
    result: list[str] = []
    style = link = ""
    for unit in units:
        if unit.link != link:
            if link:
                result.append(_CLOSE_LINK)
            if unit.link:
                result.append(unit.link)
            link = unit.link
        if unit.style != style:
            if style:
                result.append(_RESET)
            if unit.style:
                result.append(unit.style)
            style = unit.style
        result.append(unit.text)
    if link:
        result.append(_CLOSE_LINK)
    if style:
        result.append(_RESET)
    return "".join(result)


def trim(units: list[Glyph]) -> list[Glyph]:
    start, end = 0, len(units)
    while start < end and units[start].text.isspace():
        start += 1
    while end > start and units[end - 1].text.isspace():
        end -= 1
    return units[start:end]


def wrap_cell(text: str, width: int) -> list[str]:
    units = trim(glyphs(text))
    lines: list[str] = []
    start = 0
    while start < len(units):
        end, used, space = start, 0, None
        while end < len(units) and used + units[end].width <= width:
            if units[end].text.isspace():
                space = end
            used += units[end].width
            end += 1
        if end == start:
            end += 1  # Keep even a glyph wider than the requested cell.
        elif end < len(units) and not units[end].text.isspace() and space is not None:
            end = space
        lines.append(styled_text(trim(units[start:end])))
        start = end
        while start < len(units) and units[start].text.isspace():
            start += 1
    return lines or [""]


def column_widths(rows: list[list[str]], budget: int) -> list[int] | None:
    columns = list(zip(*rows))
    minimum = [
        max(1, max((g.width for cell in cells for g in glyphs(cell)), default=1))
        for cells in columns
    ]
    if sum(minimum) > budget:
        return None
    widths = [
        max(low, min(budget, max(visible_width(plain(cell).strip()) for cell in cells)))
        for cells, low in zip(columns, minimum)
    ]
    while sum(widths) > budget:
        candidates = [i for i in range(len(widths)) if widths[i] > minimum[i]]
        index = max(candidates, key=lambda i: widths[i])
        widths[index] -= 1
    return widths


def alignments(rows: list[list[str]]) -> list[str]:
    result: list[str] = []
    for cells in zip(*rows):
        alignment = "left"
        for cell in cells:
            text = plain(cell)[1:-1]  # mdansi's one-space cell padding
            if not text.strip():
                continue
            left = len(text) - len(text.lstrip())
            right = len(text) - len(text.rstrip())
            if left and not right:
                alignment = "right"
                break
            if left and right:
                alignment = "center"
                break
        result.append(alignment)
    return result


def reflow_table(lines: list[str], width: int, border: str) -> list[str] | None:
    top = _TOP.fullmatch(lines[0])
    if top is None:
        return None
    prefix, style, reset = top["prefix"], top["style"], top["reset"]
    count = len(top["segments"].split("┬"))
    delimiter = style + "│" + reset
    rows: list[list[str]] = []
    for line in lines[1:-1]:
        if not line.startswith(prefix):
            return None
        body = line[len(prefix) :].rstrip("\r\n")
        if re.fullmatch(r"├─+(?:┼─+)*┤", plain(body)):
            continue
        cells = body.split(delimiter)
        if len(cells) != count + 2 or cells[0] or cells[-1]:
            # Ambiguous literal border characters: retain the full original text.
            return None
        rows.append(cells[1:-1])
    if not rows:
        return None
    available = max(1, width - visible_width(prefix))
    padding = 0 if border == "none" else 1
    overhead = 2 * (count - 1) if border == "none" else count + 1 + 2 * padding * count
    widths = column_widths(rows, available - overhead)
    if widths is None and padding:
        padding = 0
        overhead = count + 1
        widths = column_widths(rows, available - overhead)
    if widths is None:
        # Too many columns for a horizontal table. Stack fields within each row.
        result: list[str] = []
        for row in rows[1:] or rows[:1]:
            for heading, cell in zip(rows[0], row):
                label = styled_text(trim(glyphs(heading)))
                value = styled_text(trim(glyphs(cell)))
                result.extend(
                    prefix + line + "\n"
                    for line in wrap_cell(label + ": " + value, available)
                )
            result.append(prefix + "\n")
        return result
    alignment = alignments(rows)
    wrapped = [
        [wrap_cell(cell, cell_width) for cell, cell_width in zip(row, widths)]
        for row in rows
    ]
    heights = [max(map(len, row)) for row in wrapped]
    result = []

    def paint(text: str) -> str:
        return style + text + reset

    def rule(position: str) -> str:
        if border == "none":
            return prefix + paint("  ".join("─" * w for w in widths)) + "\n"
        left, middle, right, horizontal = (
            ("+", "+", "+", "-")
            if border == "ascii"
            else {
                "top": ("┌", "┬", "┐", "─"),
                "middle": ("├", "┼", "┤", "─"),
                "bottom": ("└", "┴", "┘", "─"),
            }[position]
        )
        return (
            prefix
            + paint(
                left
                + middle.join(horizontal * (w + 2 * padding) for w in widths)
                + right
            )
            + "\n"
        )

    if border != "none":
        result.append(rule("top"))
    for index, row in enumerate(wrapped):
        for line_index in range(heights[index]):
            cells = []
            for cell, cell_width, align in zip(row, widths, alignment):
                value = cell[line_index] if line_index < len(cell) else ""
                extra = max(0, cell_width - visible_width(value))
                left = (
                    extra
                    if align == "right"
                    else extra // 2
                    if align == "center"
                    else 0
                )
                cells.append(
                    " " * (padding + left) + value + " " * (padding + extra - left)
                )
            vertical = paint("|" if border == "ascii" else "│")
            line = (
                "  ".join(cells)
                if border == "none"
                else vertical + vertical.join(cells) + vertical
            )
            result.append(prefix + line + "\n")
        if index == 0 or (index < len(wrapped) - 1 and max(heights) > 1):
            result.append(rule("middle"))
    if border != "none":
        result.append(rule("bottom"))
    return result


def wrap_tables(lines: Iterable[bytes], width: int, border: str) -> Iterator[bytes]:
    pending: list[str] = []
    top: re.Match[str] | None = None
    for raw in lines:
        line = raw.decode("utf-8")
        if not pending:
            top = _TOP.fullmatch(line)
            if top is None or re.fullmatch(r"[ │]*", plain(top["prefix"])) is None:
                yield raw
                continue
        pending.append(line)
        assert top is not None
        if (
            plain(line)
            == plain(top["prefix"]) + "└" + top["segments"].replace("┬", "┴") + "┘\n"
        ):
            rendered = reflow_table(pending, width, border)
            yield from (item.encode("utf-8") for item in rendered or pending)
            pending = []
        elif len(pending) > 1 and not line.startswith(top["prefix"]):
            yield from (item.encode("utf-8") for item in pending)
            pending = []
    yield from (item.encode("utf-8") for item in pending)
