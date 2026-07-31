"""Full-screen interactive column picker for pgslim, built on Textual.

Launched by `pgslim --ui <dump>`. Requires the optional `textual` dependency: install
with `pip install 'pgslim[tui]'` (or `uv tool install 'pgslim[tui]'`). Import this module
lazily — never at package import time — so the plain CLI keeps working without textual
installed. See `pgslim.main.run_ui_mode` for the lazy-import + install-hint wiring.
"""

from dataclasses import dataclass

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.coordinate import Coordinate
from textual.screen import ModalScreen
from textual.widgets import Button, DataTable, Footer, Header, Label

from .main import process_file_multi
from .scan import scan_candidate_columns


def _fmt_bytes(n):
    """Formats a byte count as a short human-readable string, e.g. '3.4 MB'."""
    size = float(n)
    for unit in ("B", "KB", "MB", "GB"):
        if abs(size) < 1024 or unit == "GB":
            return f"{size:.0f} {unit}" if unit == "B" else f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} TB"


@dataclass
class RunResult:
    """Summary returned by ColumnPickerApp.run() once a nullify pass completes."""

    output_file: str
    columns: int
    rows_modified: int
    values_nulled: int
    estimated_bytes: int


class ConfirmScreen(ModalScreen[bool]):
    """Modal confirmation before nullifying the selected columns and writing the output."""

    BINDINGS = [
        Binding("y", "confirm", "Yes"),
        Binding("n", "cancel", "No"),
        Binding("escape", "cancel", "No", show=False),
    ]

    def __init__(self, input_file, output_file, targets, estimated_bytes):
        super().__init__()
        self._input_file = input_file
        self._output_file = output_file
        self._targets = targets
        self._estimated_bytes = estimated_bytes

    def compose(self) -> ComposeResult:
        message = "\n".join(
            [
                f"Input:        {self._input_file}",
                f"Output:       {self._output_file}",
                f"Columns:      {len(self._targets)}",
                f"Est. savings: ~{_fmt_bytes(self._estimated_bytes)}",
                "",
                "Nullify the selected columns and write the output file?",
            ]
        )
        with Vertical(id="confirm-dialog"):
            yield Label(message, id="confirm-message")
            with Horizontal(id="confirm-buttons"):
                yield Button("Run (y)", variant="warning", id="yes")
                yield Button("Cancel (n)", variant="primary", id="no")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        self.dismiss(event.button.id == "yes")

    def action_confirm(self) -> None:
        self.dismiss(True)

    def action_cancel(self) -> None:
        self.dismiss(False)


