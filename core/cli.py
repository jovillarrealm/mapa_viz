import os
from typing import TypedDict

import questionary
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from core.domain import ProcessingSummary

console = Console()


class InteractiveCliOptions(TypedDict):
    input_sources: list[str]
    selected_styles: list[str]
    selected_formats: list[str]
    include_web_map: bool
    dpi: int
    override_with_legend: str | bool | None
    override_labels: bool | None
    override_colorbar: bool | None


def _string_list(value: object, *, field: str) -> list[str]:
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise TypeError(f"Interactive field '{field}' did not return a string list")
    return [item for item in value if isinstance(item, str)]


def display_welcome_banner() -> None:
    banner_text = (
        "[bold cyan]GEO MAP GENERATOR[/bold cyan] - [yellow]Pipeline Automatizado de Cartografía[/yellow]\n"
        "[dim]Ejes Independientes: Estilo de Capas × Formato de Exportación (PDF, PNG, TIFF, JXL)[/dim]"
    )
    console.print(Panel(banner_text, expand=False, border_style="cyan"))


def get_available_input_files(search_dir: str = "inputs") -> list[tuple[str, str]]:
    valid_exts = [".xlsx", ".xls", ".csv", ".tsv", ".geojson", ".gpkg"]
    files_found = []
    if os.path.exists(search_dir):
        for root, _, files in os.walk(search_dir):
            for f in files:
                ext = os.path.splitext(f)[1].lower()
                if (
                    ext in valid_exts
                    and not f.startswith("~$")
                    and not f.startswith(".")
                ):
                    rel_path = os.path.join(root, f)
                    files_found.append((f, rel_path))
    files_found.sort()
    return files_found


