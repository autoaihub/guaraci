"""Generic, schema-driven CLI to fetch any registered Guaraci source.

This drives :class:`guaraci.services.downloads.DownloadService` so every
registered source (DATASUS FTP, OpenDataSUS, NASA, gov.br) is reachable from a
single command, with no per-source boilerplate::

    guaraci fetch list
    guaraci fetch schema nasa_power
    guaraci fetch discover sia --set start_year=2024 --set end_year=2024 --sizes
    guaraci fetch run srag_demas --set start_year=2023 --set end_year=2023 \\
        --set uf=SP --format parquet --output-dir ./out
    guaraci fetch run nasa_power --set latitude=-23.55 --set longitude=-46.63 \\
        --set start_date=2024-01-01 --set end_date=2024-01-31 -o ./out

Parameter values are coerced to the type declared by the source schema
(``guaraci fetch schema <source>``). Credentials for NASA sources are read from
the environment (``GUARACI_FIRMS_MAP_KEY``, ``GUARACI_EARTHDATA_TOKEN``) and are
never accepted as flags (they would be persisted to disk).
"""
from __future__ import annotations

import json
from importlib import resources
from typing import Any, Dict, Optional, Tuple

import click
from rich.console import Console
from rich.table import Table

from guaraci.cli._common import json_option, print_json, result_to_dict

console = Console()

_TRUE = {"1", "true", "t", "yes", "y", "on"}
_FALSE = {"0", "false", "f", "no", "n", "off"}


def _coerce(raw: str, param_type: str) -> Any:
    """Coerce a raw ``--set`` string to the type declared by the source schema."""
    value = raw.strip()
    if param_type == "integer":
        try:
            return int(value)
        except ValueError as exc:
            raise click.BadParameter(f"expected an integer, got {raw!r}") from exc
    if param_type == "boolean":
        low = value.lower()
        if low in _TRUE:
            return True
        if low in _FALSE:
            return False
        raise click.BadParameter(f"expected a boolean (true/false), got {raw!r}")
    if param_type == "string_list":
        return [part.strip() for part in value.split(",") if part.strip()]
    return value


def _parse_sets(
    sets: Tuple[str, ...], schema: Dict[str, Dict[str, Any]]
) -> Dict[str, Any]:
    """Parse ``KEY=VALUE`` pairs into a kwargs dict, validating names + types."""
    kwargs: Dict[str, Any] = {}
    for item in sets:
        if "=" not in item:
            raise click.BadParameter(f"--set expects KEY=VALUE, got {item!r}")
        key, _, raw = item.partition("=")
        key = key.strip()
        spec = schema.get(key)
        if spec is None:
            known = ", ".join(sorted(schema)) or "(none)"
            raise click.BadParameter(
                f"unknown parameter {key!r} for this source. Known: {known}"
            )
        kwargs[key] = _coerce(raw, str(spec.get("type", "string")))
    return kwargs


@click.group()
def fetch() -> None:
    """Fetch any registered source through the DownloadService registry."""


@fetch.command(name="list")
@click.option(
    "--theme",
    "-t",
    default=None,
    help="Só as fontes de um tema (ver 'guaraci fetch themes').",
)
def list_cmd(theme: Optional[str]) -> None:
    """List every registered source (source, title, transport mode, themes)."""
    from guaraci.services.downloads import DownloadService

    try:
        descriptors = DownloadService().list_sources(theme=theme)
    except ValueError as exc:
        raise click.BadParameter(str(exc))

    title = "Guaraci registered sources"
    if theme:
        title += f" — tema: {theme.strip().lower()}"
    table = Table(title=title)
    for col in ("source", "title", "mode", "themes"):
        table.add_column(col, overflow="fold")
    for descriptor in descriptors:
        table.add_row(
            descriptor.source,
            descriptor.title,
            descriptor.mode,
            ", ".join(descriptor.themes),
        )
    console.print(table)
    if not descriptors:
        console.print("[yellow]nenhuma fonte nesse tema ainda[/yellow]")


