import streamlit as st
import pandas as pd
import re, unicodedata
from collections import defaultdict
from docx import Document

st.set_page_config(page_title="Lector de Especificaciones", page_icon="📄", layout="wide")
st.title("📄 Lector de Especificaciones Técnicas (.docx)")

# ---------- helpers ----------
def make_unique(cols):
    """['A','A','B'] -> ['A','A_1','B']"""
    seen = {}
    out = []
    for c in cols:
        c = "" if c is None else str(c).strip()
        if c in seen:
            seen[c] += 1
            out.append(f"{c}_{seen[c]}")
        else:
            seen[c] = 0
            out.append(c)
    return out

def _nrm(s: str) -> str:
    if s is None: return ""
    s = str(s).strip().lower()
    s = "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn")
    s = re.sub(r"\s+", " ", s)
    return s

def _base_name(col: str) -> str:
    c = _nrm(col)
    c = re.sub(r"_(\d+)$", "", c)  # quita sufijo _1, _2…
    return c

PRETTY = {
    "parametro": "PARÁMETRO",
    "especificacion": "ESPECIFICACIÓN",
    "condicion": "CONDICIÓN",
    "metodo utilizado": "MÉTODO UTILIZADO",
    "periodicidad de control": "PERIODICIDAD DE CONTROL",
    "coa (si/no)": "CoA (Sí/No)",
}
CANON = {
    "parametro": ["parametro", "parámetro"],
    "especificacion": ["especificacion", "especificación", "spec", "requisito", "valor"],
    "condicion": ["condicion", "condición"],
    "metodo utilizado": ["metodo utilizado", "metodo", "método", "method"],
    "periodicidad de control": ["periodicidad de control", "frecuencia", "periodicidad"],
    "coa (si/no)": ["coa (si/no)", "coa (sí/no)", "coa", "certificado de analisis"],
}
def _canon_key(base: str) -> str:
    for key, alts in CANON.items():
        for a in alts:
            if a in base:
                return key
    return base

def coalesce_repeated_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Agrupa columnas por nombre base y toma el primer valor no vacío por fila."""
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
    keep = [c for c in out.columns if out[c].astype(str).str.strip().any()]
    return out[keep]

def read_docx_tables(file):
    """Extrae todas las tablas del .docx como DataFrames; corrige encabezados duplicados y largos desiguales."""
    doc = Document(file)
    tables = []
    for t in doc.tables:
        rows = []
        for r in t.rows:
            cells = []
            for c in r.cells:
                txt = " ".join(p.text for p in c.paragraphs).strip()
                txt = " ".join(txt.split())
                cells.append(txt)
            rows.append(cells)
        if not rows:  # tabla vacía
            continue

        # normaliza número de columnas por fila
        max_cols = max(len(r) for r in rows)
        rows = [r + [""] * (max_cols - len(r)) for r in rows]

        # header seguro y ÚNICO
        header = make_unique(rows[0])
        body = rows[1:] if len(rows) > 1 else []

        # construye DataFrame incluso con duplicados (ya únicos)
        df = pd.DataFrame(body, columns=header) if body else pd.DataFrame(columns=header)
        tables.append(df)
    return tables

# ---------- UI ----------
docx_file = st.file_uploader("📂 Sube la especificación (.docx)", type=["docx"])

if docx_file:
    try:
        tdfs = read_docx_tables(docx_file)
        if not tdfs:
            st.warning("No se detectaron tablas en el documento.")
        for i, raw_df in enumerate(tdfs, start=1):
            st.divider()
            st.subheader(f"📊 Tabla {i}")

            st.caption("Versión original (encabezados ya únicos)")
            st.dataframe(raw_df, use_container_width=True)

            st.caption("✅ Versión unificada (dup. combinados)")
            clean = coalesce_repeated_columns(raw_df)
            st.dataframe(clean, use_container_width=True)

            st.download_button(
                f"⬇️ Descargar Tabla {i} unificada (CSV)",
                data=clean.to_csv(index=False).encode("utf-8"),
                file_name=f"tabla_{i}_unificada.csv",
                mime="text/csv",
                key=f"dl_clean_{i}"
            )
    except Exception as e:
        st.error(f"Error leyendo el DOCX: {e}")
else:
    st.info("Sube un .docx para comenzar.")
