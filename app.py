import streamlit as st
import pandas as pd
import docx2txt
import re

# ---------- FUNCIONES GENERALES ----------
def extract_text(file):
    return docx2txt.process(file)

def clean_series(s: pd.Series) -> pd.Series:
    return s.astype(str).str.strip().replace("nan", "")

# ---------- INCISO 1: Descripción ----------
def extraer_descripcion(texto):
    match = re.search(r"1\).*?Descripción del Producto(.*?)(?=\n\d+\)|$)", texto, re.S | re.I)
    return match.group(1).strip() if match else ""

# ---------- INCISO 2: Composición ----------
def extraer_composicion(texto):
    match = re.search(r"2\).*?COMPOSICIÓN DEL PRODUCTO.*?(?=\n\d+\)|$)", texto, re.S | re.I)
    if match:
        block = match.group(0)
        lineas = [l.strip() for l in block.split("\n") if "%" in l]
        data = []
        for linea in lineas:
            partes = re.split(r"\s{2,}|\t", linea)
            if len(partes) >= 2:
                ingrediente = partes[0]
                porcentaje = partes[-1]
                data.append([ingrediente, porcentaje])
        return pd.DataFrame(data, columns=["Ingrediente", "%"])
    return pd.DataFrame()

# ---------- INCISO 3: Organolépticos ----------
def extraer_organolepticos(doc):
    dfs = []
    for t in doc.tables:
        headers = [c.text.strip() for c in t.rows[0].cells]
        if any("OLOR" in h.upper() or "SABOR" in h.upper() for h in headers):
            df = pd.DataFrame([[c.text.strip() for c in r.cells] for r in t.rows[1:]], columns=headers)
            dfs.append(df)
    return dfs

# ---------- INCISO 4: Físico-químicos ----------
def normalize_fisicoquimicos(df: pd.DataFrame) -> pd.DataFrame:
    cols = {c.upper(): c for c in df.columns}
    out = pd.DataFrame()
    out["Parámetro"] = clean_series(df[cols.get("PARÁMETRO", "")]) if "PARÁMETRO" in cols else ""
    out["Mín"] = clean_series(df[cols.get("MIN", "")]) if "MIN" in cols else ""
    out["Target"] = clean_series(df[cols.get("TARGET", "")]) if "TARGET" in cols else ""
    out["Máx"] = clean_series(df[cols.get("MAX", "")]) if "MAX" in cols else ""
    out["Unidad"] = clean_series(df[cols.get("UNIDAD", "")]) if "UNIDAD" in cols else ""
    return out

def extraer_fisicoquimicos(doc):
    dfs = []
    for t in doc.tables:
        headers = [c.text.strip().upper() for c in t.rows[0].cells]
        if any("MIN" in h or "MAX" in h for h in headers):
            df = pd.DataFrame([[c.text.strip() for c in r.cells] for r in t.rows[1:]], columns=headers)
            dfs.append(normalize_fisicoquimicos(df))
    return dfs

# ---------- INCISO 5: Microbiológicos ----------
def normalize_microbiologicos(df: pd.DataFrame) -> pd.DataFrame:
    # Renombrar columnas duplicadas
    df.columns = pd.io.parsers.ParserBase({'names':df.columns})._maybe_dedup_names(df.columns)
    return df

def extraer_microbiologicos(doc):
    dfs = []
    for t in doc.tables:
        headers = [c.text.strip().upper() for c in t.rows[0].cells]
        if any("LÍMITE" in h or "PERIODICIDAD" in h for h in headers):
            df = pd.DataFrame([[c.text.strip() for c in r.cells] for r in t.rows[1:]], columns=headers)
            dfs.append(normalize_microbiologicos(df))
    return dfs

# ---------- INCISO 6: Micotoxinas ----------
def normalize_micotoxinas(df: pd.DataFrame) -> pd.DataFrame:
    out = pd.DataFrame()
    out["Micotoxina"] = clean_series(df.iloc[:,0]) if df.shape[1] > 0 else ""
    out["Límite"] = clean_series(df.iloc[:,1]) if df.shape[1] > 1 else ""

    # unificar número + unidad en la columna Límite
    out["Límite"] = out["Límite"].apply(lambda x: x.strip() if x else "")
    return out

def extraer_micotoxinas(doc):
    dfs = []
    for t in doc.tables:
        headers = [c.text.strip().upper() for c in t.rows[0].cells]
        if "MICOTOXINAS" in "".join(headers):
            df = pd.DataFrame([[c.text.strip() for c in r.cells] for r in t.rows[1:]], columns=headers)
            dfs.append(normalize_micotoxinas(df))
    return dfs

# ---------- STREAMLIT ----------
st.title("Homologación - Extracción de Especificación Técnica")

archivo = st.file_uploader("Sube el archivo .docx", type=["docx"])
if archivo:
    texto = extract_text(archivo)

    # Descripción
    st.header("1) Descripción del producto")
    descripcion = extraer_descripcion(texto)
    st.table(pd.DataFrame([[descripcion]], columns=["Descripción del Producto"]))

    # Composición
    st.header("2) Composición del producto")
    comp = extraer_composicion(texto)
    st.dataframe(comp, use_container_width=True)
    st.download_button("Descargar composición (CSV)", comp.to_csv(index=False), "composicion.csv")

    # Organolépticos
    st.header("3) Parámetros organolépticos")
    doc = docx2txt.process(archivo)  # usamos el doc
    import docx
    doc = docx.Document(archivo)
    org_tabs = extraer_organolepticos(doc)
    for i, df in enumerate(org_tabs, 1):
        st.subheader(f"Tabla organolépticos {i}")
        st.dataframe(df, use_container_width=True)
        st.download_button(f"Descargar organolépticos {i} (CSV)", df.to_csv(index=False), f"org_{i}.csv")

    # Físico-químicos
    st.header("4) Parámetros físico-químicos")
    fisq_tabs = extraer_fisicoquimicos(doc)
    for i, df in enumerate(fisq_tabs, 1):
        st.subheader(f"Tabla físico-químicos {i}")
        st.dataframe(df, use_container_width=True)
        st.download_button(f"Descargar fisicoquímicos {i} (CSV)", df.to_csv(index=False), f"fisq_{i}.csv")

    # Microbiológicos
    st.header("5) Parámetros microbiológicos")
    mic_tabs = extraer_microbiologicos(doc)
    for i, df in enumerate(mic_tabs, 1):
        st.subheader(f"Tabla microbiológicos {i}")
        st.dataframe(df, use_container_width=True)
        st.download_button(f"Descargar microbiológicos {i} (CSV)", df.to_csv(index=False), f"micro_{i}.csv")

    # Micotoxinas
    st.header("6) Micotoxinas")
    micotox_tabs = extraer_micotoxinas(doc)
    for i, df in enumerate(micotox_tabs, 1):
        st.subheader(f"Tabla micotoxinas {i}")
        st.dataframe(df, use_container_width=True)
        st.download_button(f"Descargar micotoxinas {i} (CSV)", df.to_csv(index=False), f"micotox_{i}.csv")
