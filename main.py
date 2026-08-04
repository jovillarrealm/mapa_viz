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
from core.domain import ExportFormat, MapStyle, ProcessingSummary
from core.result import Err, Ok
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
    args: argparse.Namespace,
    cfg: AppConfig,
    selected_styles: list[str] | None = None,
    selected_formats: list[str] | None = None,
    include_web_map: bool = True,
) -> ProcessingSummary:
    print("\n=========================================================================")
    print(f"      PROCESSING DATASET: {os.path.basename(input_source)}")
    print("=========================================================================")

    raw_styles = selected_styles or getattr(args, "styles", ["all"])
    raw_formats = selected_formats or getattr(args, "formats", ["all"])

    # Resolve MapStyles
    if "all" in raw_styles:
        active_styles = [
            MapStyle.TOPO,
            MapStyle.HYBRID_AQUATIC,
            MapStyle.HYBRID_RELIEF,
            MapStyle.BASEMAP,
        ]
    else:
        active_styles = []
        for s in raw_styles:
            s_lower = str(s).lower()
            match s_lower:
                case "hybrid_aquatic" | "hybrid1" | "dem_plus_basemap":
                    active_styles.append(MapStyle.HYBRID_AQUATIC)
                case "hybrid_relief" | "hybrid2" | "basemap_plus_hillshade":
                    active_styles.append(MapStyle.HYBRID_RELIEF)
                case "basemap" | "clean_png" | "clean_basemap":
                    active_styles.append(MapStyle.BASEMAP)
                case "topo" | "topographic" | "publication" | "publicacion" | _:
                    active_styles.append(MapStyle.TOPO)

    # Resolve ExportFormats
    if "all" in raw_formats:
        active_formats = [
            ExportFormat.PDF,
            ExportFormat.PNG,
            ExportFormat.TIFF,
            ExportFormat.JPEG_XL,
        ]
    else:
        active_formats = []
        for f in raw_formats:
            f_lower = str(f).lower()
            match f_lower:
                case "pdf":
                    active_formats.append(ExportFormat.PDF)
                case "png":
                    active_formats.append(ExportFormat.PNG)
                case "tif" | "tiff":
                    active_formats.append(ExportFormat.TIFF)
                case "jxl" | "jpegxl":
                    active_formats.append(ExportFormat.JPEG_XL)
                case "web" | "web_html" | "html":
                    include_web_map = True
                # Legacy style+format flags fallback
                case "hybrid1":
                    if MapStyle.HYBRID_AQUATIC not in active_styles:
                        active_styles.append(MapStyle.HYBRID_AQUATIC)
                    if ExportFormat.PNG not in active_formats:
                        active_formats.append(ExportFormat.PNG)
                case "hybrid2":
                    if MapStyle.HYBRID_RELIEF not in active_styles:
                        active_styles.append(MapStyle.HYBRID_RELIEF)
                    if ExportFormat.PNG not in active_formats:
                        active_formats.append(ExportFormat.PNG)
                case "clean_png":
                    if MapStyle.BASEMAP not in active_styles:
                        active_styles.append(MapStyle.BASEMAP)
                    if ExportFormat.PNG not in active_formats:
                        active_formats.append(ExportFormat.PNG)

    # 1. Ingestion via Data Adapter Architecture returning Result[SpatialDataset, SpatialError]
    print(f"\n--> 1. Ingesting & Adapting spatial data: {input_source}")
    ingest_result = load_dataset(
        source=input_source,
        lat_col=getattr(args, "lat_col", None),
        lon_col=getattr(args, "lon_col", None),
        group_col=getattr(args, "group_col", None),
        crs=getattr(args, "crs", "EPSG:4326"),
    )

    match ingest_result:
        case Err(error):
            print(f"[ERROR] Failed to ingest spatial dataset '{input_source}': {error}")
            return {
                "dataset_name": os.path.basename(input_source),
                "num_points": 0,
                "output_dir": "FAILED",
                "num_files": 0,
                "error": str(error),
            }
        case Ok(dataset):
            gdf = dataset.gdf
            dataset_name = dataset.name
            group_col = dataset.group_col

    # Read CLI / interactive cartographic overrides
    override_legend = getattr(args, "override_legend", None)
    override_labels = getattr(args, "override_labels", None)
    override_colorbar = getattr(args, "override_colorbar", None)
    override_inset = getattr(args, "override_inset", None)
    override_inset_pos = getattr(args, "inset_position", None)

    print(
        f"    [OK] Dataset '{dataset_name}' loaded successfully! "
        f"Points: {len(gdf)} | CRS: {gdf.crs} | Grouping Col: '{group_col}'"
    )

    # Determine isolated output directory for this dataset
    timestamp = datetime.datetime.now(datetime.UTC).strftime("%Y%m%d_%H%M%S")
    if getattr(args, "unique_dirs", False):
        dataset_output_dir = os.path.join(
            args.output_dir, f"{dataset_name}_{timestamp}"
        )
    else:
        dataset_output_dir = os.path.join(args.output_dir, dataset_name)

    os.makedirs(dataset_output_dir, exist_ok=True)
    print(
        f"    [Output Directory] Isolated artifacts saved to: {os.path.abspath(dataset_output_dir)}"
    )

    # 2. Elevation DEM & 3D Hillshade
    print("\n--> 2. Fetching DEM elevation & computing 3D Hillshade relief...")
    dem_tuple = get_dem_and_hillshade(
        gdf=gdf,
        padding=getattr(args, "padding", 0.35),
        azimuth=cfg.get("elevation", {}).get("azimuth_deg", 315.0),
        altitude=cfg.get("elevation", {}).get("altitude_deg", 45.0),
    )
    print("    [OK] DEM Elevation & 3D Hillshade matrix ready.")

    # 3. Static Publication Cartography & Decoupled Matrix Rendering
    dpi = getattr(args, "dpi", 1200)
    style_names = [s.value for s in active_styles]
    format_names = [f.value for f in active_formats]
    print(
        f"\n--> 3. Generating cartographic matrix ({dpi} DPI)... "
        f"Styles: {style_names} × Formats: {format_names}"
    )

    rendered_files = []

    for style in active_styles:
        outputs = render_publication_style(
            gdf=gdf,
            dem_tuple=dem_tuple,
            output_dir=dataset_output_dir,
            map_style=style,
            formats=active_formats,
            dpi=dpi,
            group_col=group_col,
            config=cfg,
            show_legend=override_legend,
            show_point_labels=override_labels,
            show_elevation_colorbar=override_colorbar,
            show_inset=override_inset,
            inset_position=override_inset_pos,
        )
        rendered_files.extend(outputs)

    # Sync primary mapa_publicacion outputs to root output/ for root level access
    import shutil
    base_out = getattr(args, "output_dir", "output")
    if os.path.abspath(dataset_output_dir) != os.path.abspath(base_out):
        for f in rendered_files:
            bname = os.path.basename(f)
            if bname.startswith("mapa_publicacion"):
                dst = os.path.join(base_out, bname)
                try:
                    shutil.copy2(f, dst)
                    print(f"    [Sync] Primary publication artifact updated -> {dst}")
                except Exception:
                    pass

    # 4. Interactive Web Map HTML (Standalone HTML output)
    if include_web_map:
        print("\n--> 4. Exporting GPU interactive Web Map (HTML)...")
        web_path = os.path.join(dataset_output_dir, "mapa_interactivo.html")
        export_web_map(
            gdf=gdf,
            output_path=web_path,
            group_col=group_col,
            title=f"Mapa de {dataset_name}",
        )
        rendered_files.append(web_path)

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
        description="Automated Cartographic Map Generator for Ichthyology (geo_map_generator)"
    )
    parser.add_argument(
        "-i",
        "--input",
        nargs="?",
        const="INTERACTIVE",
        default=None,
        help="Input file/dir path, or omit to launch Interactive CLI Menu",
    )
    parser.add_argument(
        "--interactive",
        action="store_true",
        help="Launch Rich Interactive Terminal Menu",
    )
    parser.add_argument(
        "--all-inputs",
        action="store_true",
        help="Process all compatible spatial files found in the inputs directory",
    )
    parser.add_argument(
        "-s",
        "--styles",
        nargs="+",
        default=["all"],
        help="Specify cartographic map styles: publicacion/topo hybrid_aquatic hybrid_relief basemap all",
    )
    parser.add_argument(
        "-f",
        "--formats",
        nargs="+",
        default=["all"],
        help="Specify export container formats: pdf png tif jxl all",
    )
    parser.add_argument(
        "--no-web",
        action="store_true",
        help="Disable interactive HTML web map generation",
    )

    # Cartographic CLI flags
    parser.add_argument(
        "--show-legend",
        action="store_true",
        help="Display sampling points / sectors legend box",
    )
    parser.add_argument(
        "--hide-legend",
        action="store_true",
        help="Hide sampling points / sectors legend box",
    )
    parser.add_argument(
        "--show-labels",
        action="store_true",
        help="Display text labels over sampling points",
    )
    parser.add_argument(
        "--hide-labels",
        action="store_true",
        help="Hide text labels over sampling points",
    )
    parser.add_argument(
        "--show-colorbar",
        action="store_true",
        help="Display elevation colorbar (m.s.n.m.)",
    )
    parser.add_argument(
        "--hide-colorbar",
        action="store_true",
        help="Hide elevation colorbar",
    )
    parser.add_argument(
        "--show-inset",
        action="store_true",
        help="Display Colombia submap inset",
    )
    parser.add_argument(
        "--hide-inset",
        action="store_true",
        help="Hide Colombia submap inset",
    )
    parser.add_argument(
        "--inset-position",
        default=None,
        choices=["top_left", "top_right", "bottom_left", "bottom_right", "auto", "outside", "outside_right", "outside_left"],
        help="Specify submap inset location: top_left (default), top_right, bottom_left, bottom_right, auto, outside",
    )

    parser.add_argument(
        "--lat-col",
        default=None,
        help="Name of Latitude column (optional, auto-detected)",
    )
    parser.add_argument(
        "--lon-col",
        default=None,
        help="Name of Longitude column (optional, auto-detected)",
    )
    parser.add_argument(
        "-g",
        "--group-col",
        default=None,
        help="Column for grouping markers (e.g., Sector, Species, Code)",
    )
    parser.add_argument(
        "--crs",
        default="EPSG:4326",
        help="Coordinate Reference System / Projection (e.g. EPSG:4326, EPSG:3116, EPSG:9377, EPSG:32618, 'UTM 18N', 'MAGNA-SIRGAS')",
    )
    parser.add_argument(
        "-o",
        "--output-dir",
        default="output",
        help="Base destination directory for generated map outputs",
    )
    parser.add_argument(
        "--unique-dirs",
        action="store_true",
        help="Append timestamp to output directories to create a new folder for every run",
    )
    parser.add_argument(
        "--dpi",
        type=int,
        default=300,
        help="DPI resolution for static publication maps (default: 300)",
    )
    parser.add_argument(
        "--padding",
        type=float,
        default=0.35,
        help="Padding around bounding box in degrees (default: 0.35)",
    )
    parser.add_argument(
        "-c",
        "--config",
        default="config.yaml",
        help="Path to YAML configuration file",
    )

    args = parser.parse_args()

    # Determine cartographic overrides from flags
    args.override_legend = (
        True if args.show_legend else (False if args.hide_legend else None)
    )
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
            args.override_legend = cli_opts["override_legend"]
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

    summary_results: list[ProcessingSummary] = []
    for file_path in target_files:
        try:
            res = process_single_dataset(
                file_path,
                args,
                cfg,
                selected_styles=selected_styles,
                selected_formats=selected_formats,
                include_web_map=include_web_map,
            )
            summary_results.append(res)
        except Exception as e:
            print(f"[ERROR] Failed to process dataset '{file_path}': {e}")

    if should_launch_interactive and summary_results:
        print_summary_table(summary_results)


if __name__ == "__main__":
    main()
