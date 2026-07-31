# pgslim 🐘

A simple Python CLI tool to reduce the size of a PostgreSQL dump by nullifying large `bytea` or `text` columns.

This is particularly useful when you've accidentally stored large files (like images, PDFs, or JSON responses) in your database and want to create a smaller dump for local development or staging.

## Installation

Run without installing, straight from PyPI with [uv](https://docs.astral.sh/uv/):

```bash
uvx pgslim
```

Or install it as a tool:

```bash
uv tool install pgslim
```

With pip:

```bash
pip install pgslim
```

Or from source:

```bash
git clone https://github.com/nguyenhuy158/pgslim
cd pgslim
pip install .
```

## Usage

You can use `pgslim` in **Interactive Mode**, **Command-Line Mode**, or the full-screen **Interactive UI**.

### Interactive Mode (Recommended)

Simply run the tool with no arguments to start an interactive wizard. It will scan your current directory for `.sql` files, fast-scan the selected file for tables and columns, and provide searchable dropdown menus to make your selection.

```bash
pgslim
```

Alternatively, you can provide a directory path to scan for `.sql` files:

```bash
pgslim /path/to/dumps
```

(One-off with uv: `uvx pgslim /path/to/dumps` — same arguments everywhere.)

### Command-Line Mode

For automation or quick usage, provide the input SQL file, the table name, and the column you want to nullify directly as positional arguments or named flags.

```bash
# Using positional arguments
pgslim dump_old.sql my_table large_column

# Using named flags
pgslim -i dump_old.sql -t my_table -c large_column -v
```

This will create a new file named `dump_old_slim.sql` (unless you specify a custom output with `-o`).

### Arguments

| Positional / Named Flag | Description |
|---|---|
| `input` / `-i`, `--input` | Input SQL dump file (plain text format) |
| `table` / `-t`, `--table` | Name of the table (e.g., `users`) |
| `column` / `-c`, `--column` | Name of the column to nullify (e.g., `attachment`) |

| Optional Flag | Description |
|---|---|
| `-o`, `--output` | Output SQL dump file (defaults to `<input>_slim.sql`) |
| `-z`, `--compress` | Compress output as gzip (`.gz`) |
| `-v`, `--verbose`| Enable verbose output to see detailed progress |
| `--version` | Show version and exit |
| `--ui` | Launch the full-screen interactive column picker (requires the `tui` extra) |

### Interactive UI

For dumps with many large columns spread across several tables, `--ui` opens a full-screen
picker built with [Textual](https://textual.textualize.io/): it scans the dump in the
background, lists every candidate `bytea`/`text` column with its estimated size, and lets
you select several at once before writing a single slimmed-down output file.

```bash
pgslim --ui dump.sql
```

| Key | Action |
|---|---|
| `Space` | Toggle the highlighted column for nullification |
| `a` | Select/deselect all candidate columns |
| `x` | Review the selection and run (opens a confirmation dialog) |
| `q` | Quit without writing anything |

Install the extra with:

```bash
uv tool install 'pgslim[tui]'
# or
pip install 'pgslim[tui]'
```

Without it installed, `--ui` prints an install hint and exits — the plain CLI and
Interactive Mode wizard above don't require Textual at all.

## How it works

The tool parses the `COPY` blocks in a PostgreSQL plain-text dump. It identifies the target table and the index of the specified column. For every row in that `COPY` block, it replaces the column value with `\N` (PostgreSQL's representation of `NULL`).

## License

MIT
