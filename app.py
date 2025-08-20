# app.py — Especificación · Incisos 1–6 (Micotoxinas)
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

st.set_page_config(page_title="Especificación · Incisos 1–6", page_icon="📄", layout="centered")
st.title("Especificación · 1) Descripción · 2) Composición · 3) Organolépticos · 4) Físico‑químicos · 5) Microbiológicos · 6) Micotoxinas")

# ---------------- Utils base ----------------
def nrm(s: str) -> str:
    s = "" if s is None else str(s).strip()
    s = "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn")
    s = re.sub(r"\s+", " ", s)
    return s.lower()

def es_titulo_numerado(texto: str) -> bool:
    return bool(re.match(r"^\s*\d+(\.| )", texto or ""))

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

def dedupe_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Garantiza encabezados únicos (Col, Col_1, Col_2...)."""
    new = []
    seen = {}
    for c in df.columns:
        if c in seen:
            seen[c] += 1
            new.append(f"{c}_{seen[c]}")
        else:
            seen[c] = 0
            new.append(c)
    df = df.copy()
    df.columns = new
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

def table_to_df(tbl: _Table) -> pd.DataFrame:
    rows = table_rows(tbl)
    if not rows: return pd.DataFrame()
    header = make_unique(rows[0])
    body = rows[1:] if len(rows) > 1 else []
    df = pd.DataFrame(body, columns=header) if body else pd.DataFrame(columns=header)
    return dedupe_columns(df)

def ffill_row(row):
    cur = ""
    out = []
    for x in row:
        x = (x or "").strip()
        if x: cur = x
        out.append(cur)
    return out

def table_to_df_maybe_multihdr(tbl: _Table) -> pd.DataFrame:
    """Soporta header de 2 filas (p.ej., ESPECIFICACIÓN + MÍN/TARGET/MÁX o PLAN DE MUESTREO + n/c/m/M)."""
    rows = table_rows(tbl)
    if not rows: return pd.DataFrame()
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

def extraer_bloque_por_titulo_parrafos(docx_file, contiene_titulo_norm: str) -> list[str]:
    doc = Document(docx_file)
    paras = [p.text for p in doc.paragraphs]
    start_idx = None
    for i, p in enumerate(paras):
        if es_titulo_numerado(p) and contiene_titulo_norm in nrm(p):
            start_idx = i + 1
            break
    if start_idx is None:
        return []
    out = []
    for p in paras[start_idx:]:
        if es_titulo_numerado(p):
            break
        if p.strip():
            out.append(p.strip())
    return out

def extraer_bloque_mixto_tablas(docx_file, contiene_titulo_norm: str, multihdr=False):
    doc = Document(docx_file)
    blocks = list(iter_block_items(doc))
    start = None
    for i, blk in enumerate(blocks):
        if isinstance(blk, Paragraph) and es_titulo_numerado(blk.text) and contiene_titulo_norm in nrm(blk.text):
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
            tablas.append(df)
    return tablas

def coalesce_by_stem(df, stems):
    out = df.copy()
    for stem in stems:
        cols = [c for c in df.columns if nrm(c).startswith(nrm(stem))]
        if len(cols) > 1:
            merged = df[cols].replace({"": pd.NA}).bfill(axis=1).iloc[:, 0]
            out[stem] = merged.fillna("")
            drop_cols = [c for c in cols if c != stem]
            out = out.drop(columns=drop_cols, errors="ignore")
        elif len(cols) == 1 and cols[0] != stem:
            out = out.rename(columns={cols[0]: stem})
    return out

# ---------------- Incisos 1–3 ----------------
def extraer_descripcion(docx_file) -> str:
    bloque = extraer_bloque_por_titulo_parrafos(docx_file, "descripcion del producto")
    return " ".join(bloque).strip()

RE_ITEM = re.compile(r"""^\s*(?P<ing>.+?)\s*[:\-–]?\s*(?P<pct>\d+(?:[.,]\d+)?)\s*%?\s*$""", re.VERBOSE)
def parse_ingredientes(lines: list[str]) -> pd.DataFrame:
    rows = []
    for line in lines:
        parts = [p.strip() for p in re.split(r",(?!\d)", line) if p.strip()]
        for p in parts:
            m = RE_ITEM.match(p)
            if m:
                ing = m.group("ing").strip()
                pct_raw = m.group("pct").replace(",", ".")
                try: pct = float(pct_raw)
                except: pct = None
                rows.append({"Ingrediente": ing, "%": pct})
    df = pd.DataFrame(rows)
    if not df.empty:
        df = df.drop_duplicates().reset_index(drop=True)
    return df

def extraer_composicion(docx_file) -> tuple[pd.DataFrame, list[str]]:
    bloque = extraer_bloque_por_titulo_parrafos(docx_file, "composicion del producto (%) e ingredientes")
    return parse_ingredientes(bloque), bloque

def extraer_organolepticos(docx_file) -> list[pd.DataFrame]:
    for k in ["parametros organolepticos", "parámetros organolépticos"]:
        tablas = extraer_bloque_mixto_tablas(docx_file, nrm(k))
        if tablas: return tablas
    return []

# ---------------- Inciso 4 (Físico‑químicos) ----------------
def normalize_fisicoquimicos(df):
    if df is None or df.empty:
        return df

    def pick_col(keys):
        for c in df.columns:
            cl = nrm(c)
            if any(k in cl for k in keys):
                return c
        return None

    def clean_series(s, idx):
        if s is None:
            return pd.Series([""] * len(idx), index=idx)
        if isinstance(s, pd.Series):
            return s.replace({"-": "", "–": ""})
        return pd.Series([str(s).replace("-", "").replace("–", "")] * len(idx), index=idx)

    out = pd.DataFrame(index=df.index)

    c_min = pick_col(["|min", "|mín", " min", " mín", "min", "mín", "minimo", "mínimo"])
    c_tar = pick_col(["target", "objetivo"])
    c_max = pick_col(["|max", "|máx", " max", " máx", "max", "máx", "maximo", "máximo"])

    out["MIN"]    = clean_series(df[c_min] if c_min else None, df.index)
    out["TARGET"] = clean_series(df[c_tar] if c_tar else None, df.index)
    out["MAX"]    = clean_series(df[c_max] if c_max else None, df.index)

    c_param  = pick_col(["parámetro","parametro"])
    c_unidad = pick_col(["unidad","unit"])
    c_metodo = pick_col(["método utilizado","metodo utilizado","método","metodo","method"])
    c_per    = pick_col(["periodicidad de control","frecuencia","periodicidad"])
    c_coa    = pick_col(["coa (sí/no)","coa (si/no)","coa"])

    if c_param:  out["PARÁMETRO"] = df[c_param]
    if c_unidad: out["UNIDAD"] = df[c_unidad]
    if c_metodo: out["MÉTODO UTILIZADO"] = df[c_metodo]
    if c_per:    out["PERIODICIDAD DE CONTROL"] = df[c_per]
    if c_coa:    out["CoA (Sí/No)"] = df[c_coa]

    order = [c for c in ["PARÁMETRO","MIN","TARGET","MAX","UNIDAD","MÉTODO UTILIZADO","PERIODICIDAD DE CONTROL","CoA (Sí/No)"] if c in out.columns]
    out = out[order]
    out = out[out.apply(lambda r: r.astype(str).str.strip().any(), axis=1)].reset_index(drop=True)
    return dedupe_columns(out)

def extraer_fisicoquimicos(docx_file) -> list[pd.DataFrame]:
    for k in ["parámetros físico-químicos", "parametros fisico-quimicos", "parametros físico-químicos"]:
        tablas = extraer_bloque_mixto_tablas(docx_file, nrm(k), multihdr=True)
        if tablas:
            return [normalize_fisicoquimicos(t) for t in tablas]
    return []

# ---------------- Inciso 5 (Microbiológicos) ----------------
def normalize_microbiologicos(df: pd.DataFrame) -> pd.DataFrame:
    """Flatea 'PLAN DE MUESTREO' (Categoría/Clase/n/c/m/M) y normaliza nombres (incluye m/M de LÍMITE)."""
    if df is None or df.empty:
        return df

    def has_token(col, tokens):
        cl = nrm(col)
        return any(tok in cl for tok in tokens)

    map_cols = {}
    for c in df.columns:
        if has_token(c, ["parámetro","parametro","microorganismo"]): map_cols[c] = "PARÁMETRO"
        elif has_token(c, ["método","metodo","method"]):             map_cols[c] = "MÉTODO"
        elif has_token(c, ["grupo"]):                                map_cols[c] = "GRUPO"
        elif has_token(c, ["plan de muestreo|categor","categoría","categoria"]): map_cols[c] = "CATEGORÍA"
        elif has_token(c, ["plan de muestreo|clase","clase"]):       map_cols[c] = "CLASE"
        elif has_token(c, ["|n", " n "]):                            map_cols[c] = "n"
        elif has_token(c, ["|c", " c "]):                            map_cols[c] = "c"
        elif has_token(c, ["|m", " m "]):                            map_cols[c] = "m"
        elif has_token(c, ["|m ", "|M", " M "]):                     map_cols[c] = "M"
        elif has_token(c, ["límite","limite"]):                      map_cols[c] = "LÍMITE"
        elif has_token(c, ["periodicidad de control","frecuencia","periodicidad"]): map_cols[c] = "PERIODICIDAD DE CONTROL"
        elif has_token(c, ["coa"]):                                  map_cols[c] = "CoA (Sí/No)"

    df2 = df.rename(columns=map_cols)

    # m/M dentro de "LÍMITE (m;M)" -> extraer si faltan
    if "LÍMITE" in df2.columns and ("m" not in df2.columns or "M" not in df2.columns):
        lim = df2["LÍMITE"].astype(str)
        m_vals = lim.str.extract(r"[m]\s*[:=]?\s*([0-9]+(?:[.,][0-9]+)?)", expand=False)
        M_vals = lim.str.extract(r"[M]\s*[:=]?\s*([0-9]+(?:[.,][0-9]+)?)", expand=False)
        if "m" not in df2.columns: df2["m"] = m_vals
        if "M" not in df2.columns: df2["M"] = M_vals

    order = ["PARÁMETRO","MÉTODO","GRUPO","CATEGORÍA","CLASE","n","c","m","M","LÍMITE","PERIODICIDAD DE CONTROL","CoA (Sí/No)"]
    keep = [c for c in order if c in df2.columns]
    out = df2[keep].copy()
    for k in ["n","c","m","M","LÍMITE"]:
        if k in out.columns:
            out[k] = out[k].replace({"-": "", "–": ""})
    out = out[out.apply(lambda r: r.astype(str).str.strip().any(), axis=1)].reset_index(drop=True)
    return dedupe_columns(out)

def extraer_microbiologicos(docx_file) -> list[pd.DataFrame]:
    keys = ["parámetros microbiológicos","parametros microbiologicos","microbiologicos"]
    for k in keys:
        tablas = extraer_bloque_mixto_tablas(docx_file, nrm(k), multihdr=True)
        if tablas:
            return [normalize_microbiologicos(t) for t in tablas]
    return []

# ---------------- Inciso 6 (Micotoxinas) ----------------
def normalize_micotoxinas(df: pd.DataFrame) -> pd.DataFrame:
    """Normaliza tabla de micotoxinas (mapeo flexible: micotoxina, límite, norma/método, periodicidad, CoA)."""
    if df is None or df.empty:
        return df

    def pick_col(keys):
        for c in df.columns:
            if any(k in nrm(c) for k in keys):
                return c
        return None

    out = pd.DataFrame(index=df.index)

    c_micro = pick_col(["micotoxina","aflatox","ocratox","don","zeara","toxina"])
    c_lim   = pick_col(["límite","limite","max","ppm","ppb","µg","ug","mg/kg","μg/kg"])
    c_norma = pick_col(["norma","referencia","reglament","metodo","método","iso","hplc","lc-ms"])
    c_per   = pick_col(["periodicidad de control","frecuencia","periodicidad"])
    c_coa   = pick_col(["coa (sí/no)","coa (si/no)","coa"])

    if c_micro: out["MICOTOXINA"] = df[c_micro]
    else:
        # si no hay columna clara, usar primera
        out["MICOTOXINA"] = df.iloc[:,0]

    if c_lim:   out["LÍMITE"] = df[c_lim]
    if c_norma: out["NORMA / MÉTODO"] = df[c_norma]
    if c_per:   out["PERIODICIDAD DE CONTROL"] = df[c_per]
    if c_coa:   out["CoA (Sí/No)"] = df[c_coa]

    order = [c for c in ["MICOTOXINA","LÍMITE","NORMA / MÉTODO","PERIODICIDAD DE CONTROL","CoA (Sí/No)"] if c in out.columns]
    out = out[order]
    out = out[out.apply(lambda r: r.astype(str).str.strip().any(), axis=1)].reset_index(drop=True)
    return dedupe_columns(out)

def extraer_micotoxinas(docx_file) -> list[pd.DataFrame]:
    keys = ["micotoxinas","micotoxina"]
    for k in keys:
        tablas = extraer_bloque_mixto_tablas(docx_file, nrm(k), multihdr=True)
        if tablas:
            return [normalize_micotoxinas(t) for t in tablas]
    return []

# ---------------- UI ----------------
archivo = st.file_uploader("📂 Sube la especificación (.docx)", type=["docx"])

if archivo:
    # 1) Descripción
    st.subheader("1) Descripción del Producto")
    desc = extraer_descripcion(archivo)
    if desc:
        df_desc = pd.DataFrame([{"Campo":"Descripción del Producto","Valor":desc}])
        df_desc = dedupe_columns(df_desc)
        st.table(df_desc)
        st.download_button("⬇️ Descargar descripción (CSV)", df_desc.to_csv(index=False).encode("utf-8"), "descripcion.csv", "text/csv")
    else:
        st.info("No se encontró el inciso 1 en el documento.")

    st.markdown("---")

    # 2) Composición
    st.subheader("2) Composición del Producto (%) e Ingredientes")
    df_comp, bloque_crudo = extraer_composicion(archivo)
    if not df_comp.empty:
        df_comp = dedupe_columns(df_comp)
        st.table(df_comp)
        st.download_button("⬇️ Descargar composición (CSV)", df_comp.to_csv(index=False).encode("utf-8"), "composicion.csv", "text/csv")
    else:
        st.info("No se detectaron pares Ingrediente + % en el inciso 2.")
        if bloque_crudo:
            with st.expander("Ver texto crudo"):
                st.text("\n".join(bloque_crudo))

    st.markdown("---")

    # 3) Organolépticos
    st.subheader("3) Parámetros organolépticos (tabla)")
    organo_tabs = extraer_organolepticos(archivo)
    if not organo_tabs:
        st.info("No se detectaron tablas en el inciso 3.")
    else:
        for i, df in enumerate(organo_tabs, 1):
            df_clean = coalesce_by_stem(df, ["PARÁMETRO","ESPECIFICACIÓN"])
            keep = [c for c in ["PARÁMETRO","ESPECIFICACIÓN"] if c in df_clean.columns]
            if keep: df_clean = df_clean[keep]
            df_clean = dedupe_columns(df_clean)
            st.caption(f"Tabla organolépticos {i}")
            st.dataframe(df_clean, use_container_width=True)
            st.download_button(f"⬇️ Descargar organolépticos {i} (CSV)",
                               df_clean.to_csv(index=False).encode("utf-8"),
                               f"organolepticos_{i}.csv", "text/csv", key=f"dl_org_{i}")

    st.markdown("---")

    # 4) Físico‑químicos
    st.subheader("4) Parámetros físico‑químicos (tabla)")
    fisq_tabs = extraer_fisicoquimicos(archivo)
    if not fisq_tabs:
        st.info("No se detectaron tablas en el inciso 4.")
    else:
        for i, df in enumerate(fisq_tabs, 1):
            df = dedupe_columns(df)
            st.caption(f"Tabla físico‑químicos {i}")
            st.dataframe(df, use_container_width=True)
            st.download_button(f"⬇️ Descargar físico‑químicos {i} (CSV)",
                               df.to_csv(index=False).encode("utf-8"),
                               f"fisicoquimicos_{i}.csv", "text/csv", key=f"dl_fq_{i}")

    st.markdown("---")

    # 5) Microbiológicos
    st.subheader("5) Parámetros microbiológicos (tabla)")
    micro_tabs = extraer_microbiologicos(archivo)
    if not micro_tabs:
        st.info("No se detectaron tablas en el inciso 5.")
    else:
        for i, df in enumerate(micro_tabs, 1):
            df = dedupe_columns(df)
            st.caption(f"Tabla microbiológicos {i}")
            st.dataframe(df, use_container_width=True)
            st.download_button(f"⬇️ Descargar microbiológicos {i} (CSV)",
                               df.to_csv(index=False).encode("utf-8"),
                               f"microbiologicos_{i}.csv", "text/csv", key=f"dl_micro_{i}")

    st.markdown("---")

    # 6) Micotoxinas
    st.subheader("6) Micotoxinas (tabla)")
    microtox_tabs = extraer_micotoxinas(archivo)
    if not microtox_tabs:
        st.info("No se detectaron tablas en el inciso 6 (Micotoxinas).")
    else:
        for i, df in enumerate(microtox_tabs, 1):
            df = dedupe_columns(df)
            st.caption(f"Tabla micotoxinas {i}")
            st.dataframe(df, use_container_width=True)
            st.download_button(f"⬇️ Descargar micotoxinas {i} (CSV)",
                               df.to_csv(index=False).encode("utf-8"),
                               f"micotoxinas_{i}.csv", "text/csv", key=f"dl_mico_{i}")

else:
    st.info("Sube el .docx para extraer los incisos 1–6.")
