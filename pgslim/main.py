import re
import sys
import os
import argparse
import tarfile
import gzip
import io
from contextlib import contextmanager, ExitStack
from importlib.metadata import version, PackageNotFoundError
from tqdm import tqdm


def _is_tarfile(filepath):
    try:
        return tarfile.is_tarfile(filepath)
    except Exception:
        return False


def _find_sql_member(tf):
    members = [m for m in tf.getmembers() if m.isfile()]
    sql_members = [m for m in members if m.name.endswith(".sql")]
    if sql_members:
        return sql_members[0]
    if members:
        return members[0]
    raise ValueError("No files found in tar archive")


@contextmanager
def _open_sql_stream(filepath):
    """Context manager yielding (text_stream, size) — handles .tar, .tar.gz, .gz, plain .sql."""
    if _is_tarfile(filepath):
        tf = tarfile.open(filepath, "r:*")
        try:
            member = _find_sql_member(tf)
            raw = tf.extractfile(member)
            stream = io.TextIOWrapper(raw, encoding="utf-8", errors="replace")
            yield stream, member.size
        finally:
            tf.close()
    elif filepath.endswith(".gz"):
        f = gzip.open(filepath, "rt", encoding="utf-8", errors="replace")
        try:
            yield f, os.path.getsize(filepath)
        finally:
            f.close()
    else:
        size = os.path.getsize(filepath)
        f = open(filepath, "r", encoding="utf-8", errors="replace")
        try:
            yield f, size
        finally:
            f.close()


def _default_output(input_file, compress=False):
    for ext in (".sql.tar.gz", ".sql.tar.bz2", ".sql.tar.xz", ".sql.tar", ".sql.gz", ".sql"):
        if input_file.endswith(ext):
            base = input_file[: -len(ext)] + "_slim.sql"
            return base + ".gz" if compress else base
    base = input_file + "_slim.sql"
    return base + ".gz" if compress else base


def scan_sql_metadata(filepath):
    """Scans the SQL file to map tables to their columns based on COPY statements."""
    table_metadata = {}

    with _open_sql_stream(filepath) as (fin, total_size):
        with tqdm(
            total=total_size,
            unit="B",
            unit_scale=True,
            unit_divisor=1024,
            desc="Scanning Metadata",
        ) as pbar:
            batch_size = 0
            for line in fin:
                batch_size += len(line)
                if batch_size > 1024 * 1024:
                    pbar.update(batch_size)
                    batch_size = 0

                if line.startswith("COPY"):
                    # Format: COPY public.tablename (col1, col2) FROM stdin;
                    match = re.match(
                        r"COPY\s+(?:public\.)?([^\s]+)\s*\((.+?)\)\s+FROM", line
                    )
                    if match:
                        t_name = match.group(1).strip('"')
                        cols = [c.strip().strip('"') for c in match.group(2).split(",")]
                        table_metadata[t_name] = cols

            if batch_size > 0:
                pbar.update(batch_size)

            # Ensure progress bar reaches 100%
            if pbar.n < pbar.total:
                pbar.update(pbar.total - pbar.n)

    return table_metadata


def run_interactive_mode(search_dir="."):
    import glob
    from InquirerPy import inquirer

    # Handle path expansion (e.g., ~ or .)
    search_dir = os.path.expanduser(search_dir)
    search_dir = os.path.abspath(search_dir)

    patterns = ("*.sql", "*.sql.tar", "*.sql.tar.gz", "*.sql.tar.bz2", "*.sql.gz", "*.tar", "*.tar.gz")
    sql_files = []
    for pattern in patterns:
        sql_files.extend(glob.glob(os.path.join(search_dir, pattern)))
    sql_files = sorted(set(sql_files))
    if not sql_files:
        print(f"[!] No SQL files found in {search_dir}")
        return

    # Relative paths for nicer display
    rel_files = [os.path.relpath(f, search_dir) for f in sql_files]

    try:
        selected_rel_file = inquirer.fuzzy(
            message="Select an SQL file:",
            choices=rel_files,
        ).execute()

        if not selected_rel_file:
            return

        input_file = os.path.join(search_dir, selected_rel_file)

        print(f"[*] Scanning {input_file} for tables and columns...")
        metadata = scan_sql_metadata(input_file)

        if not metadata:
            print("[!] No COPY statements found in the file.")
            return

        tables = list(metadata.keys())

        table_name = inquirer.fuzzy(
            message="Select a table:",
            choices=tables,
        ).execute()

        if not table_name:
            return

        columns = metadata[table_name]

        column_name = inquirer.fuzzy(
            message="Select a column to nullify:",
            choices=columns,
        ).execute()

        if not column_name:
            return

        compress = inquirer.confirm(
            message="Compress output as .gz?",
            default=False,
        ).execute()

        default_output = _default_output(input_file, compress)

        output_file = inquirer.text(
            message="Output filename:",
            default=default_output,
        ).execute()

        if not output_file:
            output_file = default_output

        verbose = inquirer.confirm(
            message="Enable verbose output?",
            default=False,
        ).execute()

        process_file(input_file, output_file, table_name, column_name, verbose, compress)
    except (KeyboardInterrupt, EOFError):
        print("\n[!] Operation cancelled by user.")
        return
    except Exception as e:
        print(f"[!] An error occurred: {e}")


