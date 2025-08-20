import re
import unicodedata
import pandas as pd
import streamlit as st
from docx import Document

st.set_page_config(page_title="Inciso 2 · Composición e Ingredientes", page_icon="🍫", layout="centered")
st.title("Inciso 2 · Composición del Producto (%) e Ingredientes")

def nrm(s: str) -> str:
    s = "" if s is None else str(s).strip()
    s = "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn")
    return s

def es_titulo_numerado(texto: str) -> bool:
    return bool(re.match(r"^\s*\d+(\.| )", texto or ""))

def extraer_bloque(docx_file, titulo_busqueda_norm: str) -> list[str]:
    """Devuelve los párrafos (en orden) del inciso cuyo título normalizado contiene titulo_busqueda_norm."""
    doc = Document(docx_file)
    paras = [p.text for p in doc.paragraphs]

    # hallar inicio del inciso por título numerado que contenga el texto buscado
    start_idx = None
    for i, p in enumerate(paras):
        t = nrm(p).lower()
        if es_titulo_numerado(p) and titulo_busqueda_norm in t:
            start_idx = i + 1
            break
    if start_idx is None:
        return []

    # recolectar hasta el siguiente inciso
    out = []
    for p in paras[start_idx:]:
        if es_titulo_numerado(p):
            break
        if p.strip():
            out.append(p.strip())
    return out

# Regex robusta: "Ingrediente ... 35,18%" / "Ingrediente: 35.18 %" / "Ingrediente - 64"
RE_ITEM = re.compile(
    r"""
    ^\s*
    (?P<ing>.+?)                # nombre ingrediente (perezoso)
    \s*[:\-–]?\s*               # separador opcional (: - –)
    (?P<pct>\d+(?:[.,]\d+)?)    # número (coma o punto)
    \s*%?                       # símbolo % opcional
    \s*$
    """,
    re.VERBOSE
)

def parse_ingredientes(lines: list[str]) -> pd.DataFrame:
    rows = []
    for line in lines:
        # dividir por comas si viene todo en una línea
        parts = [p.strip() for p in re.split(r",(?!\d)", line) if p.strip()]
        for p in parts:
            m = RE_ITEM.match(p)
            if m:
                ing = m.group("ing").strip()
                pct_raw = m.group("pct").replace(",", ".")
                try:
                    pct = float(pct_raw)
                except:
                    pct = None
                rows.append({"Ingrediente": ing, "%": pct})
    # quitar duplicados y vacíos
    df = pd.DataFrame(rows)
    if not df.empty:
        df = df.drop_duplicates().reset_index(drop=True)
    return df

archivo = st.file_uploader("📂 Sube la especificación (.docx)", type=["docx"])

if archivo:
    # busca el inciso 2 por texto normalizado (ajusta si tu título exacto varía)
    titulo_norm = "2. composicion del producto (%) e ingredientes".lower().replace("á","a").replace("í","i").replace("ó","o").replace("é","e").replace("ú","u")
    bloque = extraer_bloque(archivo, "composicion del producto (%) e ingredientes")

    if not bloque:
        st.error("⚠️ No encontré el inciso 2. Revisa que el título sea tipo: '2. COMPOSICIÓN DEL PRODUCTO (%) E INGREDIENTES'.")
    else:
        df = parse_ingredientes(bloque)
        if df.empty:
            st.warning("Leí el bloque, pero no pude detectar 'Ingrediente + %'. ¿Está escrito como 'Nombre : 35,18%'? Sube una captura de ejemplo si no.")
            st.text("\n".join(bloque))
        else:
            st.success("✅ Inciso 2 leído y parseado")
            st.table(df)
            st.download_button("⬇️ Descargar composición (CSV)",
                               data=df.to_csv(index=False).encode("utf-8"),
                               file_name="composicion_ingredientes.csv",
                               mime="text/csv")
else:
    st.info("Sube el .docx para extraer los ingredientes y sus porcentajes.")
