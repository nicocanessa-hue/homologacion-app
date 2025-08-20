import streamlit as st
import docx

def extraer_especificacion(path):
    doc = docx.Document(path)
    data = {}
    current_title = None
    content = []

    for para in doc.paragraphs:
        text = para.text.strip()
        if not text:
            continue

        # Detectar títulos numerados (ej: "3. Parámetros organolépticos")
        if text[0].isdigit() and "." in text[:4]:
            if current_title:  # Guardar lo anterior
                data[current_title] = "\n".join(content).strip()
                content = []
            current_title = text
        else:
            content.append(text)

    # Guardar el último bloque
    if current_title and content:
        data[current_title] = "\n".join(content).strip()

    return data

# ----------------- STREAMLIT APP -----------------
st.title("Extractor de Especificación Técnica")

archivo = st.file_uploader("📂 Sube un archivo .docx con la especificación", type=["docx"])

if archivo is not None:
    st.success("✅ Archivo cargado con éxito")
    datos = extraer_especificacion(archivo)

    st.subheader("📋 Bloques extraídos de la especificación:")
    for titulo, contenido in datos.items():
        st.markdown(f"### {titulo}")
        st.write(contenido)