def process_file(input_file, output_file, table_name, column_name, verbose=False, compress=False):
    """Processes the SQL dump to nullify a specific column's value in COPY blocks."""
    in_copy_block = False
    col_index = -1
    processed_rows = 0
    line_count = 0

    if verbose:
        print(f"[*] Starting to process '{input_file}' -> '{output_file}'")

    with ExitStack() as stack:
        fin, total_size = stack.enter_context(_open_sql_stream(input_file))
        if compress:
            fout = stack.enter_context(gzip.open(output_file, "wt", encoding="utf-8"))
        else:
            fout = stack.enter_context(open(output_file, "w", encoding="utf-8"))
        pbar = stack.enter_context(tqdm(
            total=total_size,
            unit="B",
            unit_scale=True,
            unit_divisor=1024,
            desc="Processing",
        ))
        batch_size = 0
        for line in fin:
            line_count += 1

            # Update progress bar based on approximate byte size
            batch_size += len(line)
            if batch_size > 1024 * 1024:  # Update every 1MB to reduce overhead
                pbar.update(batch_size)
                batch_size = 0

            if verbose and line_count % 500000 == 0:
                pbar.write(f"[*] Processed {line_count:,} lines...")

            # Detect COPY statement
            # Format: COPY public.tablename (col1, col2, ...) FROM stdin;
            if line.startswith(f"COPY {table_name}") or line.startswith(
                f"COPY public.{table_name}"
            ):
                in_copy_block = True

                if verbose:
                    pbar.write(
                        f"[*] Found COPY block for table '{table_name}' at line {line_count}"
                    )

                # Parse column names from the COPY statement
                match = re.search(r"\((.+?)\)", line)
                if match:
                    cols = [c.strip().strip('"') for c in match.group(1).split(",")]
                    if column_name in cols:
                        col_index = cols.index(column_name)
                        pbar.write(
                            f"[*] Found '{column_name}' at index: {col_index} in table '{table_name}'"
                        )
                    else:
                        pbar.write(
                            f"[!] Warning: Column '{column_name}' not found in the COPY statement for table '{table_name}'"
                        )
                        col_index = -1

                fout.write(line)
                continue

            if in_copy_block:
                # End of COPY block is a line with just a dot and a newline: \.
                if line.strip() == r"\.":
                    in_copy_block = False
                    col_index = -1
                    if verbose:
                        pbar.write(f"[*] Exited COPY block at line {line_count}")
                    fout.write(line)
                    continue

                # Rows in COPY are tab-separated
                if col_index != -1:
                    cols = line.rstrip("\n").split("\t")
                    if len(cols) > col_index:
                        # Use \N for NULL in PostgreSQL COPY format
                        cols[col_index] = r"\N"
                        processed_rows += 1
                    fout.write("\t".join(cols) + "\n")
                else:
                    fout.write(line)
                continue

            fout.write(line)

        if batch_size > 0:
            pbar.update(batch_size)

        if pbar.n < pbar.total:
            pbar.update(pbar.total - pbar.n)

    print(
        f"[*] Done! Processed total {line_count:,} lines. Modified {processed_rows:,} rows."
    )


def main():
    parser = argparse.ArgumentParser(
        description="Reduce PostgreSQL dump size by nullifying large columns."
    )
    try:
        _version = version("pgslim")
    except PackageNotFoundError:
        _version = "unknown"
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {_version}",
    )

    # We define positional arguments as optional (nargs="?") so we can check if they are provided,
    # or fallback to the named arguments if they are used instead.
    parser.add_argument("pos_input", nargs="?", help="Input SQL dump file")
    parser.add_argument("pos_table", nargs="?", help="Target table name (e.g., users)")
    parser.add_argument(
        "pos_column", nargs="?", help="Target column name (e.g., attachment)"
    )

    parser.add_argument("-i", "--input", help="Input SQL dump file")
    parser.add_argument("-t", "--table", help="Target table name")
    parser.add_argument("-c", "--column", help="Target column name")
    parser.add_argument(
        "-o", "--output", help="Output SQL dump file (default: <input>_slim.sql)"
    )
    parser.add_argument(
        "-z",
        "--compress",
        action="store_true",
        help="Compress output as gzip (.gz)",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Enable verbose output to see progress",
    )

    args = parser.parse_args()

    # Determine values: favor named flags (-i, -t, -c) over positionals, then positionals
    input_file = args.input if args.input else args.pos_input
    table_name = args.table if args.table else args.pos_table
    column_name = args.column if args.column else args.pos_column
    output_file = args.output
    compress = args.compress
    verbose = args.verbose

    # Trigger interactive mode if no positional or named arguments for input, table, column are provided
    if not input_file and not table_name and not column_name:
        run_interactive_mode()
        return

    # Or if exactly one argument is provided and it's a directory
    if input_file and os.path.isdir(input_file) and not table_name and not column_name:
        run_interactive_mode(input_file)
        return

    # Validate that we have all required parameters
    if not input_file or not table_name or not column_name:
        parser.error("You must provide an input file, a table name, and a column name.")

    if not output_file:
        output_file = _default_output(input_file, compress)
    elif compress and not output_file.endswith(".gz"):
        output_file += ".gz"

    if output_file.endswith(".gz"):
        compress = True

    try:
        process_file(input_file, output_file, table_name, column_name, verbose, compress)
    except FileNotFoundError:
        print(f"[!] Error: File '{input_file}' not found.")
        sys.exit(1)
    except Exception as e:
        print(f"[!] An error occurred: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
