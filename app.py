# app.py
import streamlit as st
import pandas as pd
import re, unicodedata
from collections import defaultdict
from docx import Document

st.set_page_config(page_title="Especificaciones · Lector DOCX Pro", page_icon="📄", layout="wide")
st.title("📄 Lector de Especificaciones (DOCX) con encabezados multinivel")

# ----------------- helpers de texto/encabezados -----------------
def nrm(s):
    if s is None: return ""
    s = str(s).strip().lower()
    s = "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn")
    s = re.sub(r"\s+", " ", s)
    return s

def make_unique(cols):
    seen = {}
    out = []
    for c in cols:
        c = "" if c is None else str(c).strip()
        if c in seen:
            seen[c] += 1
            out.append(f"{c}_{seen[c]}")
        else:
            seen[c] = 0
            out.append(c)
    return out

def ffill_row(row):
    cur = ""
    out = []
    for x in row:
        x = "" if x is None else str(x).strip()
        if x != "":
            cur = x
        out.append(cur)
    return out

def build_header_multirows(rows, max_header_rows=4):
    """
    Construye encabezados combinando hasta 'max_header_rows' filas superiores.
    Concatena niveles como: Top|Sub|Subsub
    """
    header_rows = rows[:max_header_rows]
    ffilled = [ffill_row(r) for r in header_rows]

    # Combina por columna
    headers = []
    for col in zip(*ffilled):
        parts = [p for p in col if p]  # solo no vacíos
        header = "|".join(parts) if parts else ""
        headers.append(header)

    headers = make_unique(headers)
    return headers, len(header_rows)

# ----------------- normalización de columnas -----------------
# Mapa a nombres finales “bonitos”
PRETTY = {
    # Físico-químicos
    "parametro": "PARÁMETRO",
    "especificacion|min": "MIN",
    "especificacion|mín": "MIN",
    "especificacion|minimo": "MIN",
    "especificacion|target": "TARGET",
    "especificacion|max": "MAX",
    "especificacion|máx": "MAX",
    "unidad": "UNIDAD",
    "metodo utilizado": "MÉTODO UTILIZADO",
    "periodicidad de control": "PERIODICIDAD DE CONTROL",
    "coa (si/no)": "CoA (Sí/No)",

    # Microbiológicos (deja como está si no mapea)
    "metodo": "MÉTODO",
    "grupo": "GRUPO",
    "plan de muestreo|categoria": "PLAN DE MUESTREO|Categoría",
    "plan de muestreo|clase": "PLAN DE MUESTREO|Clase",
    "plan de muestreo|n": "PLAN DE MUESTREO|n",
    "plan de muestreo|c": "PLAN DE MUESTREO|c",
    "limite|m": "LÍMITE|m",
    "limite|m.": "LÍMITE|m",
    "limite|max": "LÍMITE|M",
    "limite|m_": "LÍMITE|m",
    "limite|m mayus": "LÍMITE|M",
}

# Aliases para reconocer variantes/español-inglés
ALIASES = {
    "parametro": ["parametro", "parámetro"],
    "especificacion": ["especificacion", "especificación", "spec", "requisito", "valor"],
    "unidad": ["unidad", "unit", "units"],
    "metodo utilizado": ["metodo utilizado", "metodo", "método", "method"],
    "periodicidad de control": ["periodicidad de control", "frecuencia", "periodicidad"],
    "coa (si/no)": ["coa (si/no)", "coa (sí/no)", "coa"],

    # Micro
    "metodo": ["metodo", "método", "method"],
    "grupo": ["grupo", "group"],
    "plan de muestreo": ["plan de muestreo", "sampling plan", "plan muestreo", "plan"],
    "categoria": ["categoria", "categoría", "category"],
    "clase": ["clase", "class"],
    "limite": ["limite", "límite", "limit"],
    "m": ["m"],
    "max": ["m", "m "],  # algunos documentos ponen 'M' en mayúscula; lo resolveremos abajo
    "n": ["n"],
    "c": ["c"],
}

def canon_part(token):
    t = nrm(token)
    for key, alts in ALIASES.items():
        for a in alts:
            if nrm(a) == t:
                return key
    return t

