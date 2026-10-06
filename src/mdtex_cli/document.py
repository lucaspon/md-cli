"""Normalize the small subset of document LaTeX useful in a terminal.

This is deliberately not a TeX interpreter. Unsupported tables stay verbatim.
"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass

_ENVIRONMENT = re.compile(
    r"\\begin\{(?P<env>table\*?|tabularx?|figure\*?)\}.*?\\end\{(?P=env)\}",
    re.DOTALL,
)
_TABULAR = re.compile(r"\\begin\{(tabularx?)\}(?:\[[^\]]*\])?")
_IMAGE = re.compile(
    r"!\[(?P<alt>(?:\\.|[^\]\\])*)\]\("
    r"(?P<target><[^>\n]+>|(?:\\.|[^()\n]|\([^()\n]*\))+)"
    r"\)(?:[ \t]*\{[^}\n]*\})?"
)
_CODE = re.compile(
    r"(?m)^ {0,3}(?P<fence>`{3,}|~{3,})[^\n]*\n"
    r"(?s:.*?)(?:^ {0,3}(?P=fence)[`~]*[ \t]*(?:\n|$)|\Z)"
    r"|(?m:^(?:(?: {4}|\t)[^\n]*(?:\n|$))+)"
    r"|(?P<ticks>`+)(?!`)(?s:.*?)(?<!`)(?P=ticks)(?!`)",
)
_RULES = re.compile(
    r"\\(?:toprule|midrule|bottomrule|hline)\b(?:\[[^\]]*\])?"
    r"|\\(?:c?midrule|cline)(?:\([^)]*\))?\{[^}]*\}"
)


@dataclass(frozen=True)
class Image:
    alt: str
    target: str


def group(text: str, start: int) -> tuple[str, int]:
    """Read a balanced braced argument, including escaped braces."""
    while start < len(text) and text[start].isspace():
        start += 1
    if start >= len(text) or text[start] != "{":
        raise ValueError("expected braced argument")
    depth = 1
    index = start + 1
    while index < len(text):
        char = text[index]
        if char == "\\":
            index += 2
            continue
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return text[start + 1 : index], index + 1
        index += 1
    raise ValueError("unclosed argument")


def latex_text(text: str) -> str:
    """Keep math intact; convert common text commands to Markdown."""
    result: list[str] = []
    index = 0
    while index < len(text):
        math = re.match(r"\$\$?.*?\$\$?", text[index:], re.DOTALL)
        if math:
            result.append(math[0])
            index += math.end()
            continue
        if text[index] == "{":
            content, index = group(text, index)
            result.append(latex_text(content))
            continue
        if text[index] != "\\":
            if text.startswith("---", index):
                result.append("—")
                index += 3
            elif text.startswith("--", index):
                result.append("–")
                index += 2
            else:
                result.append(" " if text[index] == "~" else text[index])
                index += 1
            continue
        command = re.match(r"\\([a-zA-Z]+|.)", text[index:], re.DOTALL)
        if command is None:
            result.append("\\")
            index += 1
            continue
        name = command[1]
        index += command.end()
        if name in ("textbf", "textit", "emph", "texttt", "textrm", "textnormal"):
            content, index = group(text, index)
            content = latex_text(content)
            delimiter = {"textbf": "**", "textit": "*", "emph": "*", "texttt": "`"}.get(
                name, ""
            )
            if name == "texttt":
                content = re.sub(r"\\([_$#{}])", r"\1", content)
                delimiter = "`" * (
                    max((len(m[0]) for m in re.finditer(r"`+", content)), default=0) + 1
                )
            result.append(delimiter + content + delimiter)
        elif name == "cellcolor":
            if text[index : index + 1] == "[":
                index = text.index("]", index) + 1
            _, index = group(text, index)
        elif name in ("%", "&", "_", "$", "#", "{", "}"):
            # Escape Markdown punctuation and literal dollars before termtex.
            result.append("\\" + name if name in ("_", "$", "#", "{", "}") else name)
        elif name in (",", ";", " ", "quad", "qquad"):
            result.append(" ")
        elif name in (
            "pounds",
            "textsterling",
            "checkmark",
            "textbackslash",
            "textasciitilde",
        ):
            result.append(
                {
                    "pounds": "£",
                    "textsterling": "£",
                    "checkmark": "✓",
                    "textbackslash": "\\",
                    "textasciitilde": "~",
                }[name]
            )
        else:
            raise ValueError(f"unsupported text command: {name}")
    return " ".join("".join(result).split())


def columns(spec: str) -> list[str]:
    result: list[str] = []
    index = 0
    while index < len(spec):
        char = spec[index]
        index += 1
        if char in "lcrX":
            result.append(char)
        elif char in "pmb":
            _, index = group(spec, index)
            result.append("l")
        elif char in "@!><":
            _, index = group(spec, index)
        elif char == "*":
            count, index = group(spec, index)
            nested, index = group(spec, index)
            repeat = int(count)
            if not 1 <= repeat <= 100:
                raise ValueError("invalid column count")
            result.extend(columns(nested) * repeat)
        elif not char.isspace() and char != "|":
            raise ValueError("unsupported column type")
    if not result or len(result) > 100:
        raise ValueError("invalid column count")
    return result


def split_tex(text: str, separator: str) -> list[str]:
    """Split top-level row/cell separators, leaving escaped ones and math alone."""
    parts: list[str] = []
    start = index = depth = 0
    math = False
    while index < len(text):
        char = text[index]
        if depth == 0 and not math and text.startswith(separator, index):
            parts.append(text[start:index])
            index += len(separator)
            if separator == "\\\\":
                spacing = re.match(r"\[[^\]]*\]", text[index:])
                if spacing:
                    index += spacing.end()
            start = index
            continue
        if char == "\\":
            index += 2
            continue
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
        elif char == "$":
            math = not math
        index += 1
    parts.append(text[start:])
    return parts


def convert_table(block: str) -> str:
    match = _TABULAR.search(block)
    if match is None:
        raise ValueError("no tabular environment")
    index = match.end()
    if match[1] == "tabularx":
        _, index = group(block, index)  # print width
    spec, index = group(block, index)
    alignments = columns(spec)
    end = block.index(r"\end{" + match[1] + "}", index)
    body = re.sub(r"(?<!\\)%[^\n]*", "", block[index:end])
    body = _RULES.sub("", body)
    rows: list[list[str]] = []
    for row in split_tex(body, r"\\"):
        if not row.strip():
            continue
        cells: list[str] = []
        for cell in split_tex(row, "&"):
            cell = cell.strip()
            span = 1
            if cell.startswith(r"\multicolumn"):
                count, pos = group(cell, len(r"\multicolumn"))
                _, pos = group(cell, pos)
                cell_text, pos = group(cell, pos)
                if cell[pos:].strip():
                    raise ValueError("extra content after span")
                cell = cell_text
                span = int(count)
                if not 1 <= span <= len(alignments):
                    raise ValueError("invalid span")
            cells.append(latex_text(cell).replace("|", r"\|"))
            cells.extend([""] * (span - 1))
        if len(cells) > len(alignments):
            raise ValueError("row exceeds column count")
        cells.extend([""] * (len(alignments) - len(cells)))
        rows.append(cells)
    if not rows:
        raise ValueError("empty table")
    caption = re.search(r"\\caption(?:\[[^\]]*\])?", block)
    title = latex_text(group(block, caption.end())[0]) if caption else ""
    lines = ["**" + title + "**", ""] if title else []
    lines.append("| " + " | ".join(rows[0]) + " |")
    lines.append(
        "| "
        + " | ".join({"r": "---:", "c": ":---:"}.get(a, ":---") for a in alignments)
        + " |"
    )
    lines.extend("| " + " | ".join(row) + " |" for row in rows[1:])
    # Preserve text following the tabular, such as table footnotes.
    tail = block[end + len(r"\end{" + match[1] + "}") :]
    tail = re.sub(r"\\end\{table\*?\}|\\label\{[^}]*\}", "", tail)
    tail = re.sub(r"\\vspace\*?\{[^}]*\}|\\(?:raggedright|footnotesize)\b", "", tail)
    if tail.strip():
        # Captions after the tabular were already included above.
        if caption and caption.start() > end:
            _, pos = group(block, caption.end())
            tail = block[pos:]
            tail = re.sub(r"\\end\{table\*?\}|\\label\{[^}]*\}", "", tail)
        if tail.strip():
            lines.extend(["", latex_text(tail)])
    return "\n\n" + "\n".join(lines) + "\n\n"


def prepare_document(text: str) -> tuple[str, dict[str, Image]]:
    """Convert tables and replace figures with opaque, standalone markers."""
    prefix = "MDI" + uuid.uuid4().hex[:8]
    protected: dict[str, str] = {}

    def protect(match: re.Match[str]) -> str:
        key = prefix + "CODE" + str(len(protected))
        protected[key] = match[0]
        return key

    text = _CODE.sub(protect, text)
    images: dict[str, Image] = {}

    def image(alt: str, target: str) -> str:
        key = prefix + str(len(images))
        images[key] = Image(alt, target)
        return "\n\n" + key + "\n\n"

    def environment(match: re.Match[str]) -> str:
        block = match[0]
        try:
            if not match["env"].startswith("figure"):
                return convert_table(block)
            matches = list(re.finditer(r"\\includegraphics(?:\[[^\]]*\])?", block))
            if len(matches) != 1:
                return block
            graphics = matches[0]
            target, _ = group(block, graphics.end())
            caption = re.search(r"\\caption(?:\[[^\]]*\])?", block)
            alt = latex_text(group(block, caption.end())[0]) if caption else ""
            return image(alt, target)
        except (ValueError, IndexError):
            return block

    text = _ENVIRONMENT.sub(environment, text)

    def markdown_image(match: re.Match[str]) -> str:
        target = match["target"].strip()
        if target.startswith("<"):
            target = target[1 : target.index(">")]
        else:
            target = re.sub(r"""\s+["'][^\n]*["']$""", "", target)
        return image(match["alt"], re.sub(r"\\([ ()])", r"\1", target))

    text = _IMAGE.sub(markdown_image, text)
    text = re.sub(r"(?m)^\s*\\(?:newpage|clearpage|pagebreak)\s*$", "", text)
    text = re.sub(r"(?m)^\s*\\vspace\*?\{[^}]*\}\s*$", "", text)
    for key, value in protected.items():
        text = text.replace(key, value)
    return text, images
