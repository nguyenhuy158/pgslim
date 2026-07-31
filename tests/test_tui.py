"""Headless smoke tests for the Textual column picker, driven via `App.run_test()`.

Everything here runs against temp files created by the `sample_dump` fixture
(tests/conftest.py) — nothing touches real dumps.
"""

from conftest import BIG_VALUE
from pgslim.tui import ColumnPickerApp, ConfirmScreen

pytest_plugins = ()


async def _wait_for_scan(app, pilot, attempts=100):
    for _ in range(attempts):
        if app._candidates:
            return
        await pilot.pause(0.05)
    raise AssertionError("scan worker did not populate candidates in time")


class TestColumnPickerAppScan:
    async def test_scan_renders_candidate_rows(self, sample_dump, tmp_path):
        app = ColumnPickerApp(sample_dump, str(tmp_path / "dump_slim.sql"))
        async with app.run_test() as pilot:
            await _wait_for_scan(app, pilot)

            table = app.query_one("#columns-table")
            assert table.row_count == 3
            # Largest candidate (users.avatar) sorts first.
            assert app._candidates[0].table == "users"
            assert app._candidates[0].column == "avatar"
            assert app.sub_title.startswith("0 columns selected")


class TestColumnPickerAppSelection:
    async def test_space_toggles_the_highlighted_row(self, sample_dump, tmp_path):
        app = ColumnPickerApp(sample_dump, str(tmp_path / "dump_slim.sql"))
        async with app.run_test() as pilot:
            await _wait_for_scan(app, pilot)

            await pilot.press("space")
            assert app._selected == {0}
            assert app.sub_title.startswith("1 columns selected")

            await pilot.press("space")
            assert app._selected == set()

    async def test_select_all_toggles_every_row(self, sample_dump, tmp_path):
        app = ColumnPickerApp(sample_dump, str(tmp_path / "dump_slim.sql"))
        async with app.run_test() as pilot:
            await _wait_for_scan(app, pilot)

            await pilot.press("a")
            assert app._selected == set(range(len(app._candidates)))

            await pilot.press("a")
            assert app._selected == set()


class TestColumnPickerAppRunFlow:
    async def test_run_opens_confirm_modal_and_cancel_closes_it(self, sample_dump, tmp_path):
        app = ColumnPickerApp(sample_dump, str(tmp_path / "dump_slim.sql"))
        async with app.run_test() as pilot:
            await _wait_for_scan(app, pilot)

            await pilot.press("space")
            await pilot.press("x")
            await pilot.pause()
            assert isinstance(app.screen, ConfirmScreen)

            await pilot.press("n")
            await pilot.pause()
            assert not isinstance(app.screen, ConfirmScreen)
            assert app.result is None

    async def test_run_without_selection_does_not_open_modal(self, sample_dump, tmp_path):
        app = ColumnPickerApp(sample_dump, str(tmp_path / "dump_slim.sql"))
        async with app.run_test() as pilot:
            await _wait_for_scan(app, pilot)

            await pilot.press("x")
            await pilot.pause()
            assert not isinstance(app.screen, ConfirmScreen)

    async def test_confirm_writes_slim_output_file(self, sample_dump, tmp_path):
        output_file = tmp_path / "dump_slim.sql"
        app = ColumnPickerApp(sample_dump, str(output_file))
        async with app.run_test() as pilot:
            await _wait_for_scan(app, pilot)

            # Top candidate is users.avatar (the big value) — select and run it.
            await pilot.press("space")
            await pilot.press("x")
            await pilot.pause()
            await pilot.press("y")

            for _ in range(100):
                if app.result is not None:
                    break
                await pilot.pause(0.05)
            else:
                raise AssertionError("nullify worker did not finish in time")

        assert output_file.exists()
        content = output_file.read_text()
        assert BIG_VALUE not in content
        assert "1\tAlice\t\\N" in content
        assert "1\tshort" in content  # logs table untouched

        assert app.result.columns == 1
        assert app.result.rows_modified == 1
