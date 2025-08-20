import streamlit as st
import pandas as pd
import re, unicodedata
from collections import defaultdict
from docx import Document

st.set_page_config(page_title="Especificación: lector DOCX", page_icon="📄", layout="wide")
st.title("📄 Lector de Especificaciones con encabezado multinivel (DOCX)")

# ----------------- utilidades -----------------
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
    """forward-fill en una lista (para celdas combinadas que quedan vacías)"""
    cur = ""
    out = []
    for x in row:
        if str(x).strip() != "":
            cur = str(x).strip()
        out.append(cur)
    return out

def build_header_two_rows(rows):
    """
    Usa las dos primeras filas como encabezado multinivel.
    - Hace forward-fill en cada fila.
    - Concatena como 'Top|Sub' si el Sub es significativo (min/target/max).
    """
    if len(rows) < 2:
        hdr = [str(x).strip() for x in rows[0]]
        return make_unique(hdr), 1  # header, body_start

    top = ffill_row(rows[0])
    sub = ffill_row(rows[1])

    headers = []
    for a, b in zip(top, sub):
        a_clean = str(a).strip()
        b_clean = str(b).strip()
        # si sub encabezado parece 'min/target/max', lo incluimos
        if nrm(b_clean) in {"min", "mín", "minimo", "target", "max", "máx", "maximo"}:
            headers.append(f"{a_clean}|{b_clean}")
        else:
            headers.append(a_clean)

    headers = make_unique(headers)
    return headers, 2  # header, body_start

# mapeo a nombres finales
PRETTY = {
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
}

# sinónimos para agrupar
ALIASES = {
    "parametro": ["parametro", "parámetro"],
    "especificacion": ["especificacion", "especificación", "spec"],
    "unidad": ["unidad", "unit", "units"],
    "metodo utilizado": ["metodo utilizado","metodo","método","method"],
    "periodicidad de control": ["periodicidad de control","frecuencia","periodicidad"],
    "coa (si/no)": ["coa (si/no)","coa (sí/no)","coa"],
    # subheaders:
    "min": ["min","mín","minimo"],
    "target": ["target"],
    "max": ["max","máx","maximo"],
}

def canon_key(header):
    """Convierte 'ESPECIFICACIÓN|MÍN' -> 'especificacion|min' (canónico) para mapear a PRETTY."""
    h = nrm(header)
    parts = [p.strip() for p in h.split("|")]
    mapped = []
    for p in parts:
        hit = p
        for k, alts in ALIASES.items():
            if any(nrm(a) == p for a in alts):
                hit = k
                break
        mapped.append(hit)
    return "|".join(mapped)

def normalize_multilevel_df(df):
    """
    - Agrupa columnas por clave canónica (p. ej. todas las variantes de 'ESPECIFICACIÓN|MÍN').
    - Coalesce por fila (primer no vacío).
    - Renombra a PRETTY (MIN, TARGET, MAX, etc.).
    - Devuelve sólo columnas relevantes.
    """
    if df is None or df.empty:
        return df

    groups = defaultdict(list)
    for c in df.columns:
        groups[canon_key(c)].append(c)

    out = pd.DataFrame(index=df.index)

    # Coalesce por grupo
    for key, cols in groups.items():
        merged = df[cols].replace({"": pd.NA}).bfill(axis=1).iloc[:, 0]
        final_name = PRETTY.get(key, None)
        if final_name is None:
            # si es 'especificacion' sin subheader no la usamos (porque nos interesan MIN/TARGET/MAX)
            if key.startswith("especificacion|"):
                base = key.split("|")[-1].upper()
                final_name = base
            else:
                # deja cualquier otra columna con su nombre original (bonito)
                final_name = cols[0]
        out[final_name] = merged.fillna("")

    # Intentamos encontrar columna PARÁMETRO aunque llegue con variantes
    if "PARÁMETRO" not in out.columns:
        for c in list(out.columns):
            if nrm(c) in ("parametro","parámetro"):
                out.rename(columns={c: "PARÁMETRO"}, inplace=True)

    # Orden sugerido
    order = [c for c in ["PARÁMETRO","MIN","TARGET","MAX","UNIDAD","MÉTODO UTILIZADO","PERIODICIDAD DE CONTROL","CoA (Sí/No)"] if c in out.columns]
    # añade el resto al final
    rest = [c for c in out.columns if c not in order]
    out = out[order + rest]

    # Filtra filas completamente vacías
    out = out[ out.apply(lambda r: r.astype(str).str.strip().any(), axis=1) ].reset_index(drop=True)
    return out

def read_docx_tables(file):
    """Extrae todas las tablas de un .docx como DataFrames, soportando encabezado de 2 filas."""
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

        # normalizar ancho
        max_cols = max(len(r) for r in rows)
        rows = [r + [""] * (max_cols - len(r)) for r in rows]

        # header multinivel (2 filas)
        header, body_start = build_header_two_rows(rows)
        body = rows[body_start:] if len(rows) > body_start else []
        df = pd.DataFrame(body, columns=header) if body else pd.DataFrame(columns=header)
        tables.append(df)
    return tables

# ----------------- UI -----------------
docx_file = st.file_uploader("📂 Sube la especificación (.docx)", type=["docx"])

if docx_file:
    try:
        raw_tables = read_docx_tables(docx_file)
        if not raw_tables:
            st.warning("No se detectaron tablas en el documento.")
        for i, raw in enumerate(raw_tables, start=1):
            st.divider()
            st.subheader(f"📊 Tabla {i}")

            st.caption("Encabezado multinivel detectado (original)")
            st.dataframe(raw, use_container_width=True)

            st.caption("✅ Normalizada (PARÁMETRO / MIN / TARGET / MAX / UNIDAD / ...)")
            clean = normalize_multilevel_df(raw)
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
