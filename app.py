import streamlit as st
import pandas as pd
from docx import Document

st.set_page_config(page_title="Lector de Especificación (DOCX)", page_icon="📄", layout="wide")
st.title("Paso 1 · Leer una especificación .docx (texto + tablas)")

archivo = st.file_uploader("📂 Sube la especificación en Word (.docx)", type=["docx"])

def leer_docx(docx_file):
    doc = Document(docx_file)

    # 1) Texto (párrafos)
    parrafos = [p.text.strip() for p in doc.paragraphs if p.text and p.text.strip()]

    # 2) Tablas
    tablas = []
    for t in doc.tables:
        filas = []
        for r in t.rows:
            celdas = []
            for c in r.cells:
                # Tomamos todo el texto de la celda (líneas unidas y limpiadas)
                txt = " ".join([p.text for p in c.paragraphs]).strip()
                txt = " ".join(txt.split())  # colapsa espacios y saltos de línea
                celdas.append(txt)
            filas.append(celdas)

        # Normalizamos filas con distinta cantidad de columnas
        max_cols = max(len(f) for f in filas) if filas else 0
        filas = [f + [""] * (max_cols - len(f)) for f in filas]

        # Heurística: usar primera fila como encabezado si parece “título”
        use_header = False
        if filas and len(filas) > 1:
            # Si la primera fila tiene texto “diferente” al resto (más palabras o sin números), asumimos header
            first_row = " ".join(filas[0]).lower()
            use_header = True if len(first_row) > 0 else False

        if use_header:
            df = pd.DataFrame(filas[1:], columns=filas[0])
        else:
            df = pd.DataFrame(filas)

        tablas.append(df)

    return parrafos, tablas

if archivo:
    st.success("✅ Archivo cargado")

    try:
        parrafos, tablas = leer_docx(archivo)

        # Mostrar texto
        st.subheader("📝 Texto (párrafos)")
        st.write(f"Se detectaron **{len(parrafos)}** párrafos.")
        with st.expander("Ver texto"):
            for i, p in enumerate(parrafos, start=1):
                st.markdown(f"**{i}.** {p}")

        # Mostrar tablas
        st.subheader("📊 Tablas")
        st.write(f"Se detectaron **{len(tablas)}** tablas.")
        if not tablas:
            st.info("No se detectaron tablas en este .docx.")
        for i, df in enumerate(tablas, start=1):
            st.caption(f"Tabla {i}")
            st.dataframe(df, use_container_width=True)

            # Permitir elegir si la 1ª fila es encabezado (por si la heurística falló)
            with st.expander(f"¿La primera fila es encabezado? (opción manual) · Tabla {i}"):
                if st.checkbox(f"Usar 1ª fila como encabezado (Tabla {i})", value=False, key=f"hdr_{i}"):
                    if len(df) > 1:
                        new_df = df.iloc[1:].copy()
                        new_df.columns = df.iloc[0].tolist()
                        st.dataframe(new_df, use_container_width=True)

            # Descarga CSV
            st.download_button(
                label=f"⬇️ Descargar Tabla {i} (CSV)",
                data=df.to_csv(index=False).encode("utf-8"),
                file_name=f"tabla_{i}.csv",
                mime="text/csv",
                key=f"dl_{i}"
            )

    except Exception as e:
        st.error(f"Error leyendo el DOCX: {e}")

else:
    st.info("Sube un archivo .docx para comenzar.")
