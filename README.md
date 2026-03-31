# pgslim 🐘

A simple Python CLI tool to reduce the size of a PostgreSQL dump by nullifying large `bytea` or `text` columns.

This is particularly useful when you've accidentally stored large files (like images, PDFs, or JSON responses) in your database and want to create a smaller dump for local development or staging.

## Installation

You can install `pgslim` directly from PyPI (once uploaded):

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

You can use `pgslim` in either **Interactive Mode** or **Command-Line Mode**.

### Interactive Mode (Recommended)

Simply run the tool with no arguments to start an interactive wizard. It will scan your current directory for `.sql` files, fast-scan the selected file for tables and columns, and provide searchable dropdown menus to make your selection.

```bash
pgslim
```

Alternatively, you can provide a directory path to scan for `.sql` files:

```bash
pgslim /path/to/dumps
```

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
| `-v`, `--verbose`| Enable verbose output to see detailed progress |

## How it works

The tool parses the `COPY` blocks in a PostgreSQL plain-text dump. It identifies the target table and the index of the specified column. For every row in that `COPY` block, it replaces the column value with `\N` (PostgreSQL's representation of `NULL`).

## License

MIT
