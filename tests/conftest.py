"""Shared pytest fixtures: a small synthetic pg_dump used across pgslim's test suite."""

import pytest

# A stand-in for a large stored bytea value (4000 chars) — big enough that it always
# sorts above the small text columns in the candidate list.
BIG_VALUE = "deadbeef" * 500

SAMPLE_DUMP = (
    "SET statement_timeout = 0;\n"
    "\n"
    "CREATE TABLE public.users (\n"
    "    id integer NOT NULL,\n"
    "    name text,\n"
    "    avatar bytea\n"
    ");\n"
    "\n"
    "\n"
    "CREATE TABLE public.logs (\n"
    "    id integer NOT NULL,\n"
    "    message text\n"
    ");\n"
    "\n"
    "\n"
    "COPY public.users (id, name, avatar) FROM stdin;\n"
    f"1\tAlice\t{BIG_VALUE}\n"
    "2\tBob\t\\N\n"
    "\\.\n"
    "\n"
    "\n"
    "COPY public.logs (id, message) FROM stdin;\n"
    "1\tshort\n"
    "\\.\n"
)


@pytest.fixture
def sample_dump(tmp_path):
    """Writes SAMPLE_DUMP to a temp file and returns its path.

    Two tables: `users` (a big `avatar` bytea value, a small `name` text value, and a
    non-candidate `id` integer) and `logs` (a small `message` text value). Gives the
    scanner/nullifier tests both a clear "largest candidate" and a second table to prove
    multi-table targeting doesn't cross-contaminate.
    """
    dump_file = tmp_path / "dump.sql"
    dump_file.write_text(SAMPLE_DUMP)
    return str(dump_file)