class ColumnPickerApp(App):
    """Scans a dump for large bytea/text columns and nullifies the ones you pick."""

    TITLE = "pgslim — column picker"

    CSS = """
    ConfirmScreen { align: center middle; }
    #confirm-dialog {
        width: 70;
        height: auto;
        border: thick $warning;
        background: $surface;
        padding: 1 2;
    }
    #confirm-message { width: 100%; }
    #confirm-buttons { height: auto; align-horizontal: center; margin-top: 1; }
    #confirm-buttons Button { margin: 0 2; }
    """

    BINDINGS = [
        Binding("q", "quit", "Quit"),
        Binding("space", "toggle", "Toggle"),
        Binding("a", "select_all", "Select all"),
        Binding("x", "run", "Run"),
    ]

    def __init__(self, input_file, output_file, compress=False):
        super().__init__()
        self.input_file = input_file
        self.output_file = output_file
        self.compress = compress
        self._candidates = []
        self._selected = set()
        self.result = None

    def compose(self) -> ComposeResult:
        yield Header()
        yield DataTable(id="columns-table")
        yield Footer()

    def on_mount(self) -> None:
        table = self.query_one("#columns-table", DataTable)
        table.cursor_type = "row"
        table.add_columns("Sel", "Table", "Column", "Type", "Rows", "Est. Size")
        self.sub_title = f"Scanning {self.input_file}..."
        self.run_worker(self._scan, thread=True, exclusive=True, group="scan")

    # ------------------------------------------------------------------ scan

    def _scan(self) -> None:
        try:
            candidates = scan_candidate_columns(
                self.input_file,
                progress_cb=lambda done, total: self.call_from_thread(
                    self._report_scan_progress, done, total
                ),
            )
        except Exception as exc:  # noqa: BLE001 - surface any scan failure in the UI
            self.call_from_thread(self._scan_failed, exc)
            return
        self.call_from_thread(self._populate, candidates)

    def _report_scan_progress(self, done, total) -> None:
        pct = (done / total * 100) if total else 100
        self.sub_title = f"Scanning... {pct:.0f}%"

    def _scan_failed(self, exc) -> None:
        self.sub_title = "Scan failed"
        self.notify(str(exc), title="Scan error", severity="error", timeout=8)

    def _populate(self, candidates) -> None:
        self._candidates = candidates
        table = self.query_one("#columns-table", DataTable)
        table.clear()
        for c in candidates:
            table.add_row(
                "[ ]",
                c.table,
                c.column,
                c.col_type,
                f"{c.row_count:,}",
                _fmt_bytes(c.estimated_bytes),
            )
        if not candidates:
            self.sub_title = "No large bytea/text columns found"
        else:
            self._update_status()

    # -------------------------------------------------------------- selection

    def _update_status(self) -> None:
        total = sum(self._candidates[i].estimated_bytes for i in self._selected)
        self.sub_title = f"{len(self._selected)} columns selected — ~{_fmt_bytes(total)} saved"

    def action_toggle(self) -> None:
        table = self.query_one("#columns-table", DataTable)
        row = table.cursor_row
        if row is None or not (0 <= row < len(self._candidates)):
            return
        if row in self._selected:
            self._selected.discard(row)
            mark = "[ ]"
        else:
            self._selected.add(row)
            mark = "[x]"
        table.update_cell_at(Coordinate(row, 0), mark)
        self._update_status()

    def action_select_all(self) -> None:
        table = self.query_one("#columns-table", DataTable)
        select = len(self._selected) != len(self._candidates)
        self._selected = set(range(len(self._candidates))) if select else set()
        mark = "[x]" if select else "[ ]"
        for row in range(len(self._candidates)):
            table.update_cell_at(Coordinate(row, 0), mark)
        self._update_status()

    # ------------------------------------------------------------------- run

    def action_run(self) -> None:
        if not self._selected:
            self.notify("Select at least one column first (space)", severity="warning")
            return
        targets = [
            (self._candidates[i].table, self._candidates[i].column)
            for i in sorted(self._selected)
        ]
        estimated = sum(self._candidates[i].estimated_bytes for i in self._selected)

        def on_confirm(confirmed: bool) -> None:
            if confirmed:
                self._do_run(targets, estimated)

        self.push_screen(
            ConfirmScreen(self.input_file, self.output_file, targets, estimated), on_confirm
        )

    def _do_run(self, targets, estimated) -> None:
        self.sub_title = "Writing output..."
        self.notify(f"Nullifying {len(targets)} column(s)...", timeout=3)
        self.run_worker(
            lambda: self._run_nullify(targets, estimated), thread=True, group="run"
        )

    def _run_nullify(self, targets, estimated) -> None:
        try:
            rows_modified, values_nulled = process_file_multi(
                self.input_file,
                self.output_file,
                targets,
                verbose=False,
                compress=self.compress,
            )
        except Exception as exc:  # noqa: BLE001 - surface any write failure in the UI
            self.call_from_thread(self._run_failed, exc)
            return
        self.call_from_thread(self._run_done, targets, rows_modified, values_nulled, estimated)

    def _run_failed(self, exc) -> None:
        self.sub_title = "Failed"
        self.notify(str(exc), title="Nullify failed", severity="error", timeout=8)

    def _run_done(self, targets, rows_modified, values_nulled, estimated) -> None:
        self.result = RunResult(
            output_file=self.output_file,
            columns=len(targets),
            rows_modified=rows_modified,
            values_nulled=values_nulled,
            estimated_bytes=estimated,
        )
        self.notify(f"Wrote {self.output_file}", title="Done", timeout=4)
        self.exit(self.result)


def run_column_picker(input_file, output_file, compress=False):
    """Runs the full-screen picker and prints a plain-text summary afterwards."""
    app = ColumnPickerApp(input_file, output_file, compress)
    result = app.run()
    if result is None:
        print("[!] Cancelled — no output written.")
        return
    print(
        f"[*] Done! Wrote '{result.output_file}'. "
        f"Nullified {result.columns} column(s), modified {result.rows_modified:,} rows "
        f"({result.values_nulled:,} values), ~{_fmt_bytes(result.estimated_bytes)} saved."
    )
