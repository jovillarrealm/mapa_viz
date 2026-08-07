import argparse
import datetime
import os
import sys

import yaml

# Force UTF-8 output encoding for Windows terminals
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")  # type: ignore

import matplotlib

matplotlib.use("Agg")

from core.adapters import load_dataset
from core.cartography import render_publication_style
from core.cli import interactive_cli_menu, print_summary_table
from core.config import AppConfig, parse_config
from core.dem_handler import get_dem_and_hillshade
from core.domain import ProcessingSummary
from core.output_manager import (
    missing_artifacts,
    remove_legacy_root_artifacts,
    staged_dataset_output_directory,
)
from core.pipeline import (
    CartographyOverrides,
    DatasetRunOptions,
    dataset_output_directory,
    resolve_render_selection,
)
from core.result import Err
from core.web_exporter import export_web_map
from generate_sample_data import create_sample_excel


def load_config(config_path: str = "config.yaml") -> AppConfig:
    if os.path.exists(config_path):
        try:
            with open(config_path, encoding="utf-8") as f:
                raw: object = yaml.safe_load(f)
                return parse_config(raw)
        except Exception as e:
            print(f"[Warning] Failed to load config file '{config_path}': {e}")
    return {}


def process_single_dataset(
    input_source: str,
    options: DatasetRunOptions,
    cfg: AppConfig,
) -> ProcessingSummary:
    print("\n=========================================================================")
    print(f"      PROCESSING DATASET: {os.path.basename(input_source)}")
    print("=========================================================================")

    # 1. Ingestion via Data Adapter Architecture returning Result[SpatialDataset, SpatialError]
    print(f"\n--> 1. Ingesting & Adapting spatial data: {input_source}")
    ingest_result = load_dataset(
        source=input_source,
        lat_col=options.lat_col,
        lon_col=options.lon_col,
        group_col=options.group_col,
        crs=options.crs,
    )

    if isinstance(ingest_result, Err):
        error = ingest_result.error
        print(f"[ERROR] Failed to ingest spatial dataset '{input_source}': {error}")
        return {
            "dataset_name": os.path.basename(input_source),
            "num_points": 0,
            "output_dir": "FAILED",
            "num_files": 0,
            "error": str(error),
        }

    dataset = ingest_result.value
    gdf = dataset.gdf
    dataset_name = dataset.name
    group_col = dataset.group_col

    # Read CLI / interactive cartographic overrides
    overrides = options.overrides

    print(
        f"    [OK] Dataset '{dataset_name}' loaded successfully! "
        f"Points: {len(gdf)} | CRS: {gdf.crs} | Grouping Col: '{group_col}'"
    )

    # Determine isolated output directory for this dataset
    timestamp = datetime.datetime.now(datetime.UTC).strftime("%Y%m%d_%H%M%S")
    dataset_output_dir = dataset_output_directory(
        options.output_dir,
        dataset_name,
        unique_dirs=options.unique_dirs,
        timestamp=timestamp,
    )
    print(
        f"    [Output Directory] Isolated artifacts saved to: {os.path.abspath(dataset_output_dir)}"
    )

    # 2. Elevation DEM & 3D Hillshade
    print("\n--> 2. Fetching DEM elevation & computing 3D Hillshade relief...")
    dem_tuple = get_dem_and_hillshade(
        gdf=gdf,
        padding=options.padding,
        azimuth=cfg.get("elevation", {}).get("azimuth_deg", 315.0),
        altitude=cfg.get("elevation", {}).get("altitude_deg", 45.0),
    )
    print("    [OK] DEM Elevation & 3D Hillshade matrix ready.")

    # 3. Static Publication Cartography & Decoupled Matrix Rendering
    render_plan = options.render
    style_names = [style.value for style in render_plan.styles]
    format_names = [export_format.value for export_format in render_plan.formats]
    print(
        f"\n--> 3. Generating cartographic matrix ({options.dpi} DPI)... "
        f"Styles: {style_names} × Formats: {format_names}"
    )

    with staged_dataset_output_directory(
        dataset_output_dir,
        replace_existing=not options.unique_dirs,
    ) as staging_dir:
        for style in render_plan.styles:
            render_publication_style(
                gdf=gdf,
                dem_tuple=dem_tuple,
                output_dir=staging_dir,
                map_style=style,
                formats=list(render_plan.formats),
                dpi=options.dpi,
                group_col=group_col,
                config=cfg,
                with_legend=overrides.with_legend,
                show_point_labels=overrides.show_point_labels,
                show_elevation_colorbar=overrides.show_elevation_colorbar,
                show_inset=overrides.show_inset,
                inset_position=overrides.inset_position,
            )

        # 4. Interactive Web Map HTML (Standalone HTML output)
        if render_plan.include_web_map:
            print("\n--> 4. Exporting GPU interactive Web Map (HTML)...")
            export_web_map(
                gdf=gdf,
                output_path=os.path.join(staging_dir, "mapa_interactivo.html"),
                group_col=group_col,
                title=f"Mapa de {dataset_name}",
            )

        missing = missing_artifacts(
            staging_dir, render_plan.expected_artifact_names
        )
        if missing:
            raise RuntimeError(
                "Render completed without planned artifacts: " + ", ".join(missing)
            )

    rendered_files = [
        os.path.join(dataset_output_dir, name)
        for name in render_plan.expected_artifact_names
    ]

    print("\n-------------------------------------------------------------------------")
    print(
        f"      [OK] FINISHED DATASET '{dataset_name}' ({len(rendered_files)} files rendered)"
    )
    print("-------------------------------------------------------------------------\n")

    return {
        "dataset_name": dataset_name,
        "num_points": len(gdf),
        "output_dir": os.path.abspath(dataset_output_dir),
        "num_files": len(rendered_files),
        "rendered_files": rendered_files,
    }


