import streamlit as st
import pandas as pd
import re
import unicodedata
from collections import defaultdict
from docx import Document

st.title("📄 Lector de Especificaciones Técnicas")

# --- Funciones auxiliares ---

def _nrm(s: str) -> str:
    if s is None: return ""
    s = str(s).strip().lower()
    s = "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn")
    s = re.sub(r"\s+", " ", s)
    return s

def _base_name(col: str) -> str:
    """Quita sufijos _1, _2… y normaliza tildes/espacios."""
    c = _nrm(col)
    c = re.sub(r"_(\d+)$", "", c)         # elimina sufijo _1, _2…
    return c

# Mapa de nombres bonitos
PRETTY = {
    "parametro": "PARÁMETRO",
    "especificacion": "ESPECIFICACIÓN",
    "condicion": "CONDICIÓN",
    "metodo utilizado": "MÉTODO UTILIZADO",
    "periodicidad de control": "PERIODICIDAD DE CONTROL",
    "coa (si/no)": "CoA (Sí/No)",
}

# Sinónimos
CANON = {
    "parametro": ["parametro", "parámetro"],
    "especificacion": ["especificacion", "especificación", "spec", "requisito", "valor"],
    "condicion": ["condicion", "condición"],
    "metodo utilizado": ["metodo utilizado", "metodo", "método", "method"],
    "periodicidad de control": ["periodicidad de control", "frecuencia", "periodicidad"],
    "coa (si/no)": ["coa (si/no)", "coa (sí/no)", "coa", "certificado de analisis"],
}

def _canon_key(base: str) -> str:
    """Devuelve la clave canónica (parametro, especificacion, …) si matchea; si no, usa el base."""
    for key, alts in CANON.items():
        for a in alts:
            if a in base:
                return key
    return base

def coalesce_repeated_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Agrupa columnas por nombre base y hace 'primero no vacío' por fila."""
    if df is None or df.empty:
        return df

    groups = defaultdict(list)
    for col in df.columns:
        base = _canon_key(_base_name(col))
        groups[base].append(col)

    out = pd.DataFrame(index=df.index)
    for base, cols in groups.items():
        if len(cols) == 1:
            out[PRETTY.get(base, cols[0])] = df[cols[0]]
        else:
            merged = df[cols].replace({"": pd.NA}).bfill(axis=1).iloc[:, 0]
            out[PRETTY.get(base, base.upper())] = merged.fillna("")

    # quita columnas completamente vacías
    keep = [c for c in out.columns if out[c].astype(str).str.strip().any()]
    return out[keep]

def read_docx_tables(path: str):
    """Extrae todas las tablas de un .docx como dataframes."""
    doc = Document(path)
    tables = []
    for t in doc.tables:
        data = []
        for row in t.rows:
            data.append([cell.text.strip() for cell in row.cells])
        df = pd.DataFrame(data[1:], columns=data[0])
        tables.append(df)
    return tables

# --- Interfaz Streamlit ---

uploaded_file = st.file_uploader("📂 Sube una especificación técnica (.docx)", type=["docx"])

if uploaded_file:
    try:
        tables = read_docx_tables(uploaded_file)
        if not tables:
            st.error("⚠️ No se detectaron tablas en el documento.")
        else:
            for i, df in enumerate(tables, start=1):
                st.divider()
                st.subheader(f"📊 Tabla {i}")

                # Tabla original
                st.caption("Versión original extraída")
                st.dataframe(df, use_container_width=True)

                # Tabla unificada
                clean_df = coalesce_repeated_columns(df)
                st.caption("✅ Versión unificada (sin duplicados)")
                st.dataframe(clean_df, use_container_width=True)

                # Descarga
                st.download_button(
                    f"⬇️ Descargar Tabla {i} unificada (CSV)",
                    data=clean_df.to_csv(index=False).encode("utf-8"),
                    file_name=f"tabla_{i}_unificada.csv",
                    mime="text/csv",
                    key=f"dl_clean_{i}"
                )

    except Exception as e:
        st.error(f"Error leyendo el DOCX: {e}")
