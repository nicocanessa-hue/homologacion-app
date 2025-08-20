import re
import pdfplumber
import pandas as pd
import streamlit as st
from unidecode import unidecode

st.set_page_config(page_title="Homologación MP", page_icon="🧪", layout="wide")
st.title("Homologación de Materias Primas")

st.write("Sube una **Especificación** y uno o más **PDFs de proveedor**. El sistema extrae valores clave y compara.")

# -----------------------
# Utilidades simples
# -----------------------
def norm(s: str) -> str:
    return " ".join(unidecode((s or "").lower()).split())

def read_pdf_text_and_tables(file):
    text_parts, table_rows = [], []
    with pdfplumber.open(file) as pdf:
        for p in pdf.pages:
            text_parts.append(p.extract_text() or "")
            try:
                for tb in (p.extract_tables() or []):
                    # tb = list of rows (list of cells)
                    for row in tb:
                        if any(c and str(c).strip() for c in row):
                            table_rows.append([str(c or "").strip() for c in row])
            except:
                pass
    return "\n".join(text_parts), table_rows

# Reglas: qué campos buscamos y con qué patrones (muy básico pero útil)
FIELDS = {
    "Humedad (%)": [
        r"humedad[^0-9]{0,15}([0-9]+[.,][0-9]+|[0-9]+)\s*%|moisture[^0-9]{0,15}([0-9]+[.,][0-9]+|[0-9]+)\s*%"
    ],
    "% Cacao": [
        r"(?:%?\s*cacao|cocoa)\D{0,10}([0-9]+[.,][0-9]+|[0-9]+)\s*%|cocoa\s*content\D{0,10}([0-9]+[.,][0-9]+|[0-9]+)\s*%"
    ],
    "% Maltitol / Polioles": [
        r"(maltitol|maltitol\s*content|polyols?)\D{0,10}([0-9]+[.,][0-9]+|[0-9]+)\s*%"
    ],
    "Vida útil (meses)": [
        r"(vida\s*util|shelf\s*life|expiry|best\s*before)\D{0,15}([0-9]+)\s*(mes|meses|months?)"
    ],
    "Almacenamiento": [
        r"(almacenamiento|storage)\s*[:\-]\s*([^\n]+)"
    ],
    "Envase / Empaque": [
        r"(envase|empaque|packaging)\s*[:\-]\s*([^\n]+)"
    ],
    "Certificaciones": [
        r"(haccp|fssc|brc|iso\s*22000|kosher|halal)"
    ],
    "Microbiología (mención)": [
        r"(microbiolog)|(salmonella)|(e\.?\s*coli)|(levaduras)|(mohos)|(aerobios)"
    ],
    "Metales pesados (mención)": [
        r"(metales\s*pesados|heavy\s*metals|lead|mercury|arsenic|cadmium|pb|hg|as|cd)"
    ],
}

def find_field_in_text(field_key, text):
    t = norm(text)
    for pat in FIELDS[field_key]:
        m = re.search(pat, t, flags=re.IGNORECASE)
        if m:
            # Devuelve el primer grupo con número/texto
            groups = [g for g in m.groups() if g]
            if groups:
                val = groups[0]
                val = val.replace(",", ".")
                return val
            return "sí"
    return None

def find_field_in_tables(field_key, tables):
    # Busca filas que contengan la palabra clave y un número (muy simple)
    keys = ["humedad","moisture","cacao","cocoa","maltitol","polyol","vida util","shelf life","envase","packaging","almacenamiento","storage"]
    for row in tables:
        row_join = norm(" | ".join(row))
        if any(k in row_join for k in keys):
            # intenta encontrar números y % en la fila
            if field_key == "Humedad (%)" and ("humedad" in row_join or "moisture" in row_join):
                m = re.search(r"([0-9]+[.,][0-9]+|[0-9]+)\s*%", row_join)
                if m: return m.group(1).replace(",", ".")
            if field_key == "% Cacao" and ("cacao" in row_join or "cocoa" in row_join):
                m = re.search(r"([0-9]+[.,][0-9]+|[0-9]+)\s*%", row_join)
                if m: return m.group(1).replace(",", ".")
            if field_key == "% Maltitol / Polioles" and ("maltitol" in row_join or "polyol" in row_join):
                m = re.search(r"([0-9]+[.,][0-9]+|[0-9]+)\s*%", row_join)
                if m: return m.group(1).replace(",", ".")
            if field_key == "Vida útil (meses)" and ("vida util" in row_join or "shelf life" in row_join):
                m = re.search(r"([0-9]+)\s*(mes|meses|month)", row_join)
                if m: return m.group(1)
            if field_key == "Almacenamiento" and ("almacenamiento" in row_join or "storage" in row_join):
                return " ".join(row[:])[:120]
            if field_key == "Envase / Empaque" and ("envase" in row_join or "packaging" in row_join):
                return " ".join(row[:])[:120]
            if field_key == "Certificaciones" and any(k in row_join for k in ["haccp","fssc","brc","iso","kosher","halal"]):
                return "sí"
            if field_key == "Microbiología (mención)" and any(k in row_join for k in ["microbiol","salmonella","coli","levaduras","mohos","aerobios"]):
                return "sí"
            if field_key == "Metales pesados (mención)" and any(k in row_join for k in ["metales pesados","heavy metals","lead","mercury","arsenic","cadmium","pb","hg","as","cd"]):
                return "sí"
    return None

