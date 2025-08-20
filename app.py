import streamlit as st
import pandas as pd
import docx

# ------------------------
# Funciones auxiliares
# ------------------------

def extraer_texto(doc, inicio):
    """Extrae el párrafo de un inciso que parte con una palabra clave"""
    for p in doc.paragraphs:
        if p.text.strip().startswith(inicio):
            return p.text.replace(inicio, "").strip()
    return ""

def extraer_composicion(doc, inicio="COMPOSICIÓN DEL PRODUCTO"):
    """Extrae lista de ingredientes con % desde un inciso"""
    composicion = []
    grabar = False
    for p in doc.paragraphs:
        if inicio in p.text:
            grabar = True
            continue
        if grabar:
            if p.text.strip() == "":
                break
            if "%" in p.text:
                partes = p.text.split("%")
                ingrediente = partes[0].strip(" -:\n\t")
                porcentaje = partes[1].strip() if len(partes) > 1 else ""
                composicion.append({"Ingrediente": ingrediente, "%": porcentaje})
    return pd.DataFrame(composicion)

def extraer_tabla(doc, indice):
    """Devuelve una tabla de Word como DataFrame"""
    tabla = doc.tables[indice]
    data = []
    keys = None
    for i, row in enumerate(tabla.rows):
        text = [cell.text.strip() for cell in row.cells]
        if i == 0:
            keys = text
        else:
            data.append(text)
    return pd.DataFrame(data, columns=keys)

# ------------------------
# Normalizadores
# ------------------------

def normalize_fisicoquimicos(df: pd.DataFrame) -> pd.DataFrame:
    """Normaliza tabla de parámetros físico-químicos"""
    out = pd.DataFrame()
    cols = [c.lower() for c in df.columns]

    # Buscar columnas clave
    c_param = [c for c in df.columns if "parámetro" in c.lower()]
    c_min = [c for c in df.columns if "mín" in c.lower()]
    c_target = [c for c in df.columns if "target" in c.lower() or "objetivo" in c.lower()]
    c_max = [c for c in df.columns if "máx" in c.lower()]
    c_unid = [c for c in df.columns if "unidad" in c.lower()]

    out["PARÁMETRO"] = df[c_param[0]] if c_param else ""
    out["MIN"] = df[c_min[0]] if c_min else ""
    out["TARGET"] = df[c_target[0]] if c_target else ""
    out["MAX"] = df[c_max[0]] if c_max else ""
    out["UNIDAD"] = df[c_unid[0]] if c_unid else ""

    return out

def normalize_microbiologicos(df: pd.DataFrame) -> pd.DataFrame:
    """Normaliza tabla de parámetros microbiológicos"""
    # Renombrar columnas explícitamente
    cols = list(df.columns)
    mapping = {}
    for c in cols:
        cl = c.lower()
        if "n" == cl: mapping[c] = "n"
        elif cl == "c": mapping[c] = "c"
        elif cl == "m": mapping[c] = "m"
        elif "m;" in cl or cl == "m.1": mapping[c] = "M"
        elif "método" in cl: mapping[c] = "MÉTODO DE ANÁLISIS"
        elif "límite" in cl: mapping[c] = "LÍMITE"
        elif "periodicidad" in cl: mapping[c] = "PERIODICIDAD DE CONTROL"
    df = df.rename(columns=mapping)
    return df

# ------------------------
# App Streamlit
# ------------------------

st.title("Extractor de Especificación Técnica")

archivo = st.file_uploader("Sube un archivo DOCX", type=["docx"])

if archivo:
    doc = docx.Document(archivo)

    # 1. Descripción del producto
    descripcion = extraer_texto(doc, "DESCRIPCIÓN DEL PRODUCTO")
    st.subheader("1) Descripción del producto")
    st.table(pd.DataFrame([{"Descripción del Producto": descripcion}]))

    # 2. Composición
    st.subheader("2) Composición del producto (%) e ingredientes")
    comp_df = extraer_composicion(doc)
    st.table(comp_df)
    st.download_button("Descargar composición (CSV)", comp_df.to_csv(index=False), "composicion.csv")

    # 3. Parámetros organolépticos
    st.subheader("3) Parámetros organolépticos (tabla)")
    organo_df = extraer_tabla(doc, 0)
    st.table(organo_df)
    st.download_button("Descargar organolépticos (CSV)", organo_df.to_csv(index=False), "organolepticos.csv")

    # 4. Parámetros físico-químicos
    st.subheader("4) Parámetros físico-químicos (tabla)")
    fisq_df = extraer_tabla(doc, 1)
    fisq_norm = normalize_fisicoquimicos(fisq_df)
    st.table(fisq_norm)
    st.download_button("Descargar físico-químicos (CSV)", fisq_norm.to_csv(index=False), "fisicoquimicos.csv")

    # 5. Parámetros microbiológicos
    st.subheader("5) Parámetros microbiológicos (tabla)")
    micro_df = extraer_tabla(doc, 2)
    micro_norm = normalize_microbiologicos(micro_df)
    st.table(micro_norm)
    st.download_button("Descargar microbiológicos (CSV)", micro_norm.to_csv(index=False), "microbiologicos.csv")