def interactive_cli_menu() -> InteractiveCliOptions:
    """
    Renders rich interactive terminal menu allowing users to independently select:
    - Map Styles (Eje 1: topo, hybrid_aquatic, basemap)
    - Export Formats (Eje 2: pdf, png, tif, jxl)
    """
    display_welcome_banner()

    available_files = get_available_input_files("inputs")
    choices = []

    if available_files:
        choices.append(
            questionary.Choice(
                title="[PROCESAR TODOS] Procesar todos los datasets en inputs/",
                value="ALL",
            )
        )
        for filename, filepath in available_files:
            choices.append(
                questionary.Choice(title=f"Dataset: {filename}", value=filepath)
            )

    choices.append(
        questionary.Choice(
            title="[OTRO] Especificar ruta de archivo personalizada...", value="CUSTOM"
        )
    )

    selected_input = str(
        questionary.select(
            "Seleccione el dataset de entrada a procesar:",
            choices=choices,
        ).unsafe_ask()
    )

    if selected_input == "CUSTOM":
        custom_path = str(
            questionary.path(
                "Ingrese la ruta del archivo de entrada:"
            ).unsafe_ask()
        )
        input_sources = [custom_path]
    elif selected_input == "ALL":
        input_sources = [filepath for _, filepath in available_files]
    else:
        input_sources = [selected_input]

    # Axis 1: Map Styles
    style_choices = [
        questionary.Choice(
            title="topo           - Topografía Pura (DEM Hipsométrico + Sombra 3D)",
            value="topo",
            checked=True,
        ),
        questionary.Choice(
            title="hybrid_aquatic - Híbrido / Publicación (DEM Topográfico + Capa Acuática Basemap)",
            value="hybrid_aquatic",
            checked=True,
        ),
        questionary.Choice(
            title="basemap        - Basemap Limpio CartoDB (No-Labels)",
            value="basemap",
            checked=True,
        ),
    ]

    selected_styles = _string_list(
        questionary.checkbox(
            "Seleccione los Estilos de Mapa a generar (Eje 1):",
            choices=style_choices,
        ).unsafe_ask(),
        field="selected_styles",
    )

    if not selected_styles:
        selected_styles = ["topo", "hybrid_aquatic"]

    # Axis 2: Export Formats
    format_choices = [
        questionary.Choice(
            title="pdf - Documento Vectorial PDF",
            value="pdf",
            checked=True,
        ),
        questionary.Choice(
            title="png - Imagen PNG Alta Resolución (Compresión Nivel 9 <10MB)",
            value="png",
            checked=True,
        ),
        questionary.Choice(
            title="tif - Imagen Imprenta TIFF (Compresión Adobe Deflate <10MB)",
            value="tif",
            checked=True,
        ),
        questionary.Choice(
            title="jxl - Imagen JPEG XL Ultra-Compresible (.jxl <1MB)",
            value="jxl",
            checked=True,
        ),
    ]

    selected_formats = _string_list(
        questionary.checkbox(
            "Seleccione los Formatos de Archivo a exportar (Eje 2):",
            choices=format_choices,
        ).unsafe_ask(),
        field="selected_formats",
    )

    if not selected_formats:
        selected_formats = ["pdf", "png", "tif", "jxl"]

    include_web_map = bool(
        questionary.confirm(
            "¿Exportar también Mapa Web Interactivo HTML (GPU)?",
            default=True,
        ).unsafe_ask()
    )

    # Cartographic customization mode
    customize_carto = bool(
        questionary.confirm(
            "¿Desea personalizar las opciones cartográficas (leyendas, etiquetas, DPI)?",
            default=False,
        ).unsafe_ask()
    )

    dpi = 500
    override_with_legend: str | bool | None = None
    override_labels: bool | None = None
    override_colorbar: bool | None = None

    if customize_carto:
        legend_choice = str(
            questionary.select(
                "Visualización y Posición de Leyenda:",
                choices=[
                    questionary.Choice(
                        title="Sin Leyenda (Ocultar leyenda)", value="DEFAULT"
                    ),
                    questionary.Choice(
                        title="Leyenda Afuera (Panel Derecho - top_right_outside)", value="top_right_outside"
                    ),
                    questionary.Choice(
                        title="Leyenda Adentro (Superior Derecha - inside)", value="inside"
                    ),
                    questionary.Choice(
                        title="Leyenda Afuera Inferior (Panel Inferior - bottom_outside)", value="bottom_outside"
                    ),
                ],
            ).unsafe_ask()
        )

        if legend_choice != "DEFAULT":
            override_with_legend = legend_choice

        override_labels = bool(
            questionary.confirm(
                "¿Mostrar etiquetas de texto en puntos de muestreo?", default=True
            ).unsafe_ask()
        )
        override_colorbar = bool(
            questionary.confirm(
                "¿Mostrar barra de colores de elevación (Colorbar m.s.n.m.)?",
                default=False,
            ).unsafe_ask()
        )

        dpi_str = str(
            questionary.select(
                "Resolución DPI de Salida:",
                choices=[
                    "500 (Estándar Imprenta / Revista)",
                    "600 (Alta Resolución)",
                    "1200 (Ultra Alta Resolución)",
                ],
            ).unsafe_ask()
        )
        if "1200" in dpi_str:
            dpi = 1200
        elif "600" in dpi_str:
            dpi = 600
        else:
            dpi = 500

    return {
        "input_sources": input_sources,
        "selected_styles": selected_styles,
        "selected_formats": selected_formats,
        "include_web_map": include_web_map,
        "dpi": dpi,
        "override_with_legend": override_with_legend,
        "override_labels": override_labels,
        "override_colorbar": override_colorbar,
    }


def print_summary_table(results_summary: list[ProcessingSummary]) -> None:
    table = Table(title="📊 Resumen de Generación Cartográfica", border_style="green")
    table.add_column("Dataset", style="bold cyan")
    table.add_column("Puntos", justify="right", style="magenta")
    table.add_column("Directorio de Salida", style="yellow")
    table.add_column("Archivos Generados", justify="right", style="green")

    for item in results_summary:
        table.add_row(
            item["dataset_name"],
            str(item["num_points"]),
            item["output_dir"],
            f"{item['num_files']} archivos",
        )

    console.print("\n")
    console.print(table)
