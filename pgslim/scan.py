"""Shared dump-scanning logic: detect candidate bytea/text columns and estimate their size.

Used by the optional Textual UI (`pgslim/tui.py`) to build its column picker table. Kept
separate from `main.py` so the (potentially slow) full-content size scan doesn't run as
part of the lightweight `scan_sql_metadata` used by the plain interactive wizard.
"""

import re
from collections import defaultdict
from dataclasses import dataclass

from .main import _open_sql_stream, parse_copy_header

# Column types pgslim targets for nullification (see README: "large bytea or text columns").
_CANDIDATE_TYPES = {"bytea", "text"}

_CREATE_TABLE_RE = re.compile(
    r'^CREATE TABLE\s+(?:IF NOT EXISTS\s+)?(?:public\.)?"?([^\s"(]+)"?\s*\(\s*$'
)
_SKIP_LINE_PREFIXES = (
    "CONSTRAINT",
    "PRIMARY KEY",
    "UNIQUE",
    "FOREIGN KEY",
    "CHECK",
    "EXCLUDE",
)
_TYPE_STOP_WORDS = {
    "NOT",
    "NULL",
    "DEFAULT",
    "COLLATE",
    "CHECK",
    "PRIMARY",
    "REFERENCES",
    "UNIQUE",
    "GENERATED",
    "CONSTRAINT",
}


@dataclass
class ColumnCandidate:
    """A bytea/text column found while scanning a dump, with an estimated on-disk size."""

    table: str
    column: str
    col_type: str
    estimated_bytes: int = 0
    row_count: int = 0

    @property
    def key(self):
        return (self.table, self.column)


def _parse_column_def(line):
    """Parses one line of a CREATE TABLE block into (column_name, type), or None."""
    stripped = line.strip().rstrip(",")
    if not stripped or stripped.startswith(_SKIP_LINE_PREFIXES):
        return None
    tokens = stripped.split()
    if len(tokens) < 2:
        return None
    col_name = tokens[0].strip('"')
    type_tokens = []
    for tok in tokens[1:]:
        if tok.upper() in _TYPE_STOP_WORDS:
            break
        type_tokens.append(tok)
    if not type_tokens:
        return None
    return col_name, " ".join(type_tokens).lower()


def scan_candidate_columns(filepath, progress_cb=None):
    """Scans a dump for bytea/text columns and estimates each one's total data size.

    Reads the `CREATE TABLE` blocks first to learn column types, then walks every `COPY`
    block once, summing the raw field length of each bytea/text column. This is a full
    read of the dump (unlike the header-only `scan_sql_metadata`), so callers running it
    on large files should do so off the main thread, and may pass `progress_cb(bytes_read,
    total_bytes)` to report progress as the scan proceeds.

    Returns a list of ColumnCandidate, sorted by estimated size (largest first).
    """
    column_types = defaultdict(dict)  # table -> {column: type}
    sizes = defaultdict(int)  # (table, column) -> estimated bytes
    row_counts = defaultdict(int)  # (table, column) -> rows seen

    in_create_table = None
    in_copy_block = False
    copy_table = None
    copy_columns = []

    with _open_sql_stream(filepath) as (fin, total_size):
        bytes_read = 0
        last_report = 0
        for line in fin:
            bytes_read += len(line)
            if progress_cb and bytes_read - last_report > 1024 * 1024:
                progress_cb(bytes_read, total_size)
                last_report = bytes_read

            if in_create_table is not None:
                if line.rstrip() == ");":
                    in_create_table = None
                    continue
                parsed = _parse_column_def(line)
                if parsed:
                    col_name, col_type = parsed
                    column_types[in_create_table][col_name] = col_type
                continue

            if in_copy_block:
                if line.strip() == r"\.":
                    in_copy_block = False
                    copy_table = None
                    copy_columns = []
                    continue
                fields = line.rstrip("\n").split("\t")
                for idx, col_name in enumerate(copy_columns):
                    col_type = column_types.get(copy_table, {}).get(col_name)
                    if col_type not in _CANDIDATE_TYPES or idx >= len(fields):
                        continue
                    key = (copy_table, col_name)
                    value = fields[idx]
                    row_counts[key] += 1
                    if value != r"\N":
                        sizes[key] += len(value)
                continue

            table_match = _CREATE_TABLE_RE.match(line)
            if table_match:
                in_create_table = table_match.group(1).strip('"')
                continue

            if line.startswith("COPY"):
                parsed = parse_copy_header(line)
                if parsed:
                    table_name, cols = parsed
                    has_candidate = any(
                        column_types.get(table_name, {}).get(c) in _CANDIDATE_TYPES
                        for c in cols
                    )
                    if has_candidate:
                        in_copy_block = True
                        copy_table = table_name
                        copy_columns = cols
                continue

        if progress_cb:
            progress_cb(total_size, total_size)

    candidates = [
        ColumnCandidate(
            table=table,
            column=column,
            col_type=column_types.get(table, {}).get(column, "?"),
            estimated_bytes=size,
            row_count=row_counts.get((table, column), 0),
        )
        for (table, column), size in sizes.items()
        if size > 0
    ]
    candidates.sort(key=lambda c: c.estimated_bytes, reverse=True)
    return candidates