def main():
    parser = argparse.ArgumentParser(
        prog="geo_map_generator",
        description="""
========================================================================
   GEO MAP GENERATOR - PIPELINE AUTOMATIZADO DE CARTOGRAFÍA
   Generación automatizada de mapas topográficos, híbridos y basemaps
========================================================================
Generador cartográfico automatizado de alto rendimiento para Ictiología y Análisis Espacial.
Soporta matriz de renderizado multi-formato (PDF, PNG, TIFF, JPEG XL, Mapa Web Interactivo HTML)
con elevación DEM de AWS, sombreado 3D de relieve (hillshade), hidrografía Natural Earth y
ubicación inteligente de leyendas, insets y escalas.
""",
        epilog="""
EJEMPLOS DE USO / USAGE EXAMPLES:
------------------------------------------------------------------------
1. Procesar dataset de muestra por defecto (500 DPI):
   $ python main.py -i inputs/SampleSites_Afa_planas.xlsx

2. Procesar con leyenda por defecto (afuera en el panel derecho):
   $ python main.py -i inputs/Coordenadas_Cordylancistrus.xlsx --with-legend

3. Procesar con leyenda adentro del mapa (posición superior derecha):
   $ python main.py -i inputs/Coordenadas_Cordylancistrus.xlsx --with-legend inside

4. Especificar posición exacta de leyenda (afuera en esquina inferior derecha):
   $ python main.py -i inputs/coordenadas_mapa_Hypostomus_Liseth.xlsx --with-legend bottom_right_outside

5. Procesar todos los datasets en inputs/ con leyenda y exportar PDF + PNG:
   $ python main.py -i inputs --with-legend -f pdf png -s hybrid_aquatic topo

6. Iniciar menú interactivo Rich en la terminal:
   $ python main.py --interactive
------------------------------------------------------------------------
""",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    # 1. Input & Workflow Options
    g_input = parser.add_argument_group("Input & Workflow Options / Opciones de Entrada")
    g_input.add_argument(
        "-i",
        "--input",
        nargs="?",
        const="INTERACTIVE",
        default=None,
        help="Ruta al archivo o directorio espacial de entrada (e.g. inputs/dataset.xlsx), o sin argumento para menú interactivo.",
    )
    g_input.add_argument(
        "--interactive",
        action="store_true",
        help="Iniciar el menú interactivo Rich en la terminal.",
    )
    g_input.add_argument(
        "--all-inputs",
        action="store_true",
        help="Procesar todos los archivos espaciales compatibles en el directorio 'inputs/'.",
    )

    # 2. Styles & Export Formats
    g_style = parser.add_argument_group("Map Styles & Export Formats / Estilos y Formatos")
    g_style.add_argument(
        "-s",
        "--styles",
        nargs="+",
        default=["all"],
        help="Estilos de mapa a renderizar: 'publicacion' / 'hybrid_aquatic' (híbrido acuático), 'topo' (topográfico hipsométrico), 'basemap' (CartoDB limpio), o 'all' (por defecto: all).",
    )
    g_style.add_argument(
        "-f",
        "--formats",
        nargs="+",
        default=["png", "pdf", "jxl"],
        help="Formatos de exportación: 'png', 'pdf', 'tif' / 'tiff', 'jxl' (JPEG XL), o 'all' (por defecto: png pdf jxl).",
    )
    g_style.add_argument(
        "--dpi",
        type=int,
        default=500,
        help="Resolución DPI para exportación estática de mapas de publicación (por defecto: 500 DPI).",
    )
    g_style.add_argument(
        "--no-web",
        action="store_true",
        help="Desactivar la generación del mapa web interactivo GPU en HTML.",
    )

    # 3. Legend & Point Labels
    g_legend = parser.add_argument_group("Legend & Point Labels / Leyendas y Etiquetas")
    g_legend.add_argument(
        "--with-legend",
        nargs="?",
        const="top_right_outside",
        default=None,
        help="Activar leyenda y especificar su ubicación/posicionamiento. Afuera: 'top_right_outside' (por defecto), 'top_left_outside', 'bottom_right_outside', 'bottom_left_outside', 'bottom_outside'. Adentro: 'inside' / 'top_right_inside', 'top_left_inside', 'bottom_right_inside', 'bottom_left_inside', 'bottom_center_inside'.",
    )
    g_legend.add_argument(
        "--show-labels",
        action="store_true",
        help="Forzar la visualización de etiquetas de texto sobre los puntos de muestreo.",
    )
    g_legend.add_argument(
        "--hide-labels",
        action="store_true",
        help="Forzar el ocultamiento de etiquetas de texto sobre los puntos de muestreo.",
    )

    # 4. Map Layout Elements
    g_layout = parser.add_argument_group("Map Layout Elements / Inset y Barra de Colores")
    g_layout.add_argument(
        "--show-inset",
        action="store_true",
        help="Mostrar el submapa continental de Colombia (inset).",
    )
    g_layout.add_argument(
        "--hide-inset",
        action="store_true",
        help="Ocultar el submapa continental de Colombia.",
    )
    g_layout.add_argument(
        "--inset-position",
        default=None,
        choices=["top_left", "top_right", "bottom_left", "bottom_right", "auto", "outside", "outside_right", "outside_left"],
        help="Ubicación del submapa inset: 'top_left' (por defecto), 'top_right', 'bottom_left', 'bottom_right', 'auto', 'outside'.",
    )
    g_layout.add_argument(
        "--show-colorbar",
        action="store_true",
        help="Mostrar la barra de colores de elevación (m.s.n.m.).",
    )
    g_layout.add_argument(
        "--hide-colorbar",
        action="store_true",
        help="Ocultar la barra de colores de elevación.",
    )

    # 5. Spatial Data Ingestion & CRS
    g_geo = parser.add_argument_group("Spatial Data Ingestion & CRS / Ingesta y Coordenadas")
    g_geo.add_argument(
        "--lat-col",
        default=None,
        help="Nombre explícito de la columna de Latitud (opcional, auto-detectado).",
    )
    g_geo.add_argument(
        "--lon-col",
        default=None,
        help="Nombre explícito de la columna de Longitud (opcional, auto-detectado).",
    )
    g_geo.add_argument(
        "-g",
        "--group-col",
        default=None,
        help="Columna para agrupar marcadores/colores (e.g. Sector, Especie, Codigo, Sitio).",
    )
    g_geo.add_argument(
        "--crs",
        default="EPSG:4326",
        help="Sistema de Referencia Espacial / Proyección (e.g. EPSG:4326, EPSG:3116, MAGNA-SIRGAS) (por defecto: EPSG:4326).",
    )
    g_geo.add_argument(
        "--padding",
        type=float,
        default=0.35,
        help="Margen/Padding alrededor del bounding box en grados (por defecto: 0.35).",
    )

    # 6. Output & Configuration
    g_out = parser.add_argument_group("Output & Configuration / Salida y Configuración")
    g_out.add_argument(
        "-o",
        "--output-dir",
        default="output",
        help="Directorio base para guardar los artefactos generados (por defecto: output).",
    )
    g_out.add_argument(
        "--unique-dirs",
        action="store_true",
        help="Adjuntar timestamp al directorio de salida para crear una nueva carpeta por cada ejecución.",
    )
    g_out.add_argument(
        "-c",
        "--config",
        default="config.yaml",
        help="Ruta al archivo YAML de configuración del sistema (por defecto: config.yaml).",
    )

    args = parser.parse_args()

    # Determine cartographic overrides from flags
    args.override_labels = (
        True if args.show_labels else (False if args.hide_labels else None)
    )
    args.override_colorbar = (
        True if args.show_colorbar else (False if args.hide_colorbar else None)
    )
    args.override_inset = (
        True if args.show_inset else (False if args.hide_inset else None)
    )

    # Check if interactive mode should be launched
    is_interactive_stdin = sys.stdin and sys.stdin.isatty()
    should_launch_interactive = (
        args.interactive
        or (args.input == "INTERACTIVE")
        or (args.input is None and is_interactive_stdin)
    )

    cfg = load_config(args.config)

    if should_launch_interactive:
        try:
            cli_opts = interactive_cli_menu()
            target_files = cli_opts["input_sources"]
            selected_styles = cli_opts.get("selected_styles", ["all"])
            selected_formats = cli_opts["selected_formats"]
            include_web_map = cli_opts.get("include_web_map", True)
            args.dpi = cli_opts["dpi"]
            args.with_legend = cli_opts["override_with_legend"]
            args.override_labels = cli_opts["override_labels"]
            args.override_colorbar = cli_opts["override_colorbar"]
        except Exception as e:
            print(f"[CLI] Interactive menu cancelled or interrupted: {e}")
            sys.exit(0)
    else:
        selected_styles = args.styles
        selected_formats = args.formats
        include_web_map = not args.no_web
        input_target = (
            args.input if args.input and args.input != "INTERACTIVE" else "inputs"
        )
        target_files = []

        if os.path.isdir(input_target) or args.all_inputs:
            search_dir = input_target if os.path.isdir(input_target) else "inputs"
            valid_exts = [".xlsx", ".xls", ".csv", ".tsv", ".geojson", ".gpkg"]
            for root, _, files in os.walk(search_dir):
                for f in files:
                    ext = os.path.splitext(f)[1].lower()
                    if (
                        ext in valid_exts
                        and not f.startswith("~$")
                        and not f.startswith(".")
                    ):
                        target_files.append(os.path.join(root, f))
            target_files.sort()
        elif os.path.isfile(input_target):
            target_files = [input_target]
        else:
            sample_path = "inputs/SampleSites_Afa_planas.xlsx"
            if not os.path.exists(sample_path):
                os.makedirs("inputs", exist_ok=True)
                create_sample_excel(sample_path)
            target_files = [sample_path]

    if not target_files:
        print("[Error] No compatible spatial datasets found.")
        sys.exit(1)

    print("=========================================================================")
    print("      GEO MAP GENERATOR - PIPELINE AUTOMATIZADO DE CARTOGRAFÍA          ")
    print(f"      Data Adapters Loaded | Target Datasets: {len(target_files)}")
    print("=========================================================================")

    run_options = DatasetRunOptions(
        render=resolve_render_selection(
            selected_styles,
            selected_formats,
            include_web_map=include_web_map,
        ),
        output_dir=args.output_dir,
        unique_dirs=args.unique_dirs,
        dpi=args.dpi,
        padding=args.padding,
        lat_col=args.lat_col,
        lon_col=args.lon_col,
        group_col=args.group_col,
        crs=args.crs,
        overrides=CartographyOverrides(
            with_legend=args.with_legend,
            show_point_labels=args.override_labels,
            show_elevation_colorbar=args.override_colorbar,
            show_inset=args.override_inset,
            inset_position=args.inset_position,
        ),
    )

    removed_legacy_artifacts = remove_legacy_root_artifacts(args.output_dir)
    if removed_legacy_artifacts:
        print(
            "      Removed legacy root-level artifacts: "
            f"{len(removed_legacy_artifacts)}"
        )

    summary_results: list[ProcessingSummary] = []
    for file_path in target_files:
        try:
            res = process_single_dataset(
                file_path,
                run_options,
                cfg,
            )
            summary_results.append(res)
        except Exception as e:
            print(f"[ERROR] Failed to process dataset '{file_path}': {e}")

    if should_launch_interactive and summary_results:
        print_summary_table(summary_results)


if __name__ == "__main__":
    main()