@fetch.command(name="themes")
def themes_cmd() -> None:
    """Show the theme vocabulary used to navigate the source catalogue."""
    from guaraci.services.downloads import DownloadService

    table = Table(title="Guaraci themes")
    for col in ("slug", "label", "sources", "description"):
        table.add_column(col, overflow="fold")
    for item in DownloadService().list_themes():
        table.add_row(
            str(item["slug"]),
            str(item["label"]),
            str(item["source_count"]),
            str(item["description"]),
        )
    console.print(table)
    console.print(
        "[dim]tip: 'guaraci fetch list --theme oncologia' filtra o catálogo; "
        "'guaraci fetch presets' mostra os recortes prontos[/dim]"
    )


@fetch.command(name="presets")
def presets_cmd() -> None:
    """List the ready-made cross-source thematic cuts."""
    from guaraci.services.downloads import DownloadService

    table = Table(title="Guaraci presets")
    for col in ("name", "title", "sources"):
        table.add_column(col, overflow="fold")
    for item in DownloadService().list_presets():
        steps = item.get("steps") or []
        table.add_row(
            str(item["name"]),
            str(item["title"]),
            ", ".join(str(step["source"]) for step in steps),
        )
    console.print(table)
    console.print("[dim]tip: 'guaraci fetch preset oncologia' mostra a receita[/dim]")


@fetch.command(name="preset")
@click.argument("name")
def preset_cmd(name: str) -> None:
    """Show the recipe for preset NAME: which source, which params, what is missing.

    Cada passo diz se o recorte sai pronto da coleta ou se ainda depende de um
    filtro posterior. Os parâmetros são validados contra o schema vivo de cada
    fonte antes de serem impressos, então uma receita desatualizada falha aqui
    em vez de falhar no meio de um download.
    """
    from guaraci.services.downloads import DownloadService

    try:
        preset = DownloadService().get_preset(name)
    except ValueError as exc:
        raise click.BadParameter(str(exc))

    console.print(f"[bold]{preset['title']}[/bold] ([cyan]{preset['name']}[/cyan])")
    console.print(str(preset["description"]))
    console.print()

    table = Table(title="passos")
    for col in ("source", "params", "por quê", "falta filtrar"):
        table.add_column(col, overflow="fold")
    for step in preset["steps"]:
        params = step.get("params") or {}
        rendered = (
            ", ".join(f"{k}={_render_value(v)}" for k, v in params.items())
            if params
            else "[dim](padrão da fonte)[/dim]"
        )
        table.add_row(
            str(step["source"]),
            rendered,
            str(step["rationale"]),
            str(step.get("refine") or ""),
        )
    console.print(table)

    caveats = preset.get("caveats") or []
    if caveats:
        console.print()
        console.print("[bold yellow]ressalvas[/bold yellow]")
        for caveat in caveats:
            console.print(f"  • {caveat}")

    console.print()
    console.print("[dim]para executar um passo:[/dim]")
    for step in preset["steps"]:
        params = step.get("params") or {}
        sets = " ".join(f"--set {k}={_render_value(v)}" for k, v in params.items())
        console.print(
            f"  guaraci fetch run {step['source']} "
            f"--set start_year=2023 --set end_year=2023 {sets}".rstrip()
        )


def _render_value(value: Any) -> str:
    """Render a preset param value the way ``--set`` expects to receive it."""
    if isinstance(value, (list, tuple)):
        return ",".join(str(item) for item in value)
    return str(value)


