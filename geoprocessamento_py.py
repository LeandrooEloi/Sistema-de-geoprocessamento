import os
import webbrowser
import ee
import folium
from folium.plugins import Draw

PROJECT_ID = "analise-plantacao-gee"


def autenticar():
    try:
        ee.Initialize(project=PROJECT_ID)
    except Exception:
        ee.Authenticate(auth_mode="localhost")
        ee.Initialize(project=PROJECT_ID)


def add_ee_layer(map_obj, ee_object, vis_params, name):
    if isinstance(ee_object, ee.image.Image):
        map_id = ee_object.getMapId(vis_params)
        folium.raster_layers.TileLayer(
            tiles=map_id["tile_fetcher"].url_format,
            attr="Google Earth Engine",
            name=name,
            overlay=True,
            control=True
        ).add_to(map_obj)

    elif isinstance(ee_object, ee.imagecollection.ImageCollection):
        ee_image = ee_object.mosaic()
        map_id = ee_image.getMapId(vis_params)
        folium.raster_layers.TileLayer(
            tiles=map_id["tile_fetcher"].url_format,
            attr="Google Earth Engine",
            name=name,
            overlay=True,
            control=True
        ).add_to(map_obj)

    elif isinstance(ee_object, ee.geometry.Geometry):
        folium.GeoJson(
            data=ee_object.getInfo(),
            name=name,
            style_function=lambda x: {
                "color": "blue",
                "weight": 3,
                "fillOpacity": 0.1
            }
        ).add_to(map_obj)


def main():
    autenticar()

    perimetro = ee.Geometry.Polygon([
        [
            [-35.380397, -6.030409],
            [-35.379195, -6.030441],
            [-35.378975, -6.031060],
            [-35.378981, -6.031668],
            [-35.379345, -6.031930],
            [-35.380027, -6.031951],
            [-35.380493, -6.031540],
            [-35.380628, -6.030724],
            [-35.380397, -6.030409]
        ]
    ])

    area_ha = perimetro.area(maxError=1).divide(10000)
    print("Área em hectares:", area_ha.getInfo())

    colecao = (
        ee.ImageCollection("LANDSAT/LC08/C02/T1_TOA")
        .filterBounds(perimetro)
        .filterDate("2024-01-01", "2024-12-31")
    )

    imagem_mediana = colecao.median()
    ndvi = imagem_mediana.normalizedDifference(["B5", "B4"]).rename("NDVI")

    ndvi_medio = ndvi.reduceRegion(
        reducer=ee.Reducer.mean(),
        geometry=perimetro,
        scale=30,
        maxPixels=1e9
    )

    print("NDVI médio:", ndvi_medio.getInfo())

    mapa = folium.Map(
        location=[-6.0310, -35.3798],
        zoom_start=16,
        tiles=None
    )

    folium.TileLayer(
        tiles="https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
        attr="Esri World Imagery",
        name="Satélite",
        overlay=False,
        control=True
    ).add_to(mapa)

    draw = Draw(
        export=True,
        filename="perimetro_desenhado.geojson",
        position="topleft",
        draw_options={
            "polyline": False,
            "rectangle": True,
            "polygon": True,
            "circle": False,
            "circlemarker": False,
            "marker": True
        },
        edit_options={"edit": True}
    )
    draw.add_to(mapa)

    add_ee_layer(
        mapa,
        ndvi.clip(perimetro),
        {"min": 0, "max": 1, "palette": ["red", "yellow", "green"]},
        "NDVI"
    )

    add_ee_layer(mapa, perimetro, {}, "Perímetro atual")

    folium.LayerControl().add_to(mapa)

    html_file = os.path.abspath("mapa_plantacao_folium.html")
    mapa.save(html_file)
    webbrowser.open(html_file)

    print(f"Mapa salvo em: {html_file}")


if __name__ == "__main__":
    main()
