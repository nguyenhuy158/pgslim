"""Tests for pgslim.main.process_file_multi: nullifying several columns in one pass."""

from pathlib import Path

from conftest import BIG_VALUE
from pgslim.main import process_file_multi


class TestProcessFileMulti:
    def test_nullifies_only_selected_column(self, sample_dump, tmp_path):
        output_file = tmp_path / "dump_slim.sql"

        rows_modified, values_nulled = process_file_multi(
            sample_dump, str(output_file), [("users", "avatar")]
        )

        content = output_file.read_text(encoding="utf-8")
        assert BIG_VALUE not in content
        assert "1\tAlice\t\\N" in content
        assert "2\tBob\t\\N" in content  # was already NULL, untouched
        assert "1\tshort" in content  # logs table not targeted, left alone
        assert rows_modified == 1
        assert values_nulled == 1

    def test_multiple_targets_across_tables(self, sample_dump, tmp_path):
        output_file = tmp_path / "dump_slim.sql"

        rows_modified, values_nulled = process_file_multi(
            sample_dump, str(output_file), [("users", "avatar"), ("logs", "message")]
        )

        content = output_file.read_text(encoding="utf-8")
        assert BIG_VALUE not in content
        assert "1\tshort" not in content
        assert "1\t\\N" in content  # logs.message nulled
        assert rows_modified == 2
        assert values_nulled == 2

    def test_preserves_schema_and_untargeted_values(self, sample_dump, tmp_path):
        output_file = tmp_path / "dump_slim.sql"

        process_file_multi(sample_dump, str(output_file), [("users", "avatar")])

        content = output_file.read_text(encoding="utf-8")
        assert "CREATE TABLE public.users" in content
        assert "CREATE TABLE public.logs" in content
        assert "Alice" in content  # users.name is untouched

    def test_never_writes_to_the_input_file(self, sample_dump, tmp_path):
        output_file = tmp_path / "dump_slim.sql"
        original = Path(sample_dump).read_text(encoding="utf-8")

        process_file_multi(sample_dump, str(output_file), [("users", "avatar")])

        assert Path(sample_dump).read_text(encoding="utf-8") == original
