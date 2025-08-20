import streamlit as st
import pandas as pd
from docx import Document

st.set_page_config(page_title="Lector de Especificación (DOCX)", page_icon="📄", layout="wide")
st.title("Paso 1 · Leer una especificación .docx (texto + tablas)")

archivo = st.file_uploader("📂 Sube la especificación en Word (.docx)", type=["docx"])

def make_unique(cols):
    """Evita encabezados duplicados: ['A','A','B'] -> ['A','A_1','B']"""
    seen = {}
    unique = []
    for c in cols:
        c = "" if c is None else str(c).strip()
        if c in seen:
            seen[c] += 1
            unique.append(f"{c}_{seen[c]}")
        else:
            seen[c] = 0
            unique.append(c)
    return unique

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
                txt = " ".join(p.text for p in c.paragraphs).strip()
                txt = " ".join(txt.split())  # colapsar espacios/saltos
                celdas.append(txt)
            filas.append(celdas)

        if not filas:
            continue

        # Normalizar largo de filas (relleno con "")
        max_cols = max(len(f) for f in filas)
        filas = [f + [""] * (max_cols - len(f)) for f in filas]

        # Heurística simple: usar 1ª fila como encabezado
        header = [str(x).strip() for x in filas[0]]
        header_unique = make_unique(header)  # <<< CLAVE: volver únicos los encabezados
        body = filas[1:] if len(filas) > 1 else []

        if body:
            df = pd.DataFrame(body, columns=header_unique)
        else:
            # Si solo hay 1 fila, igual devolvemos algo
            df = pd.DataFrame(columns=header_unique)

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

            # Opción manual: volver a aplicar encabezado con la 1ª fila del cuerpo
            with st.expander(f"¿La primera fila REAL es la 2ª del archivo? (ajustar encabezado) · Tabla {i}"):
                if st.checkbox(f"Usar segunda fila como encabezado (Tabla {i})", key=f"use_second_header_{i}"):
                    if len(df) > 1:
                        # Construir nuevo header con la primera fila actual de datos
                        new_header = make_unique([str(x).strip() for x in df.iloc[0].tolist()])
                        new_df = df.iloc[1:].copy()
                        new_df.columns = new_header
                        st.dataframe(new_df, use_container_width=True)
                        # Botón de descarga de la versión ajustada
                        st.download_button(
                            label=f"⬇️ Descargar Tabla {i} (CSV) con encabezado ajustado",
                            data=new_df.to_csv(index=False).encode("utf-8"),
                            file_name=f"tabla_{i}_ajustada.csv",
                            mime="text/csv",
                            key=f"dl_adj_{i}"
                        )

            # Descarga CSV de la versión base
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
