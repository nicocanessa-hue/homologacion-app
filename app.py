import streamlit as st
import pandas as pd
from docx import Document
import unicodedata
import re

st.set_page_config(page_title="Inciso 1 · Descripción del Producto", page_icon="📄", layout="centered")
st.title("Inciso 1 · Descripción del Producto")

def nrm(s: str) -> str:
    s = "" if s is None else str(s).strip().lower()
    s = "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn")
    s = re.sub(r"\s+", " ", s)
    return s

def es_titulo_numerado(texto: str) -> bool:
    # líneas que comienzan con "1." / "2." / "3 " etc.
    return bool(re.match(r"^\d+(\.| )", texto.strip()))

def extraer_descripcion(docx_file) -> str:
    doc = Document(docx_file)
    paras = [p.text for p in doc.paragraphs]

    # buscar el párrafo que sea el título 1 y contenga "descripcion del producto"
    start_idx = None
    for i, p in enumerate(paras):
        t = nrm(p)
        if es_titulo_numerado(p) and "descripcion del producto" in t:
            start_idx = i + 1
            break

    if start_idx is None:
        return ""  # no encontrado

    # juntar párrafos hasta el próximo título numerado
    contenido = []
    for p in paras[start_idx:]:
        if es_titulo_numerado(p):  # se acabó la sección 1
            break
        if p.strip():
            contenido.append(p.strip())

    return " ".join(contenido).strip()

archivo = st.file_uploader("📂 Sube la especificación (.docx)", type=["docx"])

if archivo:
    descripcion = extraer_descripcion(archivo)
    if descripcion:
        df = pd.DataFrame([{"Campo": "Descripción del Producto", "Valor": descripcion}])
        st.success("✅ Inciso leído con éxito")
        st.table(df)
    else:
        st.error("⚠️ No se encontró el inciso '1. DESCRIPCIÓN DEL PRODUCTO' en el documento.")
else:
    st.info("Sube el .docx para leer la descripción.")
