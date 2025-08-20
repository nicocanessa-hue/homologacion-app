# app.py — Extractor Especificación Técnica (Incisos 1–6)
# 1) Descripción  2) Composición  3) Organolépticos  4) Físico‑químicos
# 5) Microbiológicos  6) Micotoxinas

import re
import unicodedata
import pandas as pd
import streamlit as st
from docx import Document
from docx.oxml.ns import qn
from docx.document import Document as _Document
from docx.table import _Cell, Table as _Table
from docx.text.paragraph import Paragraph

st.set_page_config(page_title="Extractor Especificación (1–6)", page_icon="📄", layout="wide")
st.title("Extractor de Especificación Técnica — Incisos 1–6")

# ---------------- Utils base ----------------
def nrm(s: str) -> str:
    s = "" if s is None else str(s).strip()
    s = "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn")
    s = re.sub(r"\s+", " ", s)
    return s.lower()

def es_titulo_numerado(texto: str) -> bool:
    # "1) ...", "1. ...", "1 ..." etc.
    return bool(re.match(r"^\s*\d+(\)|\.| )", texto or ""))

def iter_block_items(parent):
    if isinstance(parent, _Document):
        parent_elm = parent.element.body
    elif isinstance(parent, _Cell):
        parent_elm = parent._tc
    else:
        return
    for child in parent_elm.iterchildren():
        if child.tag == qn('w:p'):
            yield Paragraph(child, parent)
        elif child.tag == qn('w:tbl'):
            yield _Table(child, parent)

def dedupe_columns(df: pd.DataFrame) -> pd.DataFrame:
    seen = {}
    new_cols = []
    for c in df.columns:
        if c in seen:
            seen[c] += 1
            new_cols.append(f"{c}_{seen[c]}")
        else:
            seen[c] = 0
            new_cols.append(c)
    df = df.copy()
    df.columns = new_cols
    return df

def table_rows(tbl: _Table):
    rows = []
    for r in tbl.rows:
        cells = [(" ".join(p.text for p in cell.paragraphs)).strip() for cell in r.cells]
        cells = [" ".join(x.split()) for x in cells]
        rows.append(cells)
    if not rows: return []
    max_cols = max(len(r) for r in rows)
    return [r + [""] * (max_cols - len(r)) for r in rows]

def make_unique(cols):
    seen, out = {}, []
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
        x = (x or "").strip()
        if x: cur = x
        out.append(cur)
    return out

def table_to_df(tbl: _Table) -> pd.DataFrame:
    rows = table_rows(tbl)
    if not rows: return pd.DataFrame()
    header = make_unique(rows[0])
    body = rows[1:] if len(rows) > 1 else []
    df = pd.DataFrame(body, columns=header) if body else pd.DataFrame(columns=header)
    return dedupe_columns(df)

def table_to_df_maybe_multihdr(tbl: _Table) -> pd.DataFrame:
    """Soporta header de 2 filas (p.ej.: ESPECIFICACIÓN + MÍN/TARGET/MÁX; PLAN DE MUESTREO + n/c/m/M)."""
    rows = table_rows(tbl)
    if not rows: return pd.DataFrame()
    # ¿Tiene pinta de multihdr?
    if len(rows) >= 2:
        sub = [s.lower() for s in rows[1]]
        if any(k in " ".join(sub) for k in [
            "mín","min","target","máx","max","objetivo",
            "categoría","categoria","clase"," n "," c "," m "," m "
        ]):
            top = ffill_row(rows[0])
            sub = ffill_row(rows[1])
            headers = []
            for a, b in zip(top, sub):
                headers.append(f"{a.strip()}|{b.strip()}" if b.strip() else a.strip())
            headers = make_unique(headers)
            body = rows[2:] if len(rows) > 2 else []
            df = pd.DataFrame(body, columns=headers) if body else pd.DataFrame(columns=headers)
            return dedupe_columns(df)
    return table_to_df(tbl)

