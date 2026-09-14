# RCA: diagonales en la capa de agua

**Estado:** causa confirmada; autenticación corregida y capa restaurada. Validación visual final pendiente de una API key válida.
**Fecha:** 2026-09-13
**Afectación:** `hybrid_aquatic` / `publicacion` y `basemap`.

## Causa confirmada

Los PNG servidos por CARTO sin API key contienen el texto diagonal `API KEY REQUIRED` y `carto.com/basemaps/apikey`. Al reducir cientos de tiles a la resolución de un mapa, el texto se convierte en trazos diagonales repetidos. El recoloreado del híbrido acentúa esos trazos, pero también aparecen en el basemap sin recolorear.

La inspección de tiles originales de mar, río y llanura confirmó el texto antes de cualquier reproyección. Una prueba de mosaico de un solo tile conservó exactamente sus píxeles. Por tanto, atribuir el patrón a interpolación o discontinuidades entre tiles fue un diagnóstico incorrecto.

CARTO confirma el cambio y la autenticación por parámetro `key` en su [página de claves](https://carto.com/basemaps/apikey/) y su [repositorio oficial de estilos](https://github.com/CartoDB/basemap-styles).

## Corrección

- `CartoDBNoLabels` requiere `CARTO_BASEMAP_API_KEY` y la codifica como parámetro `key` en todas sus solicitudes. `CartoDBBlueWaterOverlay` hereda la misma autenticación.
- Restaurado el overlay acuático de publicación con la opacidad anterior (0.85): conserva océanos, lagos y drenajes del basemap sobre el DEM, además de los vectores Natural Earth.
- La falta de clave detiene ambos estilos antes de crear una figura o escribir salidas. No se exporta silenciosamente una capa ausente o marcada.
- Los mapas que usan CARTO incluyen atribución visible a CARTO y OpenStreetMap.
- `.env` queda ignorado por Git. Ejecutar con `uv run --env-file .env main.py` y las opciones habituales. `topo` no necesita clave.

La eliminación del overlay aplicada inicialmente fue una solución incompleta: quitaba detalle de agua en publicación y dejaba el problema en `basemap`. Las imágenes de `scratch/debug_water_overlay/after/` generadas durante ese intento son evidencia histórica, no el resultado final corregido.

## Validación

- Regresión de autenticación y composición: **5 fallos y 1 éxito antes** de la corrección; después pasa.
- `uv run pytest -q`: **34 pruebas aprobadas**. Comprueban envío/codificación de la clave, rechazo de solicitudes sin clave, conservación de salidas previas, presencia del overlay, recoloreado de agua, DEM, hidrografía vectorial, puntos, extent y atribución.
- `uv run ruff check core/ main.py tests/` y `uv run ty check core/ main.py tests/`: aprobados.
- Las pruebas automáticas usan tiles sintéticos y no requieren una clave real. La regeneración y comparación visual con tiles autenticados todavía requiere la clave del usuario; no se da por validada hasta completar esa corrida.
- Evidencia local sin modificar: `scratch/debug_water_overlay/tile_sea.png`, `tile_river.png`, `tile_plain.png`. Las tres imágenes muestran la marca del proveedor.

## Uso en publicaciones

La [página de claves de CARTO](https://carto.com/basemaps/apikey/) incluye investigación en el servicio gratuito, con un límite de 5 millones de solicitudes de tiles al mes. Las [condiciones, §9(d) y §13](https://carto.com/legal/basemap-terms/), permiten imágenes estáticas ilustrativas/editoriales/documentales con atribución legible dentro de la imagen. Esto corresponde a las figuras cartográficas del proyecto; no supone permiso general para redistribuir tiles o extraer contenido del servicio en masa.
