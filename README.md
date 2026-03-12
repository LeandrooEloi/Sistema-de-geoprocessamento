# Comparação Temporal de Áreas com NDVI

Aplicação em Python para análise geoespacial de áreas agrícolas usando imagens de satélite, Google Earth Engine, Folium e Streamlit.

O sistema permite buscar um local por nome ou por coordenadas, desenhar o perímetro da área no mapa, escolher o sensor e comparar o NDVI entre dois períodos diferentes.

---

## Demonstração

### Tela inicial
![Tela inicial](./assets/screenshots/tela-inicial.png)

### Busca por local
![Busca por local](./assets/screenshots/busca-local.png)

### Área desenhada no mapa
![Área desenhada](./assets/screenshots/area-desenhada.png)

### Comparação temporal de NDVI
![Comparação NDVI](./assets/screenshots/comparacao-ndvi.png)

### Resultado da análise
![Resultado](./assets/screenshots/resultado.png)

---

## Sobre o projeto

Este projeto foi desenvolvido para analisar a evolução de uma área ao longo do tempo com base em imagens de satélite.

A aplicação permite:

- Buscar a área de interesse por nome da cidade/local.
- Centralizar o mapa por latitude e longitude.
- Desenhar polígonos ou retângulos sobre a área de análise.
- Calcular a área do perímetro selecionado em hectares.
- Comparar dois períodos diferentes com base no NDVI.
- Visualizar camadas RGB, NDVI do período A, NDVI do período B e a diferença entre os dois períodos.
- Escolher entre Sentinel-2 e Landsat 8 como fonte de dados.

---

## Tecnologias utilizadas

- Python
- Streamlit
- Google Earth Engine
- Folium
- streamlit-folium
- Nominatim / OpenStreetMap
- Requests

---

## Como o sistema funciona

O fluxo da aplicação é simples:

1. O usuário informa um local por nome ou por coordenadas.
2. O mapa é centralizado na região escolhida.
3. O usuário desenha o perímetro da área no mapa.
4. A geometria desenhada é capturada pela aplicação.
5. O usuário seleciona o sensor e define dois períodos de análise.
6. O sistema consulta as imagens no Google Earth Engine.
7. O NDVI é calculado para cada período.
8. A aplicação calcula a diferença entre os períodos e mostra os resultados no mapa e no painel lateral.

---

## Estrutura do projeto

```bash
.
├── app.py
├── geoprocessamento_py.py
├── requirements.txt
├── README.md
└── assets/
    └── screenshots/