def find_section_paragraphs(doc: Document, title_keys: list[str]) -> list[str]:
    """Busca párrafos que siguen a un título (con o sin numeración) hasta el próximo título numerado."""
    keys_norm = [nrm(k) for k in title_keys]
    paras = [p.text for p in doc.paragraphs]
    start_idx = None
    for i, p in enumerate(paras):
        t = nrm(p)
        if (es_titulo_numerado(p) and any(k in t for k in keys_norm)) or any(t.startswith(k) for k in keys_norm):
            start_idx = i + 1
            break
    if start_idx is None:
        return []
    out = []
    for p in paras[start_idx:]:
        if es_titulo_numerado(p):  # siguiente sección
            break
        if p.strip():
            out.append(p.strip())
    return out

def find_section_tables(doc: Document, title_keys: list[str], multihdr=False) -> list[pd.DataFrame]:
    """Devuelve tablas que aparecen después de un título (hasta el próximo título numerado)."""
    keys_norm = [nrm(k) for k in title_keys]
    blocks = list(iter_block_items(doc))
    start = None
    for i, blk in enumerate(blocks):
        if isinstance(blk, Paragraph):
            t = blk.text
            if (es_titulo_numerado(t) and any(k in nrm(t) for k in keys_norm)) or any(nrm(t).startswith(k) for k in keys_norm):
                start = i + 1
                break
    if start is None:
        return []
    end = len(blocks)
    for j in range(start, len(blocks)):
        if isinstance(blocks[j], Paragraph) and es_titulo_numerado(blocks[j].text):
            end = j
            break
    tablas = []
    for b in blocks[start:end]:
        if isinstance(b, _Table):
            df = table_to_df_maybe_multihdr(b) if multihdr else table_to_df(b)
            if not df.empty:
                tablas.append(df)
    return tablas

# ---------------- Inciso 1 — Descripción ----------------
DESC_KEYS = ["descripción del producto", "descripcion del producto"]
def extraer_descripcion(doc: Document) -> str:
    paras = find_section_paragraphs(doc, DESC_KEYS)
    return " ".join(paras).strip()

# ---------------- Inciso 2 — Composición ----------------
COMP_KEYS = ["composición del producto", "composicion del producto", "ingredientes"]
RE_ITEM = re.compile(r"^\s*(?P<ing>.+?)\s*[:\-–]?\s*(?P<pct>\d+(?:[.,]\d+)?)\s*%?\s*$", re.VERBOSE)

def extraer_composicion(doc: Document) -> pd.DataFrame:
    # Preferir párrafos con %
    lines = find_section_paragraphs(doc, COMP_KEYS)
    rows = []
    for ln in lines:
        parts = [p.strip() for p in re.split(r",(?!\d)", ln) if p.strip()]  # separar por comas “fuertes”
        for p in parts:
            m = RE_ITEM.match(p)
            if m:
                ing = m.group("ing").strip()
                pct = m.group("pct").replace(",", ".")
                rows.append([ing, pct])
    df = pd.DataFrame(rows, columns=["Ingrediente", "%"])
    # Si no se encontró nada en párrafos, intentar tabla con columnas tipo “Ingrediente / %”
    if df.empty:
        tablas = find_section_tables(doc, COMP_KEYS, multihdr=False)
        for t in tablas:
            cols = [nrm(c) for c in t.columns]
            if any("%" in c or "porcentaje" in c for c in cols):
                try:
                    c_ing = [c for c in t.columns if "ingred" in nrm(c)]
                    c_pct = [c for c in t.columns if "%" in c or "porcentaje" in nrm(c)]
                    if c_ing and c_pct:
                        tmp = t[[c_ing[0], c_pct[0]]].copy()
                        tmp.columns = ["Ingrediente", "%"]
                        df = pd.concat([df, tmp], ignore_index=True)
                except:
                    pass
    if not df.empty:
        df = df.replace({"": pd.NA}).dropna(how="all").drop_duplicates().reset_index(drop=True)
    return df

