import streamlit as st
import pandas as pd
import fitz  # PyMuPDF

st.set_page_config(page_title="Extractor de Especificaciones Técnicas", layout="wide")
st.title("📄 Extractor de Parámetros Técnicos desde PDF")

# Función para limpiar texto
def clean(text):
    return text.strip().replace("\n", " ").replace("\r", "").replace("  ", " ")

# Función para extraer parámetros desde texto
def extraer_parametros(texto):
    lines = texto.splitlines()
    secciones_clave = [
        "PARÁMETROS ORGANOLÉPTICOS",
        "PARÁMETROS FÍSICO-QUÍMICOS",
        "PARÁMETROS MICROBIOLÓGICOS",
        "MICOTOXINAS",
        "METALES PESADOS",
        "INFORMACIÓN NUTRICIONAL",
        "PERFIL DE AMINOÁCIDOS",
        "VIDA ÚTIL",
        "ENVASE Y EMBALAJE"
    ]
    current_section = None
    parametros = []

    for line in lines:
        line = clean(line)
        if any(sec in line for sec in secciones_clave):
            current_section = line
            continue

        if current_section and line:
            if any(keyword in line.lower() for keyword in ["%", "mg", "ppb", "°c", "g", "kcal", "ufc", "nmp", "meses", "cada lote", "anual"]):
                nombre = line.split()[0]
                resto = " ".join(line.split()[1:]) if len(line.split()) > 1 else ""

                nums = [t for t in line.split() if any(c.isdigit() for c in t)]
                min_val, target_val, max_val = (nums + [None]*3)[:3]

                unidad = next((u for u in ["%", "mg/kg", "ppb", "°C", "g", "kcal", "ufc/g", "NMP/g", "meses"] if u in line), None)
                metodo = next((m for m in ["IOCCC", "AOAC", "ISO", "Visual", "Sensorial", "Balanza", "Viscosímetro", "CQ-CROM", "Elisa"] if m.lower() in line.lower()), None)
                frecuencia = "Cada lote" if "cada lote" in line.lower() else "Anual" if "anual" in line.lower() else None
                coa = "Sí" if "SI" in line.upper() else "No" if "NO" in line.upper() else None

                parametros.append({
                    "Sección": current_section,
                    "Parámetro": nombre,
                    "Mínimo": min_val,
                    "Target": target_val,
                    "Máximo": max_val,
                    "Unidad": unidad,
                    "Método": metodo,
                    "Frecuencia": frecuencia,
                    "CoA": coa,
                    "Texto completo": line
                })

    return pd.DataFrame(parametros)

# Subida de archivo
pdf_file = st.file_uploader("📎 Sube la especificación técnica en PDF", type=["pdf"])

if pdf_file:
    st.success("PDF cargado correctamente ✅")

    # Leer PDF con PyMuPDF
    doc = fitz.open(stream=pdf_file.read(), filetype="pdf")
    full_text = ""
    for page in doc:
        full_text += page.get_text()

    # Extraer parámetros
    df = extraer_parametros(full_text)

    st.subheader("📋 Parámetros extraídos")
    st.dataframe(df, use_container_width=True)

    # Descargar como Excel
    output = pd.ExcelWriter("parametros_extraidos.xlsx", engine="openpyxl")
    df.to_excel(output, index=False)
    output.close()

    with open("parametros_extraidos.xlsx", "rb") as f:
        st.download_button("📥 Descargar como Excel", f, file_name="parametros_extraidos.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

else:
    st.info("Por favor, sube un archivo PDF para comenzar.")

