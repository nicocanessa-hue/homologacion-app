import streamlit as st
import pandas as pd
import pdfplumber
import unicodedata

# ==============================
# 1) Normalización y utilidades
# ==============================
HEADER_MAP = {
    "variable": ["parametro", "variable", "análisis", "analito", "compound"],
    "criterio": ["especificación", "criterio", "requisito", "limite", "valor"],
    "unidad": ["unidad", "unidad de medida", "%", "mg/kg", "meses"],
    "min": ["min", "mínimo", "desde", "lower"],
    "max": ["max", "máximo", "hasta", "upper"],
}

def nrm(text):
    """Normaliza texto: minúsculas, sin tildes"""
    if not isinstance(text, str):
        return ""
    text = text.lower().strip()
    text = "".join(
        c for c in unicodedata.normalize("NFD", text)
        if unicodedata.category(c) != "Mn"
    )
    return text

def best_col_index(cols, synonyms):
    """Detecta cuál columna coincide mejor con un grupo de sinónimos"""
    cols_norm = [nrm(c) for c in cols]
    for i, c in enumerate(cols_norm):
        for s in synonyms:
            if nrm(s) in c:
                return i
    return None

def extract_table_schema_first(df):
    """Renombra columnas de un DataFrame según HEADER_MAP"""
    if df.empty:
        return df

    new_cols = {}
    for key, synonyms in HEADER_MAP.items():
        idx = best_col_index(df.columns, synonyms)
        if idx is not None:
            new_cols[df.columns[idx]] = key

    df.rename(columns=new_cols, inplace=True)
    return df

# ==============================
# 2) Lector de PDFs
# ==============================
def read_pdf_tables(uploaded_file):
    tables = []
    with pdfplumber.open(uploaded_file) as pdf:
        for page in pdf.pages:
            page_tables = page.extract_tables()
            for t in page_tables:
                df = pd.DataFrame(t[1:], columns=t[0])  # primera fila = encabezado
                tables.append(df)
    return tables

# ==============================
# 3) Streamlit UI
# ==============================
st.title("📑 Homologación de Materias Primas")
st.write("Sube la especificación técnica y los documentos del proveedor para compararlos.")

# Subir archivos
spec_file = st.file_uploader("📘 Sube la especificación técnica (PDF)", type=["pdf"])
prov_files = st.file_uploader("📗 Sube documentos del proveedor (PDF)", type=["pdf"], accept_multiple_files=True)

if spec_file and prov_files:
    try:
        # Leer especificación
        spec_tables = read_pdf_tables(spec_file)
        spec_df = extract_table_schema_first(spec_tables[0]) if spec_tables else pd.DataFrame()

        # Leer proveedores
        prov_dfs = []
        for f in prov_files:
            tables = read_pdf_tables(f)
            if tables:
                df = extract_table_schema_first(tables[0])
                prov_dfs.append(df)

        # Combinar proveedores
        prov_df = pd.concat(prov_dfs, ignore_index=True) if prov_dfs else pd.DataFrame()

        st.subheader("📘 Especificación Técnica (procesada)")
        st.dataframe(spec_df)

        st.subheader("📗 Datos del Proveedor (procesados)")
        st.dataframe(prov_df)

        # ==============================
        # 4) Comparación simple
        # ==============================
        if not spec_df.empty and not prov_df.empty:
            st.subheader("⚖️ Comparación preliminar")
            comparison = []
            for _, row in spec_df.iterrows():
                var = row.get("variable", "")
                criterio = row.get("criterio", "")
                unidad = row.get("unidad", "")

                # Buscar en proveedores
                mask = prov_df["variable"].astype(str).str.contains(str(var), case=False, na=False) if "variable" in prov_df else []
                match = prov_df[mask] if any(mask) else pd.DataFrame()

                if not match.empty:
                    comparison.append({
                        "variable": var,
                        "criterio_esp": criterio,
                        "unidad_esp": unidad,
                        "proveedor_valores": ", ".join(match["criterio"].astype(str).tolist()) if "criterio" in match else "Sin criterio"
                    })
                else:
                    comparison.append({
                        "variable": var,
                        "criterio_esp": criterio,
                        "unidad_esp": unidad,
                        "proveedor_valores": "❌ No encontrado"
                    })

            comp_df = pd.DataFrame(comparison)
            st.dataframe(comp_df)

    except Exception as e:
        st.error(f"Error al procesar archivos: {e}")
