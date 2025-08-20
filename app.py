import os, io, re, json
import pandas as pd
import streamlit as st
import pdfplumber
from docx import Document
from io import BytesIO
from unidecode import unidecode
from rapidfuzz import fuzz, process

# ---------- Config UI ----------
st.set_page_config(page_title="Homologación Pro", page_icon="🧪", layout="wide")
st.title("🧪 Homologación de Materias Primas — PRO")

st.markdown("Sube **Especificación (PDF/DOCX)** y **1..N documentos de Proveedor (PDF/DOCX)**. El sistema extrae texto y **tablas** con múltiples estrategias, normaliza unidades, resuelve **sinónimos ES/EN** y compara.")

# ---------- Utilidades ----------
def nrm(s): return " ".join(unidecode((s or "").lower()).split())

def to_float(x):
    if x is None: return None
    try: return float(str(x).replace(",", "."))
    except: return None

def normalize_unit(val, unit):
    if val is None: return None, unit
    u = (unit or "").strip().lower()
    v = to_float(val)

    # ppm == mg/kg
    if u in ["ppm", "mg/kg", "mg·kg-1", "mg kg-1"]: return v, "ppm"
    # porcentaje
    if u in ["%", "g/100g"]: return v, "%"
    # temp
    if u in ["°f", "f"]: return round((v - 32) * 5/9, 3), "°c"
    if u in ["°c", "c"]: return v, "°c"
    # tiempo
    if u in ["dias","día","d"]: return round(v/30.0, 3), "meses"
    if u in ["mes","meses","m"]: return v, "meses"
    # viscosidad
    if u in ["cp", "cps"]: return v, "cP"
    return v, u

# Sinónimos ES/EN (puedes ampliarlos)
SYN = {
    "vida util": ["vida util","shelf life","expiry","best before","caducidad"],
    "humedad": ["humedad","moisture","water content"],
    "% cacao": ["% cacao","cocoa content","cocoa %","contenido de cacao"],
    "% maltitol": ["% maltitol","maltitol content","polyols","polyols content","polioles"],
    "propiedades fisicoquimicas": ["fisicoquimicas","physicochemical","typical analysis"],
    "propiedades microbiologicas": ["microbiologicas","microbiological"],
    "metales pesados": ["heavy metals","lead","pb","mercury","hg","arsenic","as","cadmium","cd"],
    "aminograma": ["amino acid profile","aminograma","amino acids"],
    "alergenos": ["allergens","contains","may contain","alergenos"],
    "gmo": ["gmo","non-gmo","ogm","genetically modified"],
    "almacenamiento": ["almacenamiento","storage","store at","storage conditions"],
    "envase": ["envase","packaging","empaque","container","drum","bag","sack","ibc"],
    "certificaciones": ["haccp","fssc","brc","iso 22000","kosher","halal","certificaciones"],
    "micotoxinas": ["mycotoxins","aflatoxin","ochratoxin","zearalenone","micotoxinas"],
    "plaguicidas": ["pesticides","mrl","rsa","lmrs","plaguicidas"],
    "viscosidad": ["viscosity","cP","centipoise","viscosidad"],
    "punto de fusion": ["melting point","punto de fusion","m.p."],
}

def std_var(var_raw):
    v = nrm(var_raw)
    # busca por mejor parecido
    best = None; best_score = 0
    for k, alts in SYN.items():
        for a in [k] + alts:
            s = fuzz.partial_ratio(nrm(a), v)
            if s > best_score:
                best_score = s; best = k
    return best if best_score >= 70 else v

# ---------- Extracción de DOCX ----------
def read_docx_text_tables(file):
    doc = Document(file)
    text = "\n".join([p.text for p in doc.paragraphs])

    tables = []
    for t in doc.tables:
        rows = []
        for r in t.rows:
            rows.append([c.text.strip() for c in r.cells])
        if rows: tables.append(pd.DataFrame(rows))
    return text, tables

# ---------- Extracción de PDF ----------
def read_pdf_text_tables_plumber(file):
    text_parts, table_dfs = [], []
    log = []
    with pdfplumber.open(file) as pdf:
        for i, p in enumerate(pdf.pages, 1):
            txt = p.extract_text() or ""
            text_parts.append(txt)
            found = False
            try:
                tbls = p.extract_tables()
                for t in tbls or []:
                    df = pd.DataFrame(t)
                    if df.shape[1] > 1 and df.dropna(how="all").shape[0] > 1:
                        table_dfs.append(df); found = True
            except: pass
            log.append(f"pdfplumber p{i}: tables={'ok' if found else 'none'}")
    return "\n".join(text_parts), table_dfs, log

def try_camelot(file):
    try:
        import camelot
        logs = []
        tdfs = []
        for flavor in ["lattice","stream"]:
            try:
                file.seek(0)
                tables = camelot.read_pdf(file, pages="all", flavor=flavor)
                for t in tables:
                    df = t.df
                    if df.shape[1] > 1 and df.dropna(how="all").shape[0] > 1:
                        tdfs.append(df)
                logs.append(f"camelot {flavor}: {len(tables)} tables")
                if len(tdfs) > 0: break
            except Exception as e:
                logs.append(f"camelot {flavor}: error")
        return tdfs, logs
    except Exception:
        return [], ["camelot: not available"]