def extract_fields_from_pdf(uploaded_file):
    """Devuelve dict {campo: valor_encontrado} buscando en texto y en tablas."""
    text, tables = read_pdf_text_and_tables(uploaded_file)
    result = {}
    for key in FIELDS.keys():
        val = find_field_in_text(key, text)
        if val is None:
            val = find_field_in_tables(key, tables)
        result[key] = val
    return result

# -----------------------
# UI
# -----------------------
st.subheader("1) Sube la especificación técnica (PDF)")
spec_file = st.file_uploader("Especificación", type=["pdf"], key="spec")

st.subheader("2) Sube los documentos del proveedor (PDF)")
prov_files = st.file_uploader("Proveedor (1..N PDFs)", type=["pdf"], accept_multiple_files=True, key="prov")

if spec_file and prov_files:
    st.success("Archivos cargados. Procesando…")

    # Extraer SPEC
    st.markdown("### Extrayendo campos de la **Especificación**")
    spec_vals = extract_fields_from_pdf(spec_file)
    spec_df = pd.DataFrame(list(spec_vals.items()), columns=["Variable", "Especificación"])
    st.dataframe(spec_df, use_container_width=True)

    # Extraer Proveedor (consolidado)
    st.markdown("### Extrayendo campos del **Proveedor (consolidado)**")
    prov_agg = {k: None for k in FIELDS.keys()}

    for f in prov_files:
        vals = extract_fields_from_pdf(f)
        for k, v in vals.items():
            # conserva el primer valor no nulo
            if prov_agg[k] is None and v is not None:
                prov_agg[k] = v

    prov_df = pd.DataFrame(list(prov_agg.items()), columns=["Variable", "Proveedor"])
    st.dataframe(prov_df, use_container_width=True)

    # Comparación simple
    st.markdown("## Comparación")
    rows = []
    for k in FIELDS.keys():
        spec_v = spec_vals.get(k)
        prov_v = prov_agg.get(k)

        estado = "No informado"
        if prov_v is not None and spec_v is None:
            estado = "Informado (sin criterio en especificación)"
        elif prov_v is None and spec_v is not None:
            estado = "No informado"
        elif prov_v is not None and spec_v is not None:
            # reglas mínimas: si ambos son % numéricos, comparar con tolerancia
            num_pat = r"([0-9]+(?:\.[0-9]+)?)"
            if k in ["Humedad (%)", "% Cacao", "% Maltitol / Polioles"] and re.search(num_pat, str(spec_v)) and re.search(num_pat, str(prov_v)):
                sv = float(re.search(num_pat, str(spec_v)).group(1))
                pv = float(re.search(num_pat, str(prov_v)).group(1))
                if k == "Humedad (%)":
                    estado = "Cumple" if pv <= sv else "No cumple"
                else:
                    # para % cacao/maltitol asumimos ">= especificación"
                    estado = "Cumple" if pv >= sv else "No cumple"
            else:
                estado = "Coincide" if norm(str(prov_v)) in norm(str(spec_v)) or norm(str(spec_v)) in norm(str(prov_v)) else "Revisar"

        rows.append({"Variable": k, "Especificación": spec_v or "—", "Proveedor": prov_v or "—", "Estado": estado})

    comp_df = pd.DataFrame(rows)
    st.dataframe(comp_df, use_container_width=True)

    # Descarga
    st.download_button(
        "⬇️ Descargar comparación (CSV)",
        data=comp_df.to_csv(index=False).encode("utf-8"),
        file_name="comparacion_basica.csv",
        mime="text/csv"
    )

else:
    st.info("Sube una especificación y al menos un PDF de proveedor para comenzar.")
    
