import streamlit as st

st.title("Homologación de Materias Primas")

st.write("""
Esta es una app de prueba 🚀  
Aquí podrás comparar especificaciones técnicas de proveedores.
""")

# Subida de archivos
spec_file = st.file_uploader("📂 Sube la especificación técnica (PDF)", type=["pdf"])
prov_files = st.file_uploader("📂 Sube los documentos del proveedor (PDF)", type=["pdf"], accept_multiple_files=True)

if spec_file and prov_files:
    st.success("Archivos cargados correctamente ✅")
    st.write("👉 Próximo paso: implementar comparación entre requisitos y datos de proveedor")