def try_tabula(file):
    try:
        import tabula
        file.seek(0)
        dfs = tabula.read_pdf(file, pages="all", multiple_tables=True, stream=True)
        tdfs = []
        for df in dfs or []:
            if isinstance(df, pd.DataFrame) and df.shape[1] > 1 and df.dropna(how="all").shape[0] > 1:
                tdfs.append(df)
        return tdfs, [f"tabula: {len(tdfs)} tables"]
    except Exception:
        return [], ["tabula: not available or failed"]

def extract_text_tables(uploaded):
    name = uploaded.name.lower()
    if name.endswith(".docx"):
        uploaded.seek(0)
        t, dfs = read_docx_text_tables(uploaded)
        return t, dfs, ["docx: ok"]
    elif name.endswith(".pdf"):
        uploaded.seek(0)
        t, dfs, log = read_pdf_text_tables_plumber(uploaded)
        # si no hay tablas o son pocas, intenta camelot/tabula
        if len(dfs) == 0:
            cdfs, clog = try_camelot(uploaded)
            dfs += cdfs; log += clog
        if len(dfs) == 0:
            tdfs, tlog = try_tabula(uploaded)
            dfs += tdfs; log += tlog
        return t, dfs, log
    else:
        uploaded.seek(0)
        text = uploaded.read().decode("utf-8", errors="ignore")
        return text, [], ["txt: ok"]

# ---------- Parseo de valores ----------
# patrón genérico: “var ... op? numero unidad?”
RE_VAL = re.compile(
    r'(?P<var>[A-Za-zÁÉÍÓÚÜÑa-záéíóúüñ %/°\-\(\)\.\,]+?)'
    r'[:\-\s]{0,3}'
    r'(?P<op><=|≥|<=|>=|<|>|=|≤|≥|entre)?\s*'
    r'(?P<num>\d+(?:[.,]\d+)?)?\s*'
    r'(?P<unit>%|ppm|mg/kg|g/100g|cP|°c|°f|meses|dias|días)?',
    re.IGNORECASE
)

def parse_from_text(text):
    rows = []
    s = text or ""
    for m in RE_VAL.finditer(s):
        var = nrm(m.group("var") or "")
        op  = (m.group("op") or "").replace("<=","≤").replace(">=","≥")
        num = m.group("num"); unit = (m.group("unit") or "").lower()
        if num:
            rows.append({"variable_raw": var, "op": op, "val": num, "unit": unit})
    return pd.DataFrame(rows)

def parse_from_tables(dfs):
    rows = []
    for df in dfs:
        # usar primera fila como header si aplica
        df = df.fillna("")
        if df.shape[0] > 1:
            header = [str(x) for x in df.iloc[0].tolist()]
            if any(h.strip() for h in header):
                df.columns = header
                df = df.iloc[1:]
        for _, r in df.iterrows():
            line = " | ".join([str(x) for x in r.tolist()])
            for m in RE_VAL.finditer(line):
                var = nrm(m.group("var") or "")
                op  = (m.group("op") or "").replace("<=","≤").replace(">=","≥")
                num = m.group("num"); unit = (m.group("unit") or "").lower()
                if num:
                    rows.append({"variable_raw": var, "op": op, "val": num, "unit": unit})
    return pd.DataFrame(rows)

def build_spec(df):
    if df.empty:
        return pd.DataFrame(columns=["variable","criterio","unidad_objetivo","op","min","max"])
    # mapear variable y normalizar unidades
    std, ops, vals, units = [], [], [], []
    for _, r in df.iterrows():
        std.append(std_var(r["variable_raw"]))
        v,u = normalize_unit(r["val"], r["unit"])
        ops.append(r["op"]); vals.append(v); units.append(u)
    df["variable"] = std; df["v"] = vals; df["u"] = units; df["op"] = ops

    # consolidar por variable y unidad
    spec = (df.groupby(["variable","u"])
              .agg(min=("v","min"), max=("v","max"))
              .reset_index()
           )
    spec["op"] = spec.apply(lambda r: "entre" if (pd.notna(r["min"]) and pd.notna(r["max"]) and r["min"]!=r["max"]) else ("="), axis=1)
    spec["criterio"] = spec.apply(
        lambda r: (f"entre {r['min']} y {r['max']} {r['u']}" if r["op"]=="entre"
                   else f"= {r['min']} {r['u']}"), axis=1
    )
    return spec.rename(columns={"u":"unidad_objetivo"})[["variable","criterio","unidad_objetivo","op","min","max"]]

