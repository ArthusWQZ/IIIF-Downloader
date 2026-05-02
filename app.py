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

FORMATS = ["jpg", "png", "gif"]


def fetch_tile(base_url, x, y, w, h, tile_w, tile_h, img_width, img_height, scale_factors):
    """
    Tente de récupérer la tuile à (x, y, w, h) dans les coords sources,
    en essayant chaque scaleFactor dans l'ordre croissant.

    Pour sf=1 : on demande directement la région (x, y, w, h) → output (w, h).
    Pour sf>1 : on demande la tuile parente qui contient (x, y), puis on
                recadre la portion correspondante (upscalée à la taille source).
    """
    for sf in scale_factors:
        try:
            if sf == 1:
                region = f"{x},{y},{w},{h}"
                out_w = w
                crop_box = None  # pas de recadrage nécessaire
            else:
                # Origine de la tuile parente dans la grille sf
                eff_w = tile_w * sf
                eff_h = tile_h * sf
                tx = (x // eff_w) * eff_w
                ty = (y // eff_h) * eff_h
                rw = min(eff_w, img_width - tx)
                rh = min(eff_h, img_height - ty)
                region = f"{tx},{ty},{rw},{rh}"
                out_w = math.ceil(rw / sf)
                # Portion à recadrer dans la tuile parente (en coords sources)
                crop_box = (x - tx, y - ty, x - tx + w, y - ty + h)

            for fmt in FORMATS:
                url = f"{base_url}/{region}/{out_w},/0/default.{fmt}"
                r = requests.get(url, impersonate="chrome", timeout=30)
                if r.status_code != 200:
                    continue

                # Valider que la réponse est bien une image (pas une page HTML d'erreur)
                img = Image.open(BytesIO(r.content))
                img.load()  # Force le décodage complet — lève une exception si corrompu

                if sf > 1 and crop_box is not None:
                    # La tuile parente fait out_w × out_h px pour une région rw × rh source.
                    # On upscale à la taille source pour recadrer proprement.
                    img = img.resize((rw, rh), Image.LANCZOS)
                    img = img.crop(crop_box)

                return img  # succès

        except Exception:
            continue  # tentative suivante (sf ou format)

    return None  # aucun sf n'a fonctionné pour cette tuile


if st.button("Télécharger l'image", disabled=not base_url):
    progress_text = st.empty()
    progress_bar = st.progress(0)

    base_url = base_url.rstrip("/")

    try:
        progress_text.text("Récupération des métadonnées (info.json)…")
        r = requests.get(f"{base_url}/info.json", impersonate="chrome", timeout=30)
        if r.status_code != 200 or not r.text.strip():
            st.error(f"Échec info.json — status {r.status_code}: {r.text[:200]}")
            st.stop()

        info = r.json()
        width, height = info["width"], info["height"]
        tile_info = info["tiles"][0]
        tile_w = tile_info["width"]
        tile_h = tile_info.get("height", tile_w)
        scale_factors = sorted(tile_info.get("scaleFactors", [1]))

        # La grille est toujours calculée en sf=1 (résolution native).
        cols = math.ceil(width / tile_w)
        rows = math.ceil(height / tile_h)
        total = cols * rows

        st.info(
            f"Image {width}×{height} px — "
            f"tuile {tile_w}×{tile_h} px — "
            f"scaleFactors disponibles : {scale_factors} — "
            f"grille {cols}×{rows} = {total} tuiles"
        )

        result = Image.new("RGB", (width, height))
        failed = 0
        done = 0

        for row in range(rows):
            for col in range(cols):
                x = col * tile_w
                y = row * tile_h
                w = min(tile_w, width - x)
                h = min(tile_h, height - y)

                tile = fetch_tile(
                    base_url, x, y, w, h,
                    tile_w, tile_h, width, height,
                    scale_factors,
                )

                if tile is not None:
                    result.paste(tile, (x, y))
                else:
                    failed += 1

                done += 1
                progress_bar.progress(done / total)
                progress_text.text(
                    f"Tuile {done}/{total} — "
                    f"{failed} échec(s)"
                    + (" ⚠️" if failed else "")
                )

        progress_text.text(
            f"Assemblage terminé — {total - failed}/{total} tuiles récupérées."
            + (f" ({failed} tuile(s) manquante(s))" if failed else "")
        )
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