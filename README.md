# md

Render Markdown and LaTeX together in the terminal.

`md` joins two focused tools into one command:

1. [`termtex`](https://github.com/doug/termtex) expands `$...$` and `$$...$$` math into terminal-friendly Unicode.
2. [`mdansi`](https://github.com/justinhuangai/mdansi) renders the remaining Markdown with headings, tables, code highlighting, links, and ANSI color.

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
    --no-truncate          Disable table-cell truncation
    --table-border STYLE   unicode, ascii, or none
    --color MODE           always (default), never, or auto
    --plain                Strip ANSI styling
    --doctor               Check external dependencies
```

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

The first release was uploaded directly to PyPI. To enable automatic publishing
for future `v*` GitHub tags, register a PyPI trusted publisher for project
`mdtex-cli`: owner `lucaspon`, repository `md-cli`, workflow `publish.yml`,
environment `pypi`. The workflow is included but cannot authenticate until
that registration is complete.

## License

MIT
