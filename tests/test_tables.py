from __future__ import annotations

import unittest

from mdtex_cli.tables import (
    glyphs,
    plain,
    reflow_table,
    visible_width,
    wrap_cell,
    wrap_tables,
)


def table(rows: list[list[str]], sizes: list[int], styled: bool = False) -> list[str]:
    paint = lambda text: "\x1b[2m" + text + "\x1b[0m" if styled else text
    lines = [paint("┌" + "┬".join("─" * (size + 2) for size in sizes) + "┐") + "\n"]
    for index, row in enumerate(rows):
        cells = [" " + value.ljust(size) + " " for value, size in zip(row, sizes)]
        vertical = paint("│")
        lines.append(vertical + vertical.join(cells) + vertical + "\n")
        if index == 0:
            lines.append(
                paint("├" + "┼".join("─" * (size + 2) for size in sizes) + "┤") + "\n"
            )
    lines.append(paint("└" + "┴".join("─" * (size + 2) for size in sizes) + "┘") + "\n")
    return lines


class WrapCellTests(unittest.TestCase):
    def test_wraps_at_words_without_ellipsis(self) -> None:
        self.assertEqual(
            wrap_cell("full text remains visible", 12),
            ["full text", "remains", "visible"],
        )

    def test_long_tokens_keep_all_characters(self) -> None:
        source = "customer_identifier_123456789"
        wrapped = wrap_cell(source, 8)
        self.assertEqual("".join(wrapped), source)
        self.assertTrue(all(visible_width(line) <= 8 for line in wrapped))

    def test_combining_cjk_and_emoji_clusters_stay_intact(self) -> None:
        source = "界界 e\u0301e\u0301 👩🏽‍💻 🇧🇷 1️⃣"
        wrapped = wrap_cell(source, 4)
        self.assertTrue(all(visible_width(line) <= 4 for line in wrapped))
        self.assertEqual("".join(wrapped).replace(" ", ""), source.replace(" ", ""))
        self.assertEqual(visible_width("界e\u0301👩🏽‍💻🇧🇷1️⃣"), 9)
        self.assertEqual([g.text for g in glyphs("👩🏽‍💻🇧🇷1️⃣")], ["👩🏽‍💻", "🇧🇷", "1️⃣"])

    def test_styles_close_and_resume_on_each_line(self) -> None:
        lines = wrap_cell(" \x1b[38;2;0;0;255m\x1b[1mone two three\x1b[0m ", 7)
        self.assertEqual(list(map(plain, lines)), ["one two", "three"])
        for line in lines:
            self.assertTrue(line.startswith("\x1b[38;2;0;0;255m\x1b[1m"))
            self.assertTrue(line.endswith("\x1b[0m"))
        self.assertEqual(wrap_cell("\x1b[1m   \x1b[0m", 10), [""])

    def test_osc_links_close_and_resume_on_each_line(self) -> None:
        link = "\x1b]8;;https://example.com\x1b\\"
        close = "\x1b]8;;\x1b\\"
        wrapped = wrap_cell(link + "full linked text" + close, 7)
        self.assertEqual(list(map(plain, wrapped)), ["full", "linked", "text"])
        self.assertTrue(
            all(line.startswith(link) and line.endswith(close) for line in wrapped)
        )


