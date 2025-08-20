import streamlit as st
import pandas as pd
import pdfplumber
import camelot
import io
import tempfile
from rapidfuzz import fuzz

# Diccionario de sinónimos
SINONIMOS = {
    "humedad": ["moisture", "% H2O", "agua libre"],
    "color": ["color", "appearance", "visual"],
    "peso de moneda": ["peso", "weight", "coin weight"],
    "sabor": ["flavor", "taste"],
    "aroma": ["smell", "odor"],
    "textura": ["texture", "mouthfeel"],
    "vida útil": ["shelf life", "durability"],
    "empaque": ["packaging", "container"],
    "certificación": ["certification", "HACCP", "ISO"],
    "cacao": ["cocoa", "% cacao", "cacao content"],
    "aflatoxina": ["aflatoxin"],
    "plomo": ["lead", "Pb"],
    "cobre": ["copper", "Cu"],
    "selenio": ["selenium", "Se"],
    "zinc": ["Zn", "zinc"],
    "salmonella": ["salmonella"],
    "e. coli": ["e. coli", "escherichia coli"]
}

# Función para extraer texto con pdfplumber
def extract_text_pdfplumber(uploaded_file):
    text = ""
    with pdfplumber.open(uploaded_file) as pdf:
        for page in pdf.pages:
            text += page.extract_text() or ""
    return text

# Función para extraer tablas con camelot
def extract_tables_camelot(uploaded_file):
    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp_file:
        tmp_file.write(uploaded_file.read())
        tmp_file.flush()
        tables = camelot.read_pdf(tmp_file.name, pages='all', flavor='stream')
        dfs = [table.df for table in tables]
    return dfs

# Función para normalizar texto
def normalizar_variable(texto):
    texto = texto.lower()
    for clave, sinonimos in SINONIMOS.items():
        for sin in sinonimos:
            if fuzz.partial_ratio(sin.lower(), texto) > 80:
                return clave
    return texto

# Función para extraer parámetros clave desde texto
def extraer_parametros(texto):
    parametros = {}
    for linea in texto.splitlines():
        linea = linea.strip()
        if not linea:
            continue
        for clave in SINONIMOS.keys():
            if clave in normalizar_variable(linea):
                parametros[clave] = linea
    return parametros

# Función para extraer parámetros desde tablas
def extraer_parametros_tablas(dfs):
    parametros = {}
    for df in dfs:
        for _, row in df.iterrows():
            for cell in row:
                if isinstance(cell, str):
                    clave = normalizar_variable(cell)
                    if clave in SINONIMOS:
                        parametros[clave] = cell
    return parametros

# Función para comparar requisitos
def comparar(requisitos, proveedor):
    comparativa = []
    for clave, valor_req in requisitos.items():
        valor_prov = proveedor.get(clave, "No encontrado")
        cumple = "No"
        if valor_prov != "No encontrado":
            if fuzz.partial_ratio(valor_req.lower(), valor_prov.lower()) > 70:
                cumple = "Sí"
        comparativa.append({
            "Parámetro": clave,
            "Evaluación Técnica": valor_req,
            "Proveedor": valor_prov,
            "Cumple": cumple
        })
    return pd.DataFrame(comparativa)

# Interfaz Streamlit
st.set_page_config(page_title="Comparador Técnico", layout="wide")
st.title("📊 Comparador de Evaluación Técnica vs Documentos del Proveedor")

st.sidebar.header("📁 Subida de Archivos")
eval_file = st.sidebar.file_uploader("Sube la especificación técnica (PDF)", type=["pdf"])
prov_files = st.sidebar.file_uploader("Sube los documentos del proveedor (PDF)", type=["pdf"], accept_multiple_files=True)

if eval_file and prov_files:
    st.success("Archivos cargados correctamente ✅")

    # Extraer texto y tablas de evaluación técnica
    texto_eval = extract_text_pdfplumber(eval_file)
    eval_file.seek(0)
    tablas_eval = extract_tables_camelot(eval_file)
    requisitos = extraer_parametros(texto_eval)
    requisitos.update(extraer_parametros_tablas(tablas_eval))

    # Extraer texto y tablas de proveedor
    proveedor = {}
    for f in prov_files:
        texto_prov = extract_text_pdfplumber(f)
        f.seek(0)
        tablas_prov = extract_tables_camelot(f)
        proveedor.update(extraer_parametros(texto_prov))
        proveedor.update(extraer_parametros_tablas(tablas_prov))

    # Comparar
    resultado = comparar(requisitos, proveedor)

    st.subheader("📋 Resultado de la Comparación")
    st.dataframe(resultado, use_container_width=True)

    # Descargar como Excel
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        resultado.to_excel(writer, index=False, sheet_name='Comparación')
    st.download_button("📥 Descargar resultado en Excel", data=output.getvalue(), file_name="comparacion_resultado.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

else:
    st.info("Por favor, sube los archivos para comenzar la comparación.")

    
