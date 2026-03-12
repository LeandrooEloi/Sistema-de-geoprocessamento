from datetime import date, timedelta
import requests

import ee
import folium
import streamlit as st
from folium.plugins import Draw
from streamlit_folium import st_folium


# =========================================================
# CONFIGURAÇÃO GERAL
# =========================================================

# ID do projeto do Google Earth Engine
PROJECT_ID = "analise-plantacao-gee"


# =========================================================
# AUTENTICAÇÃO EARTH ENGINE
# =========================================================

# Inicializa o Earth Engine.
# Se a autenticação já existir, apenas inicia.
# Se não existir, abre o fluxo de login no navegador.
def autenticar_ee():
    try:
        ee.Initialize(project=PROJECT_ID)
    except Exception:
        ee.Authenticate(auth_mode="localhost")
        ee.Initialize(project=PROJECT_ID)


# =========================================================
# ESTADO DA SESSÃO
# =========================================================

# Cria variáveis persistentes do Streamlit para não perder
# informações importantes a cada rerun.
def inicializar_estado():
    if "comparacao" not in st.session_state:
        st.session_state.comparacao = None

    if "geometria_desenhada" not in st.session_state:
        st.session_state.geometria_desenhada = None

    if "desenho_atual" not in st.session_state:
        st.session_state.desenho_atual = None

    if "mostrar_mensagem_captura" not in st.session_state:
        st.session_state.mostrar_mensagem_captura = False

    if "mostrar_mensagem_comparacao" not in st.session_state:
        st.session_state.mostrar_mensagem_comparacao = False

    if "mostrar_mensagem_local" not in st.session_state:
        st.session_state.mostrar_mensagem_local = False

    if "mensagem_local" not in st.session_state:
        st.session_state.mensagem_local = ""

    if "center" not in st.session_state:
        st.session_state.center = [-6.0310, -35.3798]

    if "zoom" not in st.session_state:
        st.session_state.zoom = 16

    if "marcador_local" not in st.session_state:
        st.session_state.marcador_local = None


# =========================================================
# BUSCA DE LOCALIZAÇÃO
# =========================================================

# Busca um local pelo nome usando Nominatim.
# O endpoint de busca aceita q, format=jsonv2 e limit.
def buscar_local_por_nome(termo_busca):
    url = "https://nominatim.openstreetmap.org/search"
    params = {
        "q": termo_busca,
        "format": "jsonv2",
        "limit": 1
    }
    headers = {
        "User-Agent": "analise-plantacao-streamlit/1.0"
    }

    resposta = requests.get(url, params=params, headers=headers, timeout=20)
    resposta.raise_for_status()

    dados = resposta.json()

    if not dados:
        return None

    local = dados[0]

    return {
        "nome": local.get("display_name", termo_busca),
        "lat": float(local["lat"]),
        "lon": float(local["lon"])
    }


# Define o centro do mapa e cria um marcador no local pesquisado.
def definir_localizacao(nome, lat, lon, zoom=14):
    st.session_state.center = [lat, lon]
    st.session_state.zoom = zoom
    st.session_state.marcador_local = {
        "nome": nome,
        "lat": lat,
        "lon": lon
    }


# =========================================================
# CAMADAS E SENSOR
# =========================================================

# Adiciona uma camada raster no mapa do Folium.
def add_tile_layer(map_obj, tile_url, name, show=True):
    folium.raster_layers.TileLayer(
        tiles=tile_url,
        attr="Google Earth Engine",
        name=name,
        overlay=True,
        control=True,
        show=show
    ).add_to(map_obj)


# Converte uma imagem do Earth Engine em URL de tiles.
def ee_tile_url(ee_image, vis_params):
    map_id = ee_image.getMapId(vis_params)
    return map_id["tile_fetcher"].url_format


# Retorna a configuração do sensor escolhido.
# Sentinel-2 usa B8/B4 para NDVI e 10 m.
# Landsat 8 usa B5/B4 e 30 m.
def obter_config_sensor(sensor):
    if sensor == "Sentinel-2":
        return {
            "colecao": "COPERNICUS/S2_SR_HARMONIZED",
            "nir": "B8",
            "red": "B4",
            "rgb_bands": ["B4", "B3", "B2"],
            "rgb_vis": {"min": 0, "max": 3000},
            "ndvi_scale": 10,
        }

    return {
        "colecao": "LANDSAT/LC08/C02/T1_TOA",
        "nir": "B5",
        "red": "B4",
        "rgb_bands": ["B4", "B3", "B2"],
        "rgb_vis": {"min": 0.03, "max": 0.3},
        "ndvi_scale": 30,
    }


