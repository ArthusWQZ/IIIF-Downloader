import streamlit as st
from curl_cffi import requests
from PIL import Image
from io import BytesIO
import math

st.title("Dezoomify — IIIF Image Downloader")

base_url = st.text_input(
    "Base URL",
    placeholder="https://example.com/iiif/image-id",
    help="URL racine IIIF, sans le /info.json final",
)

if st.button("Télécharger l'image", disabled=not base_url):
    progress_text = st.empty()
    progress_bar = st.progress(0)

    base_url = base_url.rstrip("/")  # Supprimer les slashs finaux

    try:
        progress_text.text("Récupération des métadonnées (info.json)…")
        r = requests.get(f"{base_url}/info.json", impersonate="chrome", timeout=30)
        if r.status_code != 200 or not r.text.strip():
            st.error(f"Échec info.json — status {r.status_code}: {r.text[:200]}")
            st.stop()

        info = r.json()
        width, height = info["width"], info["height"]
        tile_size = info["tiles"][0]["width"]
        st.info(f"Image {width}×{height} px — tuile {tile_size} px")

        cols = math.ceil(width / tile_size)
        rows = math.ceil(height / tile_size)
        total = cols * rows
        result = Image.new("RGB", (width, height))
        done = 0

        for row in range(rows):
            for col in range(cols):
                x, y = col * tile_size, row * tile_size
                w, h = min(tile_size, width - x), min(tile_size, height - y)
                region = f"{x},{y},{w},{h}"

                for fmt in ["png", "jpg"]:
                    url = f"{base_url}/{region}/{w},/0/default.{fmt}"
                    tile_r = requests.get(url, impersonate="chrome", timeout=30)
                    if tile_r.status_code == 200:
                        tile = Image.open(BytesIO(tile_r.content))
                        result.paste(tile, (x, y))
                        break

                done += 1
                progress_bar.progress(done / total)
                progress_text.text(f"Tuile {done}/{total} ({row+1}/{rows} lignes)")

        progress_text.text("Assemblage terminé.")
        progress_bar.progress(1.0)

        buf = BytesIO()
        result.save(buf, format="PNG", optimize=False)
        buf.seek(0)

        st.image(result, caption="Image reconstituée", use_container_width=True)

        st.download_button(
            label="Télécharger le PNG",
            data=buf,
            file_name="image_iiif.png",
            mime="image/png",
        )

    except Exception as e:
        st.error(f"Erreur : {e}")
