import re
import unicodedata
import pandas as pd
import streamlit as st
from docx import Document

st.set_page_config(page_title="Incisos 1 y 2 · Especificación", page_icon="📄", layout="centered")
st.title("Especificación · Incisos 1 (Descripción) y 2 (Composición)")

# ---------------- Utils ----------------
def nrm(s: str) -> str:
    s = "" if s is None else str(s).strip()
    s = "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn")
    s = re.sub(r"\s+", " ", s)
    return s.lower()

def es_titulo_numerado(texto: str) -> bool:
    return bool(re.match(r"^\s*\d+(\.| )", texto or ""))

def extraer_bloque_por_titulo(docx_file, contiene_titulo_norm: str) -> list[str]:
    """Devuelve los párrafos (en orden) del inciso cuyo título normalizado contiene contiene_titulo_norm."""
    doc = Document(docx_file)
    paras = [p.text for p in doc.paragraphs]

    # hallar inicio del inciso por título numerado que contenga el texto buscado
    start_idx = None
    for i, p in enumerate(paras):
        if es_titulo_numerado(p) and contiene_titulo_norm in nrm(p):
            start_idx = i + 1
            break
    if start_idx is None:
        return []

    # recolectar hasta el siguiente título numerado
    out = []
    for p in paras[start_idx:]:
        if es_titulo_numerado(p):
            break
        if p.strip():
            out.append(p.strip())
    return out

# ---- Inciso 1: Descripción del Producto ----
def extraer_descripcion(docx_file) -> str:
    bloque = extraer_bloque_por_titulo(docx_file, "descripcion del producto")
    return " ".join(bloque).strip()

# ---- Inciso 2: Composición e Ingredientes ----
# Acepta formatos: "Ingrediente 35,18%", "Ingrediente: 35.18 %", "Ingrediente - 64", etc.
RE_ITEM = re.compile(
    r"""
    ^\s*
    (?P<ing>.+?)                # nombre ingrediente
    \s*[:\-–]?\s*               # separador opcional
    (?P<pct>\d+(?:[.,]\d+)?)    # número (coma o punto)
    \s*%?                       # % opcional
    \s*$
    """,
    re.VERBOSE
)

def parse_ingredientes(lines: list[str]) -> pd.DataFrame:
    rows = []
    for line in lines:
        # si vienen en una sola línea separados por comas, divide (sin cortar números decimales)
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
    df = pd.DataFrame(rows)
    if not df.empty:
        df = df.drop_duplicates().reset_index(drop=True)
    return df

def extraer_composicion(docx_file) -> pd.DataFrame:
    bloque = extraer_bloque_por_titulo(docx_file, "composicion del producto (%) e ingredientes")
    return parse_ingredientes(bloque), bloque

# ---------------- UI ----------------
archivo = st.file_uploader("📂 Sube la especificación (.docx)", type=["docx"])

if archivo:
    # Inciso 1
    descripcion = extraer_descripcion(archivo)
    st.subheader("1) Descripción del Producto")
    if descripcion:
        df_desc = pd.DataFrame([{"Campo": "Descripción del Producto", "Valor": descripcion}])
        st.table(df_desc)
        st.download_button("⬇️ Descargar descripción (CSV)",
                           data=df_desc.to_csv(index=False).encode("utf-8"),
                           file_name="descripcion_producto.csv",
                           mime="text/csv")
    else:
        st.warning("No se encontró el inciso 'Descripción del Producto'.")

    st.markdown("---")

    # Inciso 2
    st.subheader("2) Composición del Producto (%) e Ingredientes")
    df_comp, bloque_crudo = extraer_composicion(archivo)
    if not df_comp.empty:
        st.table(df_comp)
        st.download_button("⬇️ Descargar composición (CSV)",
                           data=df_comp.to_csv(index=False).encode("utf-8"),
                           file_name="composicion_ingredientes.csv",
                           mime="text/csv")
    else:
        st.warning("No se detectaron pares 'Ingrediente + %' en el inciso 2.")
        with st.expander("Ver texto crudo del inciso 2 para revisar"):
            st.text("\n".join(bloque_crudo) if bloque_crudo else "—")
else:
    st.info("Sube el .docx para extraer los incisos 1 y 2.")
