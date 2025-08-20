import streamlit as st
import pandas as pd
import pdfplumber
import unicodedata

# ==============================
# Utilidades
# ==============================
HEADER_MAP = {
    "variable": ["parametro", "parámetro", "variable", "analito", "análisis", "caracteristica", "characteristic", "item", "test", "descripcion", "description"],
    "criterio": ["especificacion", "especificación", "criterio", "requisito", "limite", "límite", "valor", "spec", "requirement", "limit", "target", "typical"],
    "unidad":   ["unidad", "unidad de medida", "unit", "units", "%", "ppm", "mg/kg", "meses", "months"],
    "min":      ["min", "mínimo", "minimo", "desde", "lower", "min. limit"],
    "max":      ["max", "máximo", "maximo", "hasta", "upper", "max. limit"],
}

def nrm(text):
    if not isinstance(text, str):
        text = "" if text is None else str(text)
    text = text.lower().strip()
    text = "".join(
        c for c in unicodedata.normalize("NFD", text)
        if unicodedata.category(c) != "Mn"
    )
    return text

def make_unique(cols):
    """Evita encabezados duplicados: ['A','A','B'] -> ['A','A_1','B']"""
    seen = {}
    out = []
    for c in cols:
        c = "" if c is None else str(c)
        if c in seen:
            seen[c] += 1
            out.append(f"{c}_{seen[c]}")
        else:
            seen[c] = 0
            out.append(c)
    return out

def best_col_index(cols, synonyms):
    cols_norm = [nrm(c) for c in cols]
    for i, c in enumerate(cols_norm):
        for s in synonyms:
            if nrm(s) in c:
                return i
    return None

def normalize_table(df):
    """
    Devuelve un DataFrame con columnas estandarizadas:
    variable / criterio / unidad / min / max
    (si alguna no existe, se crea vacía)
    """
    if df is None or df.empty:
        return pd.DataFrame(columns=["variable","criterio","unidad","min","max"])

    df = df.copy()
    df.columns = make_unique(df.columns)

    # mapear por similitud
    new_cols = {}
    for key, syns in HEADER_MAP.items():
        idx = best_col_index(list(df.columns), syns)
        if idx is not None:
            new_cols[df.columns[idx]] = key
    df = df.rename(columns=new_cols)

    # crear faltantes
    for c in ["variable","criterio","unidad","min","max"]:
        if c not in df.columns:
            df[c] = ""

    # nos quedamos con las columnas interesadas
    keep = ["variable","criterio","unidad","min","max"]
    df = df[keep]

    # limpiar textos básicos
    for c in ["variable","criterio","unidad"]:
        df[c] = df[c].astype(str).str.strip()

    return df

def read_pdf_tables(uploaded_file):
    """Devuelve lista de DataFrames (todas las tablas del PDF) con encabezado en la primera fila."""
    tables = []
    with pdfplumber.open(uploaded_file) as pdf:
        for page in pdf.pages:
            try:
                raw = page.extract_tables() or []
            except Exception:
                raw = []
            for t in raw:
                if not t or len(t) < 2:  # sin filas/encabezado
                    continue
                header = t[0]
                data = t[1:]
                try:
                    df = pd.DataFrame(data, columns=make_unique(header))
                except Exception:
                    # si el ancho de columnas no calza, intenta construir sin header
                    df = pd.DataFrame(data)
                    df.columns = make_unique(df.columns)
                tables.append(df)
    return tables

# ==============================
# UI
# ==============================
st.title("📑 Homologación de Materias Primas")
st.write("Sube la **especificación técnica** y **documentos del proveedor** (PDF). El sistema intentará mapear tablas y comparar.")

spec_file = st.file_uploader("📘 Especificación técnica (PDF)", type=["pdf"])
prov_files = st.file_uploader("📗 Documentos del proveedor (PDF)", type=["pdf"], accept_multiple_files=True)

if spec_file and prov_files:
    try:
        # ---------- ESPECIFICACIÓN ----------
        spec_tables = read_pdf_tables(spec_file)
        spec_norm = [normalize_table(df) for df in spec_tables]
        spec_df = pd.concat(spec_norm, ignore_index=True) if spec_norm else pd.DataFrame(columns=["variable","criterio","unidad","min","max"])
        # filtra filas sin variable
        spec_df = spec_df[spec_df["variable"].astype(str).str.strip() != ""].reset_index(drop=True)

        st.subheader("📘 Especificación (tablas detectadas)")
        st.dataframe(spec_df if not spec_df.empty else pd.DataFrame({"info":["No se detectaron tablas útiles en la especificación."]}), use_container_width=True)

        # ---------- PROVEEDOR ----------
        prov_all = []
        for f in prov_files:
            p_tabs = read_pdf_tables(f)
            p_norm = [normalize_table(df) for df in p_tabs]
            if p_norm:
                p_df = pd.concat(p_norm, ignore_index=True)
                p_df["fuente"] = f.name
                prov_all.append(p_df)

        prov_df = pd.concat(prov_all, ignore_index=True) if prov_all else pd.DataFrame(columns=["variable","criterio","unidad","min","max","fuente"])
        prov_df = prov_df[prov_df["variable"].astype(str).str.strip() != ""].reset_index(drop=True)

        st.subheader("📗 Proveedor (tablas detectadas)")
        st.dataframe(prov_df if not prov_df.empty else pd.DataFrame({"info":["No se detectaron tablas útiles en documentos de proveedor."]}), use_container_width=True)

        # ---------- COMPARACIÓN SIMPLE ----------
        st.subheader("⚖️ Comparación preliminar (por texto)")
        if spec_df.empty or prov_df.empty:
            st.info("Faltan datos estructurados para comparar. Revisa que los PDFs tengan tablas con columnas claras.")
        else:
            comp_rows = []
            # hacemos un match textual simple: si 'variable' de spec aparece en 'variable' de proveedor
            # (mejorable luego con sinónimos y normalización numérica)
            for _, s in spec_df.iterrows():
                var_s = str(s["variable"]).strip()
                crit_s = str(s["criterio"]).strip()
                uni_s  = str(s["unidad"]).strip()

                mask = prov_df["variable"].astype(str).str.contains(var_s, case=False, na=False)
                found = prov_df[mask]

                if not found.empty:
                    valores = ", ".join((found["criterio"].fillna("").astype(str)).tolist())
                    fuentes = ", ".join((found["fuente"].fillna("").astype(str)).unique().tolist()) if "fuente" in found else ""
                    estado  = "Encontrado"
                else:
                    valores = "—"
                    fuentes = ""
                    estado  = "No encontrado"

                comp_rows.append({
                    "Variable (Especificación)": var_s,
                    "Criterio (Especificación)": crit_s,
                    "Unidad (Especificación)": uni_s,
                    "Valor(es) en Proveedor": valores,
                    "Fuente(s)": fuentes,
                    "Estado": estado
                })

            comp_df = pd.DataFrame(comp_rows)
            st.dataframe(comp_df, use_container_width=True)

            st.download_button(
                "⬇️ Descargar comparación (CSV)",
                data=comp_df.to_csv(index=False).encode("utf-8"),
                file_name="comparacion_preliminar.csv",
                mime="text/csv"
            )

    except Exception as e:
        st.error(f"Error al procesar archivos: {e}")
else:
    st.info("Sube la especificación y al menos un documento de proveedor.")