def canon_key(header):
    """'ESPECIFICACIÓN|MÍN' -> 'especificacion|min' (clave canónica)"""
    parts = [p for p in header.split("|") if p]
    mapped = [canon_part(p) for p in parts]
    return "|".join(mapped)

def coalesce_groups(df, name_map=PRETTY):
    """
    Agrupa columnas por 'canon_key' y hace coalesce por fila (primer no vacío).
    Renombra con PRETTY si aplica.
    """
    if df is None or df.empty:
        return df

    groups = defaultdict(list)
    for c in df.columns:
        groups[canon_key(c)].append(c)

    out = pd.DataFrame(index=df.index)

    for key, cols in groups.items():
        merged = df[cols].replace({"": pd.NA}).bfill(axis=1).iloc[:, 0]
        final = name_map.get(key, None)
        if final is None:
            # si es 'especificacion' sin subclave, no añadir (preferimos MIN/TARGET/MAX)
            if key.startswith("especificacion|"):
                sub = key.split("|")[-1].upper()
                final = sub
            else:
                final = cols[0]
        out[final] = merged.fillna("")

    # Fallback para PARÁMETRO si no lo detectó
    if "PARÁMETRO" not in out.columns:
        for c in list(out.columns):
            if nrm(c) in ("parametro", "parámetro"):
                out.rename(columns={c: "PARÁMETRO"}, inplace=True)

    # Orden sugerido si existen
    pref_order = [
        "PARÁMETRO", "MIN", "TARGET", "MAX",
        "UNIDAD", "MÉTODO UTILIZADO", "MÉTODO",
        "GRUPO",
        "PLAN DE MUESTREO|Categoría", "PLAN DE MUESTREO|Clase",
        "PLAN DE MUESTREO|n", "PLAN DE MUESTREO|c",
        "LÍMITE|m", "LÍMITE|M",
        "PERIODICIDAD DE CONTROL", "CoA (Sí/No)"
    ]
    ordered = [c for c in pref_order if c in out.columns]
    rest = [c for c in out.columns if c not in ordered]
    out = out[ordered + rest]

    # Elimina filas completamente vacías
    out = out[out.apply(lambda r: r.astype(str).str.strip().any(), axis=1)].reset_index(drop=True)
    return out

# ----------------- lectura de DOCX a DataFrames -----------------
def read_docx_tables(file, max_header_rows=4):
    """
    Extrae todas las tablas del .docx como DataFrames, soportando encabezados de múltiple nivel.
    """
    doc = Document(file)
    tables = []
    for t in doc.tables:
        rows = []
        for r in t.rows:
            cells = []
            for c in r.cells:
                txt = " ".join(p.text for p in c.paragraphs).strip()
                txt = " ".join(txt.split())
                cells.append(txt)
            rows.append(cells)
        if not rows:
            continue

        # normaliza ancho
        max_cols = max(len(r) for r in rows)
        rows = [r + [""] * (max_cols - len(r)) for r in rows]

        # encabezado multinivel
        header, body_start = build_header_multirows(rows, max_header_rows=max_header_rows)
        body = rows[body_start:] if len(rows) > body_start else []

        df = pd.DataFrame(body, columns=header) if body else pd.DataFrame(columns=header)
        tables.append(df)
    return tables

# ----------------- UI -----------------
docx_file = st.file_uploader("📂 Sube la especificación (.docx)", type=["docx"])

if docx_file:
    try:
        raw_tables = read_docx_tables(docx_file, max_header_rows=4)
        if not raw_tables:
            st.warning("No se detectaron tablas en el documento.")
        for i, raw in enumerate(raw_tables, start=1):
            st.divider()
            st.subheader(f"📊 Tabla {i}")

            st.caption("Encabezado multinivel detectado (original)")
            st.dataframe(raw, use_container_width=True)

            st.caption("✅ Normalizada / fusionada (óptima para checklist)")
            clean = coalesce_groups(raw)
            st.dataframe(clean, use_container_width=True)

            st.download_button(
                f"⬇️ Descargar Tabla {i} normalizada (CSV)",
                data=clean.to_csv(index=False).encode("utf-8"),
                file_name=f"tabla_{i}_normalizada.csv",
                mime="text/csv",
                key=f"dl_norm_{i}"
            )

    except Exception as e:
        st.error(f"Error leyendo el DOCX: {e}")
else:
    st.info("Sube un .docx para comenzar.")