@fetch.command(name="schema")
@click.argument("source")
def schema_cmd(source: str) -> None:
    """Show the parameter schema for SOURCE (name, type, required, default)."""
    from guaraci.services.downloads import DownloadService

    try:
        schema = DownloadService().get_source_schema(source.strip().lower())
    except (KeyError, ValueError) as exc:
        raise click.BadParameter(str(exc))
    table = Table(
        title=f"{schema['title']} ({schema['source']}) - mode: {schema['mode']}"
    )
    for col in ("name", "type", "required", "default", "allowed_values"):
        table.add_column(col, overflow="fold")
    for param in schema["params"]:
        allowed = param.get("allowed_values")
        table.add_row(
            str(param.get("name", "")),
            str(param.get("type", "")),
            "yes" if param.get("required") else "",
            "" if param.get("default") is None else str(param.get("default")),
            ", ".join(map(str, allowed)) if allowed else "",
        )
    console.print(table)


@fetch.command(name="run")
@click.argument("source")
@click.option(
    "--set",
    "sets",
    multiple=True,
    metavar="KEY=VALUE",
    help="Source parameter (repeatable). See 'guaraci fetch schema <source>'.",
)
@click.option(
    "--format",
    "output_format",
    type=click.Choice(["csv", "parquet", "sqlite"]),
    default=None,
    help=(
        "Export format. Omit to only download/collect without exporting "
        "(preserves each source's default); crawler sources ignore it."
    ),
)
@click.option(
    "--output-dir",
    "-o",
    default=None,
    help="Output directory (defaults to the Guaraci data dir if omitted).",
)
@click.option(
    "--verbose",
    "-v",
    is_flag=True,
    default=False,
    help="Also print the full raw result payload.",
)
@json_option
def run_cmd(
    source: str,
    sets: Tuple[str, ...],
    output_format: str,
    output_dir: Optional[str],
    verbose: bool,
    as_json: bool,
) -> None:
    """Fetch SOURCE, optionally exporting a dataset with --format.

    Required parameters vary per source; run 'guaraci fetch schema <source>'
    first. Validation errors list exactly what is missing or unknown.
    """
    from guaraci.services.downloads import DownloadService

    service = DownloadService()
    canonical = source.strip().lower()
    try:
        schema_params = {
            param["name"]: param
            for param in service.get_source_schema(canonical)["params"]
        }
    except (KeyError, ValueError) as exc:
        raise click.BadParameter(str(exc))

    kwargs = _parse_sets(sets, schema_params)
    # Only inject these when the source declares them (validation rejects
    # unknown keys, e.g. gov.br crawlers have no output_format), and only inject
    # output_format when the user explicitly passed --format so the source's own
    # default ("download only, no export") is preserved.
    if output_format is not None and "output_format" in schema_params:
        kwargs["output_format"] = output_format
    if output_dir and "output_dir" in schema_params:
        kwargs["output_dir"] = output_dir

    # Convert *validation* errors into a clean usage error, but let genuine
    # runtime failures from run() surface as real errors (not "bad parameter").
    try:
        service.validate_source_params(canonical, kwargs)
    except ValueError as exc:
        raise click.BadParameter(str(exc))
    result = service.run(canonical, **kwargs)

    if as_json:
        print_json(result)
        return

    payload = result_to_dict(result)
    exported = payload.get("exported_files") or []
    if exported:
        console.print(f"[green]OK[/green] - wrote {len(exported)} file(s):")
        for path in exported:
            console.print(f"  {path}")
    else:
        warning = payload.get("export_warning") or (
            "no dataset exported (empty result, or a crawler source that only "
            "downloads raw files)"
        )
        console.print(f"[yellow]No exported dataset[/yellow] - {warning}")

    # Avisos da coleta (truncamento no limite de páginas, recorte sem
    # registros) precisam aparecer aqui: ficar só no manifesto em disco fazia
    # uma coleta cortada passar por bem-sucedida.
    warnings = getattr(result, "warnings", None) or []
    for item in warnings:
        console.print(f"[yellow]WARNING[/yellow] {item}")

    if verbose:
        console.print(payload)

    if payload.get("status") == "partial_success":
        raise click.ClickException(
            "The collection did not complete in full; see the warnings above."
        )


def _human_bytes(value: object) -> str:
    """Format a byte count as a human-readable string."""
    try:
        size = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return str(value)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if size < 1024 or unit == "TB":
            return f"{int(size)} B" if unit == "B" else f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} TB"


