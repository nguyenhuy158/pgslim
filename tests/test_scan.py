"""Tests for pgslim.scan: candidate bytea/text column detection + size estimation."""

from conftest import BIG_VALUE
from pgslim.scan import scan_candidate_columns


class TestScanCandidateColumns:
    def test_finds_bytea_and_text_columns_only(self, sample_dump):
        candidates = scan_candidate_columns(sample_dump)
        keys = {(c.table, c.column) for c in candidates}

        # The `id` integer columns must never show up — pgslim only targets bytea/text.
        assert keys == {("users", "avatar"), ("users", "name"), ("logs", "message")}
        assert all(c.col_type in ("bytea", "text") for c in candidates)

    def test_sorted_by_size_descending_with_largest_first(self, sample_dump):
        candidates = scan_candidate_columns(sample_dump)

        assert candidates[0].table == "users"
        assert candidates[0].column == "avatar"
        assert candidates[0].col_type == "bytea"
        assert candidates[0].estimated_bytes == len(BIG_VALUE)
        assert candidates[0].row_count == 2

        sizes = [c.estimated_bytes for c in candidates]
        assert sizes == sorted(sizes, reverse=True)

    def test_null_values_do_not_count_toward_size(self, sample_dump):
        candidates = scan_candidate_columns(sample_dump)
        avatar = next(c for c in candidates if c.column == "avatar")

        # Row 2's avatar is already \N: it should count toward row_count but not size.
        assert avatar.row_count == 2
        assert avatar.estimated_bytes == len(BIG_VALUE)

    def test_progress_callback_reaches_completion(self, sample_dump):
        calls = []
        scan_candidate_columns(sample_dump, progress_cb=lambda d, t: calls.append((d, t)))

        assert calls
        done, total = calls[-1]
        assert done == total