# ---------------- Inciso 3 — Organolépticos ----------------
ORG_KEYS = ["parámetros organolépticos", "parametros organolepticos"]
def extraer_organolepticos(doc: Document) -> list[pd.DataFrame]:
    tabs = find_section_tables(doc, ORG_KEYS, multihdr=False)
    out = []
    for t in tabs:
        # Unificar columnas repetidas de “PARÁMETRO / ESPECIFICACIÓN”
        t = dedupe_columns(t)
        # si existen variantes, consolidar nombres
        rename = {}
        for c in t.columns:
            cl = nrm(c)
            if "parámetro" in cl or "parametro" in cl: rename[c] = "PARÁMETRO"
            elif "especificación" in cl or "especificacion" in cl: rename[c] = "ESPECIFICACIÓN"
        if rename:
            t = t.rename(columns=rename)
            keep = [c for c in ["PARÁMETRO","ESPECIFICACIÓN"] if c in t.columns]
            if keep:
                t = t[keep]
        out.append(t)
    return out

# ---------------- Inciso 4 — Físico‑químicos ----------------
FISQ_KEYS = ["parámetros físico-químicos","parametros fisico-quimicos","parametros físico-químicos"]

def normalize_fisicoquimicos(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty: return df

    def pick(keys):
        for c in df.columns:
            if any(k in nrm(c) for k in keys): return c
        return None

    def clean(s):
        if s is None: return ""
        if isinstance(s, pd.Series): return s.replace({"-":"", "–":""}).astype(str).str.strip()
        return str(s).strip()

    out = pd.DataFrame(index=df.index)
    out["PARÁMETRO"] = clean(df[pick(["parámetro","parametro"])]) if pick(["parámetro","parametro"]) else ""

    out["MIN"]    = clean(df[pick(["|min"," mín"," min","mín","minimo","mínimo","min"])]) if pick(["|min"," mín"," min","mín","minimo","mínimo","min"]) else ""
    out["TARGET"] = clean(df[pick(["target","objetivo"])]) if pick(["target","objetivo"]) else ""
    out["MAX"]    = clean(df[pick(["|max"," máx"," max","máx","maximo","máximo","max"])]) if pick(["|max"," máx"," max","máx","maximo","máximo","max"]) else ""
    out["UNIDAD"] = clean(df[pick(["unidad","unit"])]) if pick(["unidad","unit"]) else ""
    if pick(["método utilizado","metodo utilizado","método","metodo","method"]):
        out["MÉTODO UTILIZADO"] = clean(df[pick(["método utilizado","metodo utilizado","método","metodo","method"])])
    if pick(["periodicidad de control","frecuencia","periodicidad"]):
        out["PERIODICIDAD DE CONTROL"] = clean(df[pick(["periodicidad de control","frecuencia","periodicidad"])])
    if pick(["coa (sí/no)","coa (si/no)","coa"]):
        out["CoA (Sí/No)"] = clean(df[pick(["coa (sí/no)","coa (si/no)","coa"])])

    cols = [c for c in ["PARÁMETRO","MIN","TARGET","MAX","UNIDAD","MÉTODO UTILIZADO","PERIODICIDAD DE CONTROL","CoA (Sí/No)"] if c in out.columns]
    out = dedupe_columns(out[cols])
    out = out[out.apply(lambda r: r.astype(str).str.strip().any(), axis=1)].reset_index(drop=True)
    return out

def extraer_fisicoquimicos(doc: Document) -> list[pd.DataFrame]:
    tabs = find_section_tables(doc, FISQ_KEYS, multihdr=True)
    return [normalize_fisicoquimicos(t) for t in tabs] if tabs else []

# ---------------- Inciso 5 — Microbiológicos ----------------
MICRO_KEYS = ["parámetros microbiológicos","parametros microbiologicos","microbiologicos"]

def normalize_microbio(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty: return df
    # map nombres
    rename = {}
    for c in df.columns:
        cl = nrm(c)
        if "parámetro" in cl or "parametro" in cl or "microorganismo" in cl: rename[c] = "PARÁMETRO"
        elif "método" in cl or "metodo" in cl or "method" in cl: rename[c] = "MÉTODO"
        elif "grupo" in cl: rename[c] = "GRUPO"
        elif "categor" in cl: rename[c] = "CATEGORÍA"
        elif "clase" in cl: rename[c] = "CLASE"
        elif "|n" in cl or cl == "n": rename[c] = "n"
        elif "|c" in cl or cl == "c": rename[c] = "c"
        elif "|m" in cl or cl == "m": rename[c] = "m"
        elif "|m " in cl or cl == "m_1" or cl == "m_2": rename[c] = "M"  # fallback
        elif "límite" in cl or "limite" in cl: rename[c] = "LÍMITE"
        elif "periodicidad" in cl or "frecuencia" in cl: rename[c] = "PERIODICIDAD DE CONTROL"
        elif "coa" in cl: rename[c] = "CoA (Sí/No)"
    df2 = df.rename(columns=rename)
    # Si LÍMITE tiene “m … M …” en una sola celda → extraer
    if "LÍMITE" in df2.columns:
        lim = df2["LÍMITE"].astype(str)
        m_vals = lim.str.extract(r"[m]\s*[:=]?\s*([0-9]+(?:[.,][0-9]+)?)", expand=False)
        M_vals = lim.str.extract(r"[M]\s*[:=]?\s*([0-9]+(?:[.,][0-9]+)?)", expand=False)
        if "m" not in df2.columns: df2["m"] = m_vals
        if "M" not in df2.columns: df2["M"] = M_vals
    order = ["PARÁMETRO","MÉTODO","GRUPO","CATEGORÍA","CLASE","n","c","m","M","LÍMITE","PERIODICIDAD DE CONTROL","CoA (Sí/No)"]
    keep = [c for c in order if c in df2.columns]
    out = dedupe_columns(df2[keep])
    out = out[out.apply(lambda r: r.astype(str).str.strip().any(), axis=1)].reset_index(drop=True)
    return out

def extraer_microbiologicos(doc: Document) -> list[pd.DataFrame]:
    tabs = find_section_tables(doc, MICRO_KEYS, multihdr=True)
    return [normalize_microbio(t) for t in tabs] if tabs else []

# ---------------- Inciso 6 — Micotoxinas ----------------
MICOTOX_KEYS = ["micotoxinas", "toxinas micotoxinas", "contaminantes químicos", "contaminantes quimicos"]

def normalize_micotox(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty: return df
    rename = {}
    for c in df.columns:
        cl = nrm(c)
        if "micotoxina" in cl or "aflatoxina" in cl or "ocratoxina" in cl or "zearalenona" in cl or "fumonisina" in cl:
            rename[c] = "MICOTOXINA"
        elif "límite" in cl or "limite" in cl or "máximo" in cl or "maximo" in cl:
            rename[c] = "LÍMITE"
        elif "unidad" in cl or "ppb" in cl or "µg/kg" in cl or "ug/kg" in cl or "ppm" in cl or "mg/kg" in cl:
            rename[c] = "UNIDAD"
        elif "norma" in cl or "referencia" in cl or "rsa" in cl or "codex" in cl or "reglamento" in cl:
            rename[c] = "NORMA/REFERENCIA"
        elif "método" in cl or "metodo" in cl or "method" in cl:
            rename[c] = "MÉTODO"
        elif "periodicidad" in cl or "frecuencia" in cl:
            rename[c] = "PERIODICIDAD DE CONTROL"
        elif "coa" in cl:
            rename[c] = "CoA (Sí/No)"
    df2 = df.rename(columns=rename)
    # Si LÍMITE viene como “10 ppb” → separar
    if "LÍMITE" in df2.columns:
        lim = df2["LÍMITE"].astype(str)
        val = lim.str.extract(r"([0-9]+(?:[.,][0-9]+)?)", expand=False)
        unit = lim.str.extract(r"([a-zA-Zµ/%]+)$", expand=False)
        df2["VALOR"] = val
        if "UNIDAD" not in df2.columns:
            df2["UNIDAD"] = unit
    order = ["MICOTOXINA","VALOR","UNIDAD","LÍMITE","NORMA/REFERENCIA","MÉTODO","PERIODICIDAD DE CONTROL","CoA (Sí/No)"]
    keep = [c for c in order if c in df2.columns]
    out = dedupe_columns(df2[keep])
    out = out[out.apply(lambda r: r.astype(str).str.strip().any(), axis=1)].reset_index(drop=True)
    return out

def extraer_micotoxinas(doc: Document) -> list[pd.DataFrame]:
    tabs = find_section_tables(doc, MICOTOX_KEYS, multihdr=True)
    return [normalize_micotox(t) for t in tabs] if tabs else []

# ---------------- UI ----------------
uploaded = st.file_uploader("📂 Sube la especificación (.docx)", type=["docx"])

if uploaded:
    doc = Document(uploaded)

    # 1) Descripción
    st.subheader("1) Descripción del Producto")
    desc = extraer_descripcion(doc)
    if desc:
        df_desc = pd.DataFrame([{"Descripción del Producto": desc}])
        st.table(df_desc)
        st.download_button("⬇️ Descripción (CSV)", df_desc.to_csv(index=False).encode("utf-8"), "descripcion.csv", "text/csv")
    else:
        st.info("No se encontró la descripción (intenta revisar el título del inciso).")

    st.divider()

    # 2) Composición
    st.subheader("2) Composición del Producto (%) e Ingredientes")
    comp = extraer_composicion(doc)
    if not comp.empty:
        st.dataframe(comp, use_container_width=True)
        st.download_button("⬇️ Composición (CSV)", comp.to_csv(index=False).encode("utf-8"), "composicion.csv", "text/csv")
    else:
        st.info("No se detectó la composición (ni en texto ni en tabla).")

    st.divider()

    # 3) Organolépticos
    st.subheader("3) Parámetros organolépticos")
    org_tabs = extraer_organolepticos(doc)
    if not org_tabs:
        st.info("No se detectaron tablas de organolépticos.")
    else:
        for i, df in enumerate(org_tabs, 1):
            st.caption(f"Tabla organolépticos {i}")
            st.dataframe(df, use_container_width=True)
            st.download_button(f"⬇️ Organolépticos {i} (CSV)", df.to_csv(index=False).encode("utf-8"), f"organolepticos_{i}.csv", "text/csv", key=f"dl_org_{i}")

    st.divider()

    # 4) Físico‑químicos
    st.subheader("4) Parámetros físico‑químicos")
    fisq_tabs = extraer_fisicoquimicos(doc)
    if not fisq_tabs:
        st.info("No se detectaron tablas físico‑químicas.")
    else:
        for i, df in enumerate(fisq_tabs, 1):
            st.caption(f"Tabla físico‑químicos {i}")
            st.dataframe(df, use_container_width=True)
            st.download_button(f"⬇️ Físico‑químicos {i} (CSV)", df.to_csv(index=False).encode("utf-8"), f"fisicoquimicos_{i}.csv", "text/csv", key=f"dl_fq_{i}")

    st.divider()

    # 5) Microbiológicos
    st.subheader("5) Parámetros microbiológicos")
    micro_tabs = extraer_microbiologicos(doc)
    if not micro_tabs:
        st.info("No se detectaron tablas microbiológicas.")
    else:
        for i, df in enumerate(micro_tabs, 1):
            st.caption(f"Tabla microbiológicos {i}")
            st.dataframe(df, use_container_width=True)
            st.download_button(f"⬇️ Microbiológicos {i} (CSV)", df.to_csv(index=False).encode("utf-8"), f"microbiologicos_{i}.csv", "text/csv", key=f"dl_micro_{i}")

    st.divider()

    # 6) Micotoxinas
    st.subheader("6) Micotoxinas")
    mico_tabs = extraer_micotoxinas(doc)
    if not mico_tabs:
        st.info("No se detectaron tablas de micotoxinas.")
    else:
        for i, df in enumerate(mico_tabs, 1):
            st.caption(f"Tabla micotoxinas {i}")
            st.dataframe(df, use_container_width=True)
            st.download_button(f"⬇️ Micotoxinas {i} (CSV)", df.to_csv(index=False).encode("utf-8"), f"micotoxinas_{i}.csv", "text/csv", key=f"dl_mico_{i}")
else:
    st.info("Sube el archivo .docx para comenzar.")