class TableTests(unittest.TestCase):
    def test_long_cells_keep_full_content_and_fit_width(self) -> None:
        source = table(
            [
                ["#", "Request", "Status"],
                ["1", "Every word of this long request must remain visible.", "Open"],
            ],
            [3, 15, 6],
        )
        wrapped = reflow_table(source, 40, "unicode")
        self.assertIsNotNone(wrapped)
        assert wrapped is not None
        self.assertTrue(all(visible_width(line.rstrip("\n")) <= 40 for line in wrapped))
        values = [
            line.split("│")[2].strip() for line in wrapped if line.startswith("│")
        ][1:]
        self.assertEqual(
            " ".join(values).strip(),
            "Every word of this long request must remain visible.",
        )

    def test_header_wraps_and_styles_do_not_leak(self) -> None:
        source = table(
            [["\x1b[1mA long header\x1b[0m", "Value"], ["Body", "42"]],
            [8, 5],
            styled=True,
        )
        wrapped = reflow_table(source, 20, "unicode")
        assert wrapped is not None
        text = "".join(wrapped)
        self.assertIn("\x1b[1m", text)
        self.assertIn("\x1b[2m", text)
        self.assertTrue(all(visible_width(line.rstrip("\n")) <= 20 for line in wrapped))
        self.assertIn("long", text)
        self.assertIn("header", text)

    def test_ascii_and_borderless_keep_full_content(self) -> None:
        source = table(
            [["Request", "Status"], ["Full request with many words", "Open"]], [12, 6]
        )
        for border in ("ascii", "none"):
            with self.subTest(border=border):
                wrapped = reflow_table(source, 25, border)
                assert wrapped is not None
                self.assertTrue(
                    all(visible_width(line.rstrip("\n")) <= 25 for line in wrapped)
                )
                self.assertNotIn("│", "".join(wrapped))
                self.assertIn("Open", "".join(wrapped))
                if border == "ascii":
                    self.assertTrue(wrapped[0].startswith("+"))
                else:
                    self.assertNotIn("+", "".join(wrapped))

    def test_alignment_is_preserved_for_right_and_center_columns(self) -> None:
        source = [
            "┌────────┬────────┐\n",
            "│ Amount │ Middle │\n",
            "├────────┼────────┤\n",
            "│      7 │  Yes   │\n",
            "└────────┴────────┘\n",
        ]
        wrapped = reflow_table(source, 30, "unicode")
        assert wrapped is not None
        self.assertIn("│      7 │  Yes   │\n", wrapped)

    def test_many_columns_stack_fields_if_they_cannot_fit(self) -> None:
        source = table(
            [
                ["Heading " + str(i) for i in range(15)],
                ["Cell " + str(i) for i in range(15)],
            ],
            [5] * 15,
        )
        wrapped = reflow_table(source, 20, "unicode")
        assert wrapped is not None
        self.assertTrue(all(visible_width(line.rstrip("\n")) <= 20 for line in wrapped))
        self.assertIn("Heading 14: Cell 14", "".join(wrapped))

    def test_indented_table_keeps_indent_and_fits_total_width(self) -> None:
        source = [
            "  " + line
            for line in table(
                [["Request"], ["Every word should be wrapped inside this list."]], [15]
            )
        ]
        wrapped = reflow_table(source, 25, "unicode")
        assert wrapped is not None
        self.assertTrue(all(line.startswith("  ") for line in wrapped))
        self.assertTrue(all(visible_width(line.rstrip("\n")) <= 25 for line in wrapped))

    def test_plain_literal_box_character_preserves_original_table(self) -> None:
        source = table([["Request"], ["Use │ as a literal symbol"]], [15])
        self.assertIsNone(reflow_table(source, 25, "unicode"))
        self.assertEqual(
            list(wrap_tables([line.encode() for line in source], 25, "unicode")),
            [line.encode() for line in source],
        )

    def test_stream_preserves_surrounding_text_multiple_tables_and_partial_table(
        self,
    ) -> None:
        source = table([["Request"], ["All text remains visible in this table"]], [15])
        data = ["Before\n", *source, "Between\n", *source, "After\n", *source[:2]]
        wrapped = b"".join(
            wrap_tables([line.encode() for line in data], 25, "unicode")
        ).decode()
        self.assertTrue(wrapped.startswith("Before\n┌"))
        self.assertIn("Between\n┌", wrapped)
        self.assertIn("After\n┌", wrapped)
        self.assertTrue(wrapped.endswith("".join(source[:2])))


if __name__ == "__main__":
    unittest.main()
