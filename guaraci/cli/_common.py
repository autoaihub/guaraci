"""Shared helpers for the Guaraci CLI commands.

Centralises the options, progress rendering and error handling that used to
be copy-pasted across the health-system CLIs (sih/sim/sinan) and snis.
"""

from __future__ import annotations

import json
from contextlib import contextmanager
from typing import Any, Callable, Dict, Iterator, Optional

import click
from rich.console import Console
from rich.progress import BarColumn, Progress, SpinnerColumn, TextColumn

EXPORT_FORMATS = ("csv", "parquet", "sqlite")

#: Shared click options ------------------------------------------------------

output_dir_option = click.option(
    "--output-dir", "-o", type=click.Path(), help="Output directory"
)

format_option = click.option(
    "--format",
    "output_format",
    type=click.Choice(list(EXPORT_FORMATS)),
    default="csv",
    help="Output format",
)

states_option = click.option(
    "--states", "-s", multiple=True, help="States (UF codes) to download, e.g. SP RJ"
)

json_option = click.option(
    "--json",
    "as_json",
    is_flag=True,
    default=False,
    help="Print only a machine-readable JSON result on stdout (no rich output).",
)


def resolve_verbose(ctx: click.Context, local_verbose: bool) -> bool:
    """Combine a subgroup's own -v with the root group's -v (via ctx.obj)."""
    ctx.ensure_object(dict)
    verbose = bool(local_verbose) or bool(ctx.obj.get("verbose"))
    ctx.obj["verbose"] = verbose
    return verbose


def current_verbose() -> bool:
    """Read the propagated --verbose value from the active click context."""
    ctx = click.get_current_context(silent=True)
    if ctx is None or not isinstance(ctx.obj, dict):
        return False
    return bool(ctx.obj.get("verbose"))


def result_to_dict(result: Any) -> Dict[str, Any]:
    """Normalize a JobResult/Mapping into a plain dict."""
    if hasattr(result, "to_dict"):
        return dict(result.to_dict())
    return dict(result)


def print_json(result: Any) -> None:
    """Print a result as plain JSON on stdout (for scripting)."""
    click.echo(json.dumps(result_to_dict(result), ensure_ascii=False, indent=2, default=str))


def raise_cli_error(exc: BaseException, verbose: bool = False) -> None:
    """Standard CLI error handling: ClickException (exit 1) or, under
    verbose, let the original traceback surface."""
    if isinstance(exc, (click.ClickException, click.Abort)):
        raise exc
    if verbose:
        raise exc
    raise click.ClickException(str(exc)) from exc


def raise_if_downloads_failed(download_info: Any, *, unit: str = "file") -> None:
    """Encerra com erro quando parte dos arquivos não foi baixada.

    Uma coleta em que 10 de 11 arquivos falharam não é um sucesso, mas era
    reportada como tal: o CLI imprimia um aviso, seguia para o export do que
    sobrou e saía com 0, de modo que qualquer script a jusante tratava a
    execução como boa. O aviso continua sendo impresso pelo chamador; aqui
    só se garante que o código de saída conte a mesma história.
    """
    failed = (download_info or {}).get("failed_downloads") or []
    if not failed:
        return
    total = (download_info or {}).get("total_files") or 0
    raise click.ClickException(
        f"{len(failed)} of {total} {unit}(s) failed during download; "
        "the exported data covers only what was retrieved."
    )


@contextmanager
def download_progress(
    console: Console, description: str
) -> Iterator[Callable[[int, int], None]]:
    """Yield a (completed, total) progress callback rendered with Rich.

    This is the progress block previously duplicated in sih/sim/sinan.
    """
    progress_state: Dict[str, Optional[Any]] = {"task": None}
    with Progress(
        SpinnerColumn(),
        BarColumn(bar_width=None),
        TextColumn("{task.completed}/{task.total} files"),
        console=console,
        transient=True,
    ) as progress:

        def progress_callback(completed: int, total: int) -> None:
            if total <= 0:
                return
            if progress_state["task"] is None:
                progress_state["task"] = progress.add_task(description, total=total)
            progress.update(progress_state["task"], completed=completed)

        yield progress_callback
