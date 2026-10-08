# md

Render Markdown and LaTeX together in the terminal.

`md` joins two focused tools into one command:

1. [`termtex`](https://github.com/doug/termtex) expands `$...$` and `$$...$$` math into terminal-friendly Unicode.
2. [`mdansi`](https://github.com/justinhuangai/mdansi) renders the remaining Markdown with headings, tables, code highlighting, links, and ANSI color.

`md` also converts common LaTeX tables to Markdown and displays local chart
images in supported terminals.

## Install

Install the two renderers first:

```nu
^go install github.com/doug/termtex/cmd/termtex@latest
^cargo install mdansi
```

Then install `md` with uv:

```nu
^uv tool install mdtex-cli
```

PyPI is optional. Install directly from this GitHub repo instead:

```nu
^uv tool install 'git+https://github.com/lucaspon/md-cli'
```

Make sure Go's and uv's executable directories are on your `PATH` (usually
`~/go/bin` and `~/.local/bin`). If you used the old Nushell `alias md`, remove
it so the installed command takes precedence.

Check setup:

```nu
^md --doctor
```

## Usage

Render a file:

```nu
^md README.md
```

Render standard input:

```nu
"# Formula\n\nEuler: $e^{i\\pi}+1=0$" | ^md
```

Choose width and theme:

```nu
^md --width 100 --theme dracula notes.md
```

Headings at every level (`#` through `######`) render bold without visible
hash markers by default, even when output is piped. Use `--color auto` to honor terminal detection and
`NO_COLOR`, `--color never` to disable styling, or `--plain` for plain text.

Useful options:

```text
-w, --width N              Output width
-t, --theme NAME           mdansi theme
-n, --line-numbers         Show code line numbers
    --no-italic            Disable mathematical italic Unicode
    --ascii                Restrict math output to ASCII
    --no-wrap              Disable prose wrapping
    --no-highlight         Disable syntax highlighting
    --no-code-wrap         Disable code wrapping
    --no-table-wrap        Truncate table cells instead of wrapping
    --no-truncate          Preserve full unwrapped cells with --no-table-wrap
    --table-border STYLE   unicode, ascii, or none
    --color MODE           always (default), never, or auto
    --plain                Strip ANSI styling
    --images MODE          auto (default), never, kitty, or iterm
    --doctor               Check external dependencies
```

## Tables and images

Table cells wrap at word boundaries by default, printing their full contents
within the selected output width. Headers wrap too; short columns stay compact.
Long identifiers and URLs split across lines when needed. Rows gain separators
when cells span multiple lines. This applies to both Markdown and LaTeX tables,
including ASCII and borderless output. Tables with too many columns for the
available width stack fields vertically.

Use `--no-table-wrap` for the previous truncated display. Combine it with
`--no-truncate` to print full cells on a single line, even if rows exceed the
output width. `--no-wrap` controls prose independently of table wrapping.

Raw LaTeX `table`, `tabular`, and `tabularx` blocks render as terminal tables.
Captions, column alignment, common text formatting, math, escaped characters,
and `\multicolumn` are supported. Spanning cells expand to ordinary columns;
booktabs rules and print layout commands are removed. Unsupported tables stay
as source text. Code examples stay untouched.

Local Markdown images and single-image LaTeX `figure` blocks display inline
in Ghostty, Kitty, and iTerm2 3.5+. Paths resolve relative to the Markdown file;
stdin uses the current directory. Pandoc image attributes such as
`{ width=95% }` are removed; previews fit the terminal width and height.

PNG previews need no extra tools. PDF previews show the first page and use
`pdftoppm` from Poppler. Other image formats use ImageMagick. Install optional
converters on macOS:

```nu
^brew install poppler imagemagick
```

`--doctor` reports optional converters too. Missing files or converters produce
an explanatory placeholder and rendering continues. Remote images are never
downloaded.

Piped output, `--plain`, unsupported terminals, and sessions inside tmux or
screen show image captions and paths. Use `--images never` to disable previews.
`--images kitty` or `--images iterm` forces that graphics protocol, including
when stdout is redirected; `--plain` always disables graphics.

## Why external dependencies?

`md` stays small and dependency-free. `termtex` and `mdansi` remain independently upgradeable native executables. Missing tools produce a direct setup error.

## LaTeX limits

Terminal math uses Unicode, not a full TeX font layout engine. Simple inline notation renders best. Put complex expressions in display blocks. Avoid nested scripts when an equivalent form exists. For example:

```latex
\frac{\exp(\eta_j)}{\sum_{k\in\mathcal D}\exp(\eta_k)}
```

works better than nested powers such as `e^{\eta_{j'}}`.

## Development

```nu
^uv sync
^uv run python -m unittest discover -s tests
^uv build
```

## Releasing

Production releases publish to PyPI through the configured GitHub trusted
publisher (`publish.yml`, environment `pypi`). Bump the version in
`pyproject.toml`, `src/mdtex_cli/__init__.py`, and `uv.lock`, then push to `main`.
After CI passes, create and push the matching `v*` tag to trigger publication.

## License

MIT