@fetch.command(name="discover")
@click.argument("source")
@click.option(
    "--set",
    "sets",
    multiple=True,
    metavar="KEY=VALUE",
    help="Source parameter (repeatable), e.g. --set start_year=2024 --set end_year=2024.",
)
@click.option(
    "--sizes",
    "-S",
    is_flag=True,
    default=False,
    help="Also estimate the total download size (slower: one SIZE call per file).",
)
def discover_cmd(source: str, sets: Tuple[str, ...], sizes: bool) -> None:
    """Preflight SOURCE: count files (and optionally total size) WITHOUT downloading.

    Only DATASUS FTP sources support discovery (sih, sim, sinan, sinasc, sia,
    cnes, pni, ciha, cih, siscan, sisprenatal, resp, pce, painel_oncologia).
    """
    from guaraci.services.downloads import DownloadService

    service = DownloadService()
    canonical = source.strip().lower()
    try:
        schema_params = {
            param["name"]: param
            for param in service.get_source_schema(canonical)["params"]
        }
    except (KeyError, ValueError) as exc:
        raise click.BadParameter(str(exc))

    kwargs = _parse_sets(sets, schema_params)
    try:
        summary = service.discover(canonical, fetch_sizes=sizes, **kwargs)
    except (ValueError, NotImplementedError) as exc:
        raise click.BadParameter(str(exc))

    count = summary.get("documents_found", summary.get("file_count", 0))
    console.print(
        f"[bold]{canonical}[/bold]: [cyan]{count}[/cyan] file(s) match (no download)"
    )
    total = summary.get("total_size_bytes")
    if total is not None:
        console.print(f"  total download size: [cyan]{_human_bytes(total)}[/cyan]")
    elif sizes:
        console.print("  total download size: [yellow]not reported[/yellow]")
    if summary.get("by_group"):
        console.print(f"  by group: {summary['by_group']}")
    if summary.get("by_state"):
        console.print(f"  by state: {summary['by_state']}")
    if not sizes:
        console.print(
            "[dim]  tip: add --sizes to also estimate the total download size[/dim]"
        )


def _load_field_dictionary() -> Dict[str, Any]:
    """Load the shipped per-source field dictionary (guaraci/data/field_dictionary.json)."""
    try:
        with resources.files("guaraci").joinpath("data", "field_dictionary.json").open(
            "r", encoding="utf-8"
        ) as fh:
            return json.load(fh)
    except (FileNotFoundError, ModuleNotFoundError, AttributeError, OSError):
        return {}


@fetch.command(name="fields")
@click.argument("source")
def fields_cmd(source: str) -> None:
    """Show the known OUTPUT field names for SOURCE (from the data dictionary).

    Fields come from a real sample captured by scripts/sample_sources.py and
    shipped in guaraci/data/field_dictionary.json (point-in-time). For the live
    filter parameters use 'guaraci fetch schema <source>'.
    """
    data = _load_field_dictionary()
    if not data:
        raise click.ClickException(
            "field dictionary not found. Run scripts/sample_sources.py to generate "
            "guaraci/data/field_dictionary.json."
        )
    canonical = source.strip().lower()
    entry = data.get(canonical)
    if entry is None:
        raise click.BadParameter(
            f"unknown source {source!r} (not in the field dictionary). "
            "See 'guaraci fetch list'."
        )
    console.print(f"[bold]{canonical}[/bold] — status: {entry.get('status')}")
    if entry.get("filters"):
        console.print("  [dim]filters:[/dim] " + ", ".join(entry["filters"]))
    fields = entry.get("fields")
    if fields:
        console.print(f"  [dim]fields ({len(fields)}):[/dim]")
        console.print("    " + ", ".join(fields))
    else:
        note = entry.get("note") or (
            "not sampled yet — run scripts/sample_sources.py to populate fields"
        )
        console.print(f"  [yellow]no fields captured[/yellow] — {note}")