# =========================================================
# PROCESSAMENTO DE UM PERÍODO
# =========================================================

# Prepara a imagem e os indicadores de um período.
def preparar_periodo(perimetro, data_inicial, data_final, sensor):
    config = obter_config_sensor(sensor)

    colecao = (
        ee.ImageCollection(config["colecao"])
        .filterBounds(perimetro)
        .filterDate(str(data_inicial), str(data_final))
    )

    quantidade = colecao.size().getInfo()

    if quantidade == 0:
        return {
            "sem_imagem": True,
            "sensor": sensor,
            "data_inicial": str(data_inicial),
            "data_final": str(data_final),
            "quantidade_imagens": 0,
        }

    imagem = colecao.median()
    ndvi = imagem.normalizedDifference([config["nir"], config["red"]]).rename("NDVI")

    ndvi_medio = ndvi.reduceRegion(
        reducer=ee.Reducer.mean(),
        geometry=perimetro,
        scale=config["ndvi_scale"],
        maxPixels=1e9
    ).getInfo().get("NDVI")

    rgb_vis = {
        "bands": config["rgb_bands"],
        **config["rgb_vis"]
    }

    ndvi_vis = {
        "min": 0,
        "max": 1,
        "palette": ["red", "yellow", "green"]
    }

    return {
        "sem_imagem": False,
        "sensor": sensor,
        "data_inicial": str(data_inicial),
        "data_final": str(data_final),
        "quantidade_imagens": quantidade,
        "ndvi_medio": ndvi_medio,
        "rgb_tile_url": ee_tile_url(imagem, rgb_vis),
        "ndvi_tile_url": ee_tile_url(ndvi, ndvi_vis),
        "ndvi_image": ndvi,
    }


# =========================================================
# COMPARAÇÃO ENTRE PERÍODOS
# =========================================================

# Compara dois períodos para a mesma geometria.
def comparar_periodos(perimetro, a_ini, a_fim, b_ini, b_fim, sensor):
    config = obter_config_sensor(sensor)

    area_ha = perimetro.area(maxError=1).divide(10000).getInfo()

    periodo_a = preparar_periodo(perimetro, a_ini, a_fim, sensor)
    periodo_b = preparar_periodo(perimetro, b_ini, b_fim, sensor)

    resultado = {
        "sensor": sensor,
        "area_ha": area_ha,
        "periodo_a": periodo_a,
        "periodo_b": periodo_b,
        "perimetro_geojson": perimetro.getInfo(),
    }

    if periodo_a["sem_imagem"] or periodo_b["sem_imagem"]:
        resultado["sem_imagem"] = True
        return resultado

    ndvi_diff = periodo_b["ndvi_image"].subtract(periodo_a["ndvi_image"]).rename("NDVI_DIF")

    diff_stats = ndvi_diff.reduceRegion(
        reducer=ee.Reducer.mean(),
        geometry=perimetro,
        scale=config["ndvi_scale"],
        maxPixels=1e9
    ).getInfo().get("NDVI_DIF")

    diff_vis = {
        "min": -0.4,
        "max": 0.4,
        "palette": ["red", "white", "green"]
    }

    resultado["sem_imagem"] = False
    resultado["delta_ndvi"] = None

    if periodo_a["ndvi_medio"] is not None and periodo_b["ndvi_medio"] is not None:
        resultado["delta_ndvi"] = periodo_b["ndvi_medio"] - periodo_a["ndvi_medio"]

    resultado["ndvi_diff_medio"] = diff_stats
    resultado["ndvi_diff_tile_url"] = ee_tile_url(ndvi_diff, diff_vis)

    del resultado["periodo_a"]["ndvi_image"]
    del resultado["periodo_b"]["ndvi_image"]

    return resultado


# =========================================================
# CRIAÇÃO DO MAPA
# =========================================================

