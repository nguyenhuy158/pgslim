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

Provide the input SQL file, the output SQL file, the table name, and the column you want to nullify.

```bash
pgslim -i dump_old.sql -o dump_new.sql -t farmlink_disbursement_bank_transaction -c attachment
```

### Arguments

| Flag | Long Flag | Description |
|---|---|---|
| `-i` | `--input` | Input SQL dump file (plain text format) |
| `-o` | `--output` | Output SQL dump file |
| `-t` | `--table` | Name of the table (e.g., `users`) |
| `-c` | `--column` | Name of the column to nullify (e.g., `attachment`) |

## How it works

The tool parses the `COPY` blocks in a PostgreSQL plain-text dump. It identifies the target table and the index of the specified column. For every row in that `COPY` block, it replaces the column value with `\N` (PostgreSQL's representation of `NULL`).

## License

MIT
