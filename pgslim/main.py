import re
import sys
import os
import argparse
from tqdm import tqdm


def scan_sql_metadata(filepath):
    """Scans the SQL file to map tables to their columns based on COPY statements."""
    table_metadata = {}
    total_size = os.path.getsize(filepath)

    with (
        open(filepath, "r", encoding="utf-8", errors="replace") as fin,
        tqdm(
            total=total_size,
            unit="B",
            unit_scale=True,
            unit_divisor=1024,
            desc="Scanning Metadata",
        ) as pbar,
    ):
        for line in fin:
            pbar.update(len(line.encode("utf-8", errors="replace")))
            if line.startswith("COPY"):
                # Format: COPY public.tablename (col1, col2) FROM stdin;
                match = re.match(
                    r"COPY\s+(?:public\.)?([^\s]+)\s*\((.+?)\)\s+FROM", line
                )
                if match:
                    t_name = match.group(1).strip('"')
                    cols = [c.strip().strip('"') for c in match.group(2).split(",")]
                    table_metadata[t_name] = cols

    return table_metadata


def run_interactive_mode(search_dir="."):
    import glob
    from InquirerPy import inquirer

    # Handle path expansion (e.g., ~ or .)
    search_dir = os.path.expanduser(search_dir)
    search_dir = os.path.abspath(search_dir)

    sql_files = glob.glob(os.path.join(search_dir, "*.sql"))
    if not sql_files:
        print(f"[!] No .sql files found in {search_dir}")
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

        default_output = (
            input_file.replace(".sql", "_slim.sql")
            if input_file.endswith(".sql")
            else input_file + "_slim"
        )

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

        process_file(input_file, output_file, table_name, column_name, verbose)
    except (KeyboardInterrupt, EOFError):
        print("\n[!] Operation cancelled by user.")
        return
    except Exception as e:
        print(f"[!] An error occurred: {e}")


def process_file(input_file, output_file, table_name, column_name, verbose=False):
    """Processes the SQL dump to nullify a specific column's value in COPY blocks."""
    in_copy_block = False
    col_index = -1
    processed_rows = 0
    line_count = 0

    total_size = os.path.getsize(input_file)

    if verbose:
        print(f"[*] Starting to process '{input_file}' -> '{output_file}'")

    # Ensure table_name is in a format matching the COPY statement (e.g., public.table_name)
    # The COPY line usually looks like: COPY public.farmlink_disbursement_bank_transaction (id, attachment, ...) FROM stdin;

    with (
        open(input_file, "r", encoding="utf-8", errors="replace") as fin,
        open(output_file, "w", encoding="utf-8") as fout,
        tqdm(
            total=total_size,
            unit="B",
            unit_scale=True,
            unit_divisor=1024,
            desc="Processing",
        ) as pbar,
    ):
        for line in fin:
            line_count += 1

            # Update progress bar based on the bytes size of the line
            pbar.update(len(line.encode("utf-8", errors="replace")))

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

    print(
        f"[*] Done! Processed total {line_count:,} lines. Modified {processed_rows:,} rows."
    )


def main():
    parser = argparse.ArgumentParser(
        description="Reduce PostgreSQL dump size by nullifying large columns."
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
        if input_file.endswith(".sql"):
            output_file = input_file.replace(".sql", "_slim.sql")
        else:
            output_file = input_file + "_slim"

    try:
        process_file(input_file, output_file, table_name, column_name, verbose)
    except FileNotFoundError:
        print(f"[!] Error: File '{input_file}' not found.")
        sys.exit(1)
    except Exception as e:
        print(f"[!] An error occurred: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