# Monta o mapa com:
# - satélite base
# - ferramentas de desenho
# - marcador do local pesquisado
# - área capturada
# - camadas de NDVI quando houver comparação
def criar_mapa():
    m = folium.Map(
        location=st.session_state.center,
        zoom_start=st.session_state.zoom,
        tiles=None
    )

    folium.TileLayer(
        tiles="https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
        attr="Esri World Imagery",
        name="Satélite",
        overlay=False,
        control=True
    ).add_to(m)

    Draw(
        export=False,
        position="topleft",
        draw_options={
            "polyline": False,
            "rectangle": True,
            "polygon": True,
            "circle": False,
            "circlemarker": False,
            "marker": False
        },
        edit_options={"edit": True}
    ).add_to(m)

    if st.session_state.marcador_local is not None:
        folium.Marker(
            location=[
                st.session_state.marcador_local["lat"],
                st.session_state.marcador_local["lon"]
            ],
            popup=st.session_state.marcador_local["nome"],
            tooltip="Local pesquisado"
        ).add_to(m)

    if st.session_state.geometria_desenhada is not None:
        folium.GeoJson(
            st.session_state.geometria_desenhada,
            name="Área selecionada",
            style_function=lambda x: {
                "color": "#00bfff",
                "weight": 3,
                "fillColor": "#00bfff",
                "fillOpacity": 0.15
            }
        ).add_to(m)

    comp = st.session_state.comparacao
    if comp is not None and not comp.get("sem_imagem", False):
        add_tile_layer(m, comp["periodo_a"]["rgb_tile_url"], "RGB período A", show=False)
        add_tile_layer(m, comp["periodo_b"]["rgb_tile_url"], "RGB período B", show=False)
        add_tile_layer(m, comp["periodo_a"]["ndvi_tile_url"], "NDVI período A", show=False)
        add_tile_layer(m, comp["periodo_b"]["ndvi_tile_url"], "NDVI período B", show=False)
        add_tile_layer(m, comp["ndvi_diff_tile_url"], "Diferença NDVI (B - A)", show=True)

    folium.LayerControl().add_to(m)
    return m


# =========================================================
# INTERFACE PRINCIPAL
# =========================================================

st.set_page_config(page_title="Comparação temporal NDVI", layout="wide")
st.title("Comparação temporal da área")

autenticar_ee()
inicializar_estado()


# ---------------------------------------------------------
# SIDEBAR - LOCALIZAÇÃO
# ---------------------------------------------------------
with st.sidebar:
    st.subheader("Localização")

    with st.form("form_localizacao"):
        termo_busca = st.text_input(
            "Buscar por cidade/local",
            value="",
            placeholder="Ex.: Natal, RN"
        )

        latitude = st.number_input(
            "Latitude",
            value=float(st.session_state.center[0]),
            format="%.6f"
        )

        longitude = st.number_input(
            "Longitude",
            value=float(st.session_state.center[1]),
            format="%.6f"
        )

        buscar_nome = st.form_submit_button("Buscar por nome", use_container_width=True)
        ir_coordenadas = st.form_submit_button("Ir para coordenadas", use_container_width=True)

    st.subheader("Sensor")
    sensor = st.radio(
        "Escolha o sensor",
        options=["Sentinel-2", "Landsat 8"],
        index=0,
        key="sensor_escolhido"
    )

    with st.form("form_periodos"):
        st.subheader("Período A")
        intervalo_a = st.date_input(
            "Escolha o intervalo A",
            value=(date(2020, 1, 1), date(2020, 12, 31)),
            key="intervalo_a"
        )

        st.subheader("Período B")
        intervalo_b = st.date_input(
            "Escolha o intervalo B",
            value=(date(2025, 1, 1), date(2025, 12, 31)),
            key="intervalo_b"
        )

        capturar = st.form_submit_button("Capturar área desenhada", use_container_width=True)
        comparar = st.form_submit_button("Comparar períodos", use_container_width=True)
        limpar = st.form_submit_button("Limpar análise", use_container_width=True)


# ---------------------------------------------------------
# AÇÕES DE LOCALIZAÇÃO
# ---------------------------------------------------------
if buscar_nome:
    if not termo_busca.strip():
        st.session_state.mensagem_local = "Digite um nome de cidade ou local."
        st.session_state.mostrar_mensagem_local = True
        st.rerun()
    else:
        try:
            local = buscar_local_por_nome(termo_busca.strip())
            if local is None:
                st.session_state.mensagem_local = "Nenhum local encontrado."
            else:
                definir_localizacao(local["nome"], local["lat"], local["lon"], zoom=13)
                st.session_state.mensagem_local = f"Local encontrado: {local['nome']}"
            st.session_state.mostrar_mensagem_local = True
            st.rerun()
        except Exception:
            st.session_state.mensagem_local = "Não foi possível buscar o local pelo nome."
            st.session_state.mostrar_mensagem_local = True
            st.rerun()

if ir_coordenadas:
    definir_localizacao(
        nome=f"Lat {latitude:.6f}, Lon {longitude:.6f}",
        lat=float(latitude),
        lon=float(longitude),
        zoom=15
    )
    st.session_state.mensagem_local = "Mapa centralizado nas coordenadas informadas."
    st.session_state.mostrar_mensagem_local = True
    st.rerun()


# ---------------------------------------------------------
# LAYOUT PRINCIPAL
# ---------------------------------------------------------
col1, col2 = st.columns([2, 1])

