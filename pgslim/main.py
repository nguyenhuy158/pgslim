import re
import sys
import argparse


def process_file(input_file, output_file, table_name, column_name):
    """Processes the SQL dump to nullify a specific column's value in COPY blocks."""
    in_copy_block = False
    col_index = -1
    processed_rows = 0

    # Ensure table_name is in a format matching the COPY statement (e.g., public.table_name)
    # The COPY line usually looks like: COPY public.farmlink_disbursement_bank_transaction (id, attachment, ...) FROM stdin;

    with (
        open(input_file, "r", encoding="utf-8", errors="replace") as fin,
        open(output_file, "w", encoding="utf-8") as fout,
    ):
        for line in fin:
            # Detect COPY statement
            # Format: COPY public.tablename (col1, col2, ...) FROM stdin;
            if line.startswith(f"COPY {table_name}") or line.startswith(
                f"COPY public.{table_name}"
            ):
                in_copy_block = True

                # Parse column names from the COPY statement
                match = re.search(r"\((.+?)\)", line)
                if match:
                    cols = [c.strip().strip('"') for c in match.group(1).split(",")]
                    if column_name in cols:
                        col_index = cols.index(column_name)
                        print(
                            f"[*] Found '{column_name}' at index: {col_index} in table '{table_name}'"
                        )
                    else:
                        print(
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

    print(f"[*] Done! Processed {processed_rows} rows.")


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

    args = parser.parse_args()

    # Determine values: favor named flags (-i, -t, -c) over positionals, then positionals
    input_file = args.input if args.input else args.pos_input
    table_name = args.table if args.table else args.pos_table
    column_name = args.column if args.column else args.pos_column
    output_file = args.output

    # Validate that we have all required parameters
    if not input_file or not table_name or not column_name:
        parser.error("You must provide an input file, a table name, and a column name.")

    if not output_file:
        if input_file.endswith(".sql"):
            output_file = input_file.replace(".sql", "_slim.sql")
        else:
            output_file = input_file + "_slim"

    try:
        process_file(input_file, output_file, table_name, column_name)
    except FileNotFoundError:
        print(f"[!] Error: File '{input_file}' not found.")
        sys.exit(1)
    except Exception as e:
        print(f"[!] An error occurred: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
