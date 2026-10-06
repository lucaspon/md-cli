from __future__ import annotations

import unittest

from mdtex_cli.document import prepare_document

TABLE = r"""\begin{table}[H]
\footnotesize
\caption{Values \& Fees}
\begin{tabularx}{\textwidth}{l r X}
\toprule
\textbf{Metric} & \textbf{Mean} & \textbf{Details} \\
\midrule
Claim\_value & \pounds 142.9M & \texttt{pre\_2014} \\
\cellcolor{black!12}\textbf{Fees (29\%)} & £59.9M & $\mu + \sigma^2$ \\
\bottomrule
\end{tabularx}
\end{table}"""


class DocumentTests(unittest.TestCase):
    def test_tabularx_keeps_values_alignment_formatting_and_math(self) -> None:
        result, images = prepare_document(TABLE)
        self.assertFalse(images)
        self.assertIn("**Values & Fees**", result)
        self.assertIn("| :--- | ---: | :--- |", result)
        self.assertIn(r"| Claim\_value | £ 142.9M | `pre_2014` |", result)
        self.assertIn(r"| **Fees (29%)** | £59.9M | $\mu + \sigma^2$ |", result)
        self.assertNotIn(r"\begin", result)

    def test_nested_formatting_and_escaped_separators(self) -> None:
        source = r"""\begin{tabular}{l r}
\textbf{A \& \textit{B}} & Amount \\
\midrule
\texttt{name\_id} & $30{,}138$ \\
\end{tabular}"""
        result, _ = prepare_document(source)
        self.assertIn("| **A & *B*** | Amount |", result)
        self.assertIn(r"$30{,}138$", result)

    def test_spanning_headers_partial_rules_and_sparse_rows(self) -> None:
        source = r"""\begin{tabular}{l *{2}{r}}
 & \multicolumn{2}{c}{\textbf{Captive}} \\
\cmidrule(lr){2-3}
Metric & Yes & No \\
\cline{2-3}
Removed scenario \\
\end{tabular}"""
        result, _ = prepare_document(source)
        self.assertIn("|  | **Captive** |  |", result)
        self.assertIn("| Metric | Yes | No |", result)
        self.assertIn("| Removed scenario |  |  |", result)
        self.assertNotIn("2-3", result)

    def test_fixed_width_columns_and_footnotes(self) -> None:
        source = r"""\begin{table}[H]
\caption{Example}
\begin{tabular}{p{2.6cm} r}
Name & Count \\
One$^{1}$ & 2 \\
\end{tabular}
\vspace{4pt}\raggedright\footnotesize $^{1}$Footnote.
\end{table}"""
        result, _ = prepare_document(source)
        self.assertIn("| One$^{1}$ | 2 |", result)
        self.assertIn("$^{1}$Footnote.", result)

    def test_unsupported_tables_keep_source(self) -> None:
        for source in (
            r"\begin{tabular}{l r} A & B \\ \multirow{2}{*}{A} & B \\ \end{tabular}",
            r"\begin{tabular}{l} A & B \\ \end{tabular}",
            r"\begin{tabular}{unknown} A \\ \end{tabular}",
        ):
            with self.subTest(source=source):
                self.assertEqual(prepare_document(source)[0], source)

    def test_comments_and_optional_row_spacing(self) -> None:
        source = r"""\begin{tabular}{l r}
A & B \\[4pt] % heading
Rate & 29\% \\
\end{tabular}"""
        result, _ = prepare_document(source)
        self.assertIn("| Rate | 29% |", result)
        self.assertNotIn("heading", result)
        self.assertNotIn("4pt", result)

    def test_fenced_indented_and_inline_code_are_untouched(self) -> None:
        for source in (
            "```latex\n" + TABLE + "\n![Chart](x.pdf){ width=95% }\n\\newpage\n```\n",
            "~~~~md\n![Chart](x.pdf)\n\\newpage\n~~~~\n",
            "```md\n![Chart](x.pdf)\n",  # unclosed fence
            "`![Chart](x.pdf)` and ``\\newpage``",
            "    ![Chart](x.pdf)\n    \\newpage\n",
        ):
            with self.subTest(source=source[:40]):
                self.assertEqual(prepare_document(source), (source, {}))

    def test_markdown_images_keep_paths_and_remove_attributes(self) -> None:
        source = '![Chart](../outputs/chart.pdf){ width=95% }\n![Other](<image with spaces.png>)\n![Title](chart(1).png "Title")'
        result, images = prepare_document(source)
        self.assertEqual(
            [i.target for i in images.values()],
            ["../outputs/chart.pdf", "image with spaces.png", "chart(1).png"],
        )
        self.assertNotIn("width=95%", result)
        for marker in images:
            self.assertLess(len(marker), 20)
            self.assertIn("\n\n" + marker + "\n\n", result)

    def test_latex_figure_and_page_commands(self) -> None:
        source = r"""Before
\newpage
\begin{figure}[H]
\centering
\includegraphics[width=\textwidth]{../chart.pdf}
\caption{Fee \& Profit (29\%)}
\label{fig:fees}
\end{figure}
\vspace{0.5cm}
After"""
        result, images = prepare_document(source)
        self.assertEqual(len(images), 1)
        image = next(iter(images.values()))
        self.assertEqual(image.alt, "Fee & Profit (29%)")
        self.assertEqual(image.target, "../chart.pdf")
        self.assertNotIn(r"\newpage", result)
        self.assertNotIn(r"\vspace", result)
        self.assertIn("After", result)

    def test_multiple_graphics_figure_is_preserved(self) -> None:
        source = (
            r"\begin{figure}\includegraphics{a.png}\includegraphics{b.png}\end{figure}"
        )
        self.assertEqual(prepare_document(source), (source, {}))

    def test_normal_markdown_and_math_are_untouched(self) -> None:
        source = "# Heading\n\n| A | B |\n| --- | --- |\n| 1 | 2 |\n\nInline $x^2$.\n"
        self.assertEqual(prepare_document(source), (source, {}))

    def test_text_dashes_do_not_change_math_operators(self) -> None:
        source = r"\begin{tabular}{l l} Year & Math \\ 2009--2012 & $a--b \sim c$ \\ \end{tabular}"
        result, _ = prepare_document(source)
        self.assertIn(r"| 2009–2012 | $a--b \sim c$ |", result)


if __name__ == "__main__":
    unittest.main()
