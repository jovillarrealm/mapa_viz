import os

import folium
from folium.plugins import Fullscreen, MeasureControl


def export_web_map(
    gdf,
    output_path="output/mapa_interactivo.html",
    group_col="Sector",
    title="Mapa Interactivo de Ictiología",
):
    """
    Exports an interactive Web Map in HTML format using Folium / Leaflet JS.
    Includes popup cards, layer toggling per sector, tooltips, and tile choices.
    """
    bounds = gdf.total_bounds
    min_lon, min_lat, max_lon, max_lat = bounds[0], bounds[1], bounds[2], bounds[3]
    center_lat = (min_lat + max_lat) / 2.0
    center_lon = (min_lon + max_lon) / 2.0

    # Initialize Folium Map
    m = folium.Map(location=[center_lat, center_lon], zoom_start=10, tiles=None)

    # Tile Layers
    folium.TileLayer("OpenStreetMap", name="OpenStreetMap (Callejero)").add_to(m)
    folium.TileLayer(
        tiles="https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
        attr="Esri World Imagery",
        name="Esri Satelital 🛰️",
    ).add_to(m)
    folium.TileLayer(
        tiles="https://server.arcgisonline.com/ArcGIS/rest/services/World_Topo_Map/MapServer/tile/{z}/{y}/{x}",
        attr="Esri World Topo Map",
        name="Esri Topográfico 🏔️",
    ).add_to(m)
    folium.TileLayer("CartoDB Positron", name="CartoDB Claro").add_to(m)

    # Color Palette for groups
    palette = [
        "#1f77b4",
        "#ff7f0e",
        "#2ca02c",
        "#d62728",
        "#9467bd",
        "#8c564b",
        "#e377c2",
        "#7f7f7f",
        "#bcbd22",
        "#17becf",
        "#35b779",
        "#fde725",
        "#440154",
        "#31688e",
    ]

    # Create FeatureGroups for each sector/group
    groups = gdf.groupby(group_col)
    for idx, (group_name, group_data) in enumerate(groups):
        color = palette[idx % len(palette)]
        feature_group = folium.FeatureGroup(
            name=f"{group_col}: {group_name} ({len(group_data)})"
        )

        for _, row in group_data.iterrows():
            lat = float(row.geometry.y)
            lon = float(row.geometry.x)

            popup_html = f"""
            <div style="font-family: Arial, sans-serif; font-size: 12px; width: 230px;">
                <h4 style="margin:0 0 8px 0; color: {color}; border-bottom: 2px solid {color}; padding-bottom: 3px;">
                    📍 {group_name}
                </h4>
                <table style="width: 100%; border-collapse: collapse;">
                    <tr><td style="padding: 2px 0;"><b>Latitud:</b></td><td>{lat:.5f}°</td></tr>
                    <tr><td style="padding: 2px 0;"><b>Longitud:</b></td><td>{lon:.5f}°</td></tr>
            """

            for col in group_data.columns:
                if col not in ["geometry", group_col, "Group"] and not col.startswith(
                    "Unnamed"
                ):
                    val = row[col]
                    if pd_not_null(val):
                        popup_html += f"<tr><td style='padding: 2px 0;'><b>{col}:</b></td><td>{val}</td></tr>"

            popup_html += """
                </table>
            </div>
            """

            tooltip_text = f"{group_name} (Lat: {lat:.3f}, Lon: {lon:.3f})"

            folium.CircleMarker(
                location=[lat, lon],
                radius=7,
                popup=folium.Popup(popup_html, max_width=320),
                tooltip=tooltip_text,
                color="black",
                weight=1.2,
                fill=True,
                fill_color=color,
                fill_opacity=0.9,
            ).add_to(feature_group)

        feature_group.add_to(m)

    # Automatically fit map view to bounding box of dataset
    m.fit_bounds([[min_lat - 0.05, min_lon - 0.05], [max_lat + 0.05, max_lon + 0.05]])

    # Add interactive controls
    folium.LayerControl(collapsed=False).add_to(m)
    Fullscreen(position="topright").add_to(m)
    MeasureControl(position="bottomleft").add_to(m)

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    m.save(output_path)
    print(f"[WebExporter] Interactive web map saved to: {output_path}")
    return output_path


def pd_not_null(val):
    import pandas as pd

    return pd.notna(val) and str(val).strip() != ""