def build_provider(df_list):
    rows = []
    for name, df in df_list:
        if df.empty: continue
        for _, r in df.iterrows():
            v,u = normalize_unit(r.get("val"), r.get("unit"))
            rows.append({
                "variable": std_var(r.get("variable_raw","")),
                "valor": v, "unidad": u, "fuente": name
            })
    if not rows:
        return pd.DataFrame(columns=["variable","valor","unidad","fuente"])
    prov = pd.DataFrame(rows)
    # preferir filas con unidad clara
    prov = prov.sort_values(["variable", prov["unidad"].isna(), "fuente"])
    prov = prov.drop_duplicates(subset=["variable"], keep="first")
    return prov

def compare(spec, prov):
    out = []
    pmap = {r["variable"]: r for _, r in prov.iterrows()}
    for _, s in spec.iterrows():
        var = s["variable"]; u = s["unidad_objetivo"]; op = s["op"]
        vmin, vmax = s["min"], s["max"]
        prow = pmap.get(var)

        if prow is None:
            out.append({"Variable": var, "Criterio": s["criterio"], "Proveedor": "—", "Unidad": u or "", "Estado": "No informado", "Fuente": ""})
            continue

        pv = prow["valor"]; pu = prow["unidad"]; fuente = prow["fuente"]
        estado = "Revisar"

        if op=="entre" and pd.notna(pv) and pd.notna(vmin) and pd.notna(vmax):
            if vmin <= pv <= vmax: estado = "Cumple"
            elif pv < vmin: estado = "Supera requisito"
            else: estado = "No cumple"
        elif pd.notna(vmax) and pd.isna(vmin) and pd.notna(pv):
            estado = "Cumple" if pv <= vmax else "No cumple"
        elif pd.notna(vmin) and pd.isna(vmax) and pd.notna(pv):
            estado = "Cumple" if pv >= vmin else "No cumple"
        elif pd.notna(vmin) and pd.notna(vmax) and vmin==vmax and pd.notna(pv):
            estado = "Cumple" if abs(pv - vmin) < 1e-6 else "No cumple"
        elif pd.isna(pv):
            estado = "No informado"

        out.append({"Variable": var, "Criterio": s["criterio"], "Proveedor": pv if pd.notna(pv) else "—",
                    "Unidad": u or pu or "", "Estado": estado, "Fuente": fuente})
    return pd.DataFrame(out)

# ---------- UI: uploads ----------
col1, col2 = st.columns([1,2], gap="large")
with col1:
    st.header("1) Especificación")
    spec_file = st.file_uploader("PDF o DOCX", type=["pdf","docx"])
with col2:
    st.header("2) Documentos de Proveedor")
    prov_files = st.file_uploader("PDF o DOCX (múltiples)", type=["pdf","docx"], accept_multiple_files=True)

run = st.button("Comparar")

if run:
    if not spec_file:
        st.error("Sube la Especificación.")
        st.stop()
    if not prov_files:
        st.error("Sube al menos un documento de proveedor.")
        st.stop()

    # ----- SPEC -----
    st.subheader("Extrayendo Especificación…")
    s_text, s_tables, s_log = extract_text_tables(spec_file)
    st.caption("Log extracción especificación:")
    st.code("\n".join(s_log)[:2000])

    s_df = pd.concat([parse_from_text(s_text), parse_from_tables(s_tables)], ignore_index=True)
    spec_df = build_spec(s_df)
    st.dataframe(spec_df, use_container_width=True)

    # ----- PROV -----
    st.subheader("Consolidando Proveedor…")
    p_rows = []
    p_logs = []
    for f in prov_files:
        t, tbls, lg = extract_text_tables(f); p_logs += [f"{f.name}:"] + lg
        pdf = pd.concat([parse_from_text(t), parse_from_tables(tbls)], ignore_index=True)
        p_rows.append((f.name, pdf))
    st.caption("Log extracción proveedor:")
    st.code("\n".join(p_logs)[:2000])

    prov_df = build_provider(p_rows)
    st.dataframe(prov_df, use_container_width=True)

    # ----- COMPARE -----
    st.subheader("Comparación")
    comp_df = compare(spec_df, prov_df)

    # Orden útil
    priority = ["vida util","humedad","% cacao","% maltitol","propiedades microbiologicas","metales pesados","alergenos","gmo","envase","almacenamiento","certificaciones"]
    comp_df["__ord"] = comp_df["Variable"].apply(lambda v: priority.index(v) if v in priority else 999)
    comp_df = comp_df.sort_values(["__ord","Variable"]).drop(columns="__ord")
    st.dataframe(comp_df, use_container_width=True)

    st.write("**Resumen**")
    st.json(comp_df["Estado"].value_counts().to_dict())

    # Descarga Excel
    out = BytesIO()
    with pd.ExcelWriter(out, engine="openpyxl") as xw:
        spec_df.to_excel(xw, index=False, sheet_name="Checklist")
        prov_df.to_excel(xw, index=False, sheet_name="Proveedor")
        comp_df.to_excel(xw, index=False, sheet_name="Comparacion")
    st.download_button("⬇️ Descargar paquete (Excel)", data=out.getvalue(), file_name="homologacion_pro.xlsx",
                       mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    
    
