import re
import unicodedata
import pandas as pd
import streamlit as st
from docx import Document
from docx.oxml.ns import qn
from docx.document import Document as _Document
from docx.table import _Cell, Table as _Table
from docx.text.paragraph import Paragraph

st.set_page_config(page_title="Especificación · Incisos 1-3", page_icon="📄", layout="centered")
st.title("Especificación · Incisos 1 (Descripción), 2 (Composición) y 3 (Organolépticos)")

# ---------------- Utils ----------------
def nrm(s: str) -> str:
    s = "" if s is None else str(s).strip()
    s = "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn")
    s = re.sub(r"\s+", " ", s)
    return s.lower()

def es_titulo_numerado(texto: str) -> bool:
    return bool(re.match(r"^\s*\d+(\.| )", texto or ""))

def iter_block_items(parent):
    """Itera párrafos y tablas en orden."""
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

def table_to_df(tbl: _Table) -> pd.DataFrame:
    """Convierte una tabla DOCX en DataFrame (header = 1ª fila)."""
    rows = []
    for r in tbl.rows:
        cells = [(" ".join(p.text for p in cell.paragraphs)).strip() for cell in r.cells]
        cells = [" ".join(x.split()) for x in cells]
        rows.append(cells)
    if not rows:
        return pd.DataFrame()
    max_cols = max(len(r) for r in rows)
    rows = [r + [""] * (max_cols - len(r)) for r in rows]
    header = make_unique(rows[0])
    body = rows[1:] if len(rows) > 1 else []
    return pd.DataFrame(body, columns=header) if body else pd.DataFrame(columns=header)

def extraer_bloque_por_titulo_parrafos(docx_file, contiene_titulo_norm: str) -> list[str]:
    """Solo párrafos entre el título buscado y el siguiente inciso numerado."""
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

def extraer_bloque_mixto_tablas(docx_file, contiene_titulo_norm: str):
    """Devuelve todas las tablas entre el título buscado y el siguiente inciso."""
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
            tablas.append(table_to_df(b))
    return tablas

# --- helper para colapsar encabezados duplicados por prefijo (PARÁMETRO, ESPECIFICACIÓN, etc.) ---
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

# ---- Inciso 1: Descripción del Producto ----
def extraer_descripcion(docx_file) -> str:
    bloque = extraer_bloque_por_titulo_parrafos(docx_file, "descripcion del producto")
    return " ".join(bloque).strip()

# ---- Inciso 2: Composición e Ingredientes ----
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

# ---- Inciso 3: Parámetros organolépticos (tabla) ----
def extraer_organolepticos(docx_file) -> list[pd.DataFrame]:
    keys = [
        "parametros organolepticos",
        "parámetros organolépticos",
    ]
    for k in keys:
        tablas = extraer_bloque_mixto_tablas(docx_file, nrm(k))
        if tablas:
            return tablas
    return []

# ---------------- UI ----------------
archivo = st.file_uploader("📂 Sube la especificación (.docx)", type=["docx"])

if archivo:
    # 1) Descripción
    st.subheader("1) Descripción del Producto")
    descripcion = extraer_descripcion(archivo)
    if descripcion:
        df_desc = pd.DataFrame([{"Campo": "Descripción del Producto", "Valor": descripcion}])
        st.table(df_desc)
        st.download_button("⬇️ Descargar descripción (CSV)",
                           data=df_desc.to_csv(index=False).encode("utf-8"),
                           file_name="descripcion_producto.csv",
                           mime="text/csv")
    else:
        st.warning("No se encontró el inciso 'Descripción del Producto'.")

    st.markdown("---")

    # 2) Composición
    st.subheader("2) Composición del Producto (%) e Ingredientes")
    df_comp, bloque_crudo = extraer_composicion(archivo)
    if not df_comp.empty:
        st.table(df_comp)
        st.download_button("⬇️ Descargar composición (CSV)",
                           data=df_comp.to_csv(index=False).encode("utf-8"),
                           file_name="composicion_ingredientes.csv",
                           mime="text/csv")
    else:
        st.warning("No se detectaron pares 'Ingrediente + %' en el inciso 2.")
        with st.expander("Ver texto crudo del inciso 2"):
            st.text("\n".join(bloque_crudo) if bloque_crudo else "—")

    st.markdown("---")

    # 3) Organolépticos
    st.subheader("3) Parámetros organolépticos (tabla)")
    organo_tabs = extraer_organolepticos(archivo)
    if not organo_tabs:
        st.warning("No se detectaron tablas en el inciso 3.")
    else:
        for i, df in enumerate(organo_tabs, 1):
            # Limpia duplicados de encabezado (PARÁMETRO, ESPECIFICACIÓN, etc.)
            df_clean = coalesce_by_stem(df, ["PARÁMETRO", "ESPECIFICACIÓN"])
            keep = [c for c in ["PARÁMETRO", "ESPECIFICACIÓN"] if c in df_clean.columns]
            if keep:
                df_clean = df_clean[keep]
            st.caption(f"Tabla organolépticos {i}")
            st.dataframe(df_clean, use_container_width=True)
            st.download_button(
                f"⬇️ Descargar organolépticos {i} (CSV)",
                data=df_clean.to_csv(index=False).encode("utf-8"),
                file_name=f"organolepticos_{i}.csv",
                mime="text/csv",
                key=f"dl_org_{i}"
            )
else:
    st.info("Sube el .docx para extraer los incisos 1, 2 y 3.")