with col1:
    st.subheader("Mapa")

    mapa = criar_mapa()

    mapa_data = st_folium(
        mapa,
        key="mapa_comparacao_estavel",
        width=900,
        height=620,
        returned_objects=["all_drawings", "last_active_drawing"],
        use_container_width=True
    )

    if mapa_data:
        ultimo = mapa_data.get("last_active_drawing")
        todos = mapa_data.get("all_drawings", [])

        if ultimo is not None:
            st.session_state.desenho_atual = ultimo
        elif todos:
            st.session_state.desenho_atual = todos[-1]

with col2:
    st.subheader("Resultados")

    if st.session_state.mostrar_mensagem_local:
        st.success(st.session_state.mensagem_local)
        st.session_state.mostrar_mensagem_local = False

    if capturar:
        if st.session_state.desenho_atual is None:
            st.warning("Desenhe um polígono ou retângulo no mapa primeiro.")
        else:
            st.session_state.geometria_desenhada = st.session_state.desenho_atual
            st.session_state.comparacao = None
            st.session_state.mostrar_mensagem_captura = True
            st.session_state.mostrar_mensagem_comparacao = False
            st.rerun()

    if limpar:
        st.session_state.comparacao = None
        st.session_state.geometria_desenhada = None
        st.session_state.desenho_atual = None
        st.session_state.mostrar_mensagem_captura = False
        st.session_state.mostrar_mensagem_comparacao = False
        st.rerun()

    if comparar:
        if st.session_state.geometria_desenhada is None:
            st.warning("Capture uma área desenhada antes de comparar.")
        else:
            perimetro = ee.Geometry(st.session_state.geometria_desenhada["geometry"])

            if isinstance(intervalo_a, tuple) and len(intervalo_a) == 2:
                a_ini, a_fim = intervalo_a
            else:
                a_ini = intervalo_a
                a_fim = intervalo_a + timedelta(days=1)

            if isinstance(intervalo_b, tuple) and len(intervalo_b) == 2:
                b_ini, b_fim = intervalo_b
            else:
                b_ini = intervalo_b
                b_fim = intervalo_b + timedelta(days=1)

            st.session_state.comparacao = comparar_periodos(
                perimetro, a_ini, a_fim, b_ini, b_fim, sensor
            )
            st.session_state.mostrar_mensagem_comparacao = True
            st.rerun()

    if st.session_state.mostrar_mensagem_captura:
        st.success("Área capturada com sucesso.")
        st.session_state.mostrar_mensagem_captura = False

    if st.session_state.mostrar_mensagem_comparacao:
        st.success("Comparação concluída.")
        st.session_state.mostrar_mensagem_comparacao = False

    if st.session_state.geometria_desenhada is None:
        st.info("1. Busque o local ou informe coordenadas. 2. Desenhe a área no mapa. 3. Clique em Capturar área desenhada.")
    elif st.session_state.comparacao is None:
        st.info("Área capturada. Agora clique em Comparar períodos.")
    else:
        comp = st.session_state.comparacao

        if comp.get("sem_imagem", False):
            st.warning("Um dos períodos não retornou imagens para esse sensor.")
            st.write(f"Sensor: {comp['sensor']}")
            st.write(f"Período A: {comp['periodo_a']['data_inicial']} até {comp['periodo_a']['data_final']}")
            st.write(f"Período B: {comp['periodo_b']['data_inicial']} até {comp['periodo_b']['data_final']}")
        else:
            st.write(f"Sensor usado: {comp['sensor']}")
            st.metric("Área (ha)", f"{comp['area_ha']:.2f}")
            st.metric("NDVI médio A", f"{comp['periodo_a']['ndvi_medio']:.3f}")
            st.metric("NDVI médio B", f"{comp['periodo_b']['ndvi_medio']:.3f}")

            if comp["delta_ndvi"] is not None:
                st.metric("Delta NDVI (B - A)", f"{comp['delta_ndvi']:.3f}")

            if comp["ndvi_diff_medio"] is not None:
                st.metric("Média da diferença", f"{comp['ndvi_diff_medio']:.3f}")

            st.write(f"Período A: {comp['periodo_a']['data_inicial']} até {comp['periodo_a']['data_final']}")
            st.write(f"Imagens no A: {comp['periodo_a']['quantidade_imagens']}")
            st.write(f"Período B: {comp['periodo_b']['data_inicial']} até {comp['periodo_b']['data_final']}")
            st.write(f"Imagens no B: {comp['periodo_b']['quantidade_imagens']}")
            st.caption("Ative no mapa as camadas RGB, NDVI A, NDVI B e Diferença NDVI.")
