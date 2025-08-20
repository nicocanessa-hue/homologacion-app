# ====== BLOQUE ROBUSTO DE EXTRACCIÓN + NORMALIZACIÓN ======
import re, io
import pdfplumber
import pandas as pd
from docx import Document
from unidecode import unidecode
from rapidfuzz import fuzz

# ------------------- Normalización segura (arregla unidecode) -------------------
def nrm(x):
    """Normaliza de forma segura (sin reventar con acentos/símbolos)."""
    try:
        s = str(x)
    except Exception:
        s = ""
    try:
        s = unidecode(s)  # quita tildes, ñ -> n, etc.
    except Exception:
        s = s  # fallback: deja el string como está
    return " ".join(s.lower().split())

# ------------------- Sinónimos ES/EN (puedes ampliar) -------------------
SYN = {
    "vida util": ["vida util","shelf life","expiry","best before","caducidad"],
    "humedad": ["humedad","moisture","water content","% h2o","humidity"],
    "% cacao": ["% cacao","cocoa content","cocoa %","contenido de cacao","% cocoa"],
    "% maltitol": ["% maltitol","maltitol content","polyols","polyols content","polioles"],
    "viscosidad": ["viscosity","cp","cps","centipoise","viscosidad"],
    "punto de fusion": ["melting point","punto de fusion","m.p.","mp"],
    "propiedades fisicoquimicas": ["physicochemical","typical analysis","fisicoquimicas"],
    "propiedades microbiologicas": ["microbiological","microbiologicas"],
    "metales pesados": ["heavy metals","lead","pb","mercury","hg","arsenic","as","cadmium","cd"],
    "aminograma": ["amino acid profile","aminograma","amino acids"],
    "alergenos": ["allergens","contains","may contain","alergenos"],
    "gmo": ["gmo","non-gmo","ogm","genetically modified"],
    "almacenamiento": ["almacenamiento","storage","store at","storage conditions"],
    "envase": ["envase","packaging","empaque","container","drum","bag","sack","ibc"],
    "certificaciones": ["haccp","fssc","brc","iso 22000","kosher","halal","certificaciones"],
}

KEYWORDS = {k for k in SYN.keys()} | {w for lst in SYN.values() for w in lst}

def std_var(var_raw: str) -> str:
    """Devuelve nombre estándar (SYN) si hay match razonable; si no, la versión normalizada."""
    v = nrm(var_raw)
    best, score = None, 0
    for k, alts in SYN.items():
        for a in [k] + alts:
            s = fuzz.partial_ratio(nrm(a), v)
            if s > score:
                score, best = s, k
    return best if score >= 70 else v

def seems_like_var(v: str) -> bool:
    """Descarta basura: debe contener letras y alguna palabra clave de SYN."""
    v2 = nrm(v)
    if len(v2) < 4: return False
    if not re.search(r"[a-z]", v2): return False
    return any(nrm(k) in v2 for k in KEYWORDS)

# ------------------- Normalización de unidades -------------------
def to_float(x):
    try: return float(str(x).replace(",", "."))
    except: return None

def normalize_unit(val, unit):
    """Convierte unidades comunes a un objetivo consistente."""
    if val is None: return None, (unit or "")
    u = (unit or "").strip().lower()
    v = to_float(val)
    # % y g/100g
    if u in ["%", "g/100g"]: return v, "%"
    # ppm == mg/kg
    if u in ["ppm", "mg/kg", "mg kg-1", "mg·kg-1"]: return v, "ppm"
    # temperatura
    if u in ["°f","f"]: return round((v - 32) * 5/9, 3), "°c"
    if u in ["°c","c"]: return v, "°c"
    # tiempo
    if u in ["dias","día","days","d"]: return round((v or 0)/30.0, 3), "meses"
    if u in ["mes","meses","month","months","m"]: return v, "meses"
    # viscosidad
    if u in ["cp","cps"]: return v, "cP"
    return v, u

# ------------------- Lectura de DOCX -------------------
def read_docx_text_tables(file):
    doc = Document(file)
    text = "\n".join([p.text for p in doc.paragraphs])
    tables = []
    for t in doc.tables:
        rows = []
        for r in t.rows:
            rows.append([c.text.strip() for c in r.cells])
        if rows:
            tables.append(pd.DataFrame(rows))
    return text, tables, ["docx: ok"]

# ------------------- Lectura de PDF (3 intentos) -------------------
def read_pdf_text_tables_plumber(file):
    text_parts, table_dfs, log = [], [], []
    with pdfplumber.open(file) as pdf:
        for i, p in enumerate(pdf.pages, 1):
            txt = p.extract_text() or ""
            text_parts.append(txt)
            found = False
            try:
                for t in p.extract_tables() or []:
                    df = pd.DataFrame(t)
                    if df.shape[1] > 1 and df.dropna(how="all").shape[0] > 1:
                        table_dfs.append(df); found = True
            except: pass
            log.append(f"pdfplumber p{i}: tables={'ok' if found else 'none'}")
    return "\n".join(text_parts), table_dfs, log

def try_camelot(file):
    try:
        import camelot
        logs, tdfs = [], []
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
            except Exception:
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
    """Detecta tipo de archivo y saca texto + tablas + log."""
    name = (uploaded.name or "").lower()
    if name.endswith(".docx"):
        uploaded.seek(0)
        return read_docx_text_tables(uploaded)
    elif name.endswith(".pdf"):
        uploaded.seek(0)
        t, dfs, log = read_pdf_text_tables_plumber(uploaded)
        if len(dfs) == 0:
            cdfs, clog = try_camelot(uploaded)
            dfs += cdfs; log += clog
        if len(dfs) == 0:
            tdfs, tlog = try_tabula(uploaded)
            dfs += tdfs; log += tlog
        return t, dfs, log
    else:
        uploaded.seek(0)
        try:
            return uploaded.read().decode("utf-8", errors="ignore"), [], ["txt: ok"]
        except Exception:
            return "", [], ["unknown format"]

# ------------------- Parser genérico (fallback) -------------------
RE_VAL = re.compile(
    r'(?P<var>[A-Za-zÁÉÍÓÚÜÑa-záéíóúüñ %/°\-\(\)\.\,]+?)'
    r'[:\-\s]{0,3}'
    r'(?P<op><=|≥|<=|>=|<|>|=|≤|≥|entre)?\s*'
    r'(?P<num>\d+(?:[.,]\d+)?)?\s*'
    r'(?P<unit>%|ppm|mg/kg|g/100g|cP|°c|°f|meses|dias|days|month|months)?',
    re.IGNORECASE
)

def parse_from_text(text):
    rows = []
    for m in RE_VAL.finditer(text or ""):
        var = (m.group("var") or "").strip()
        if not seems_like_var(var): 
            continue
        op  = (m.group("op") or "").replace("<=","≤").replace(">=","≥")
        num = m.group("num"); unit = (m.group("unit") or "").lower()
        if not num: 
            continue
        rows.append({"variable_raw": var, "op": op, "val": num, "unit": unit})
    return pd.DataFrame(rows)

def parse_from_tables(dfs):
    rows = []
    for df in dfs:
        if df.empty: continue
        df = df.fillna("").astype(str)
        header = df.iloc[0].tolist()
        if any(h.strip() for h in header):
            df.columns = header; df = df.iloc[1:]
        for _, r in df.iterrows():
            line = " | ".join([str(x) for x in r.tolist()])
            for m in RE_VAL.finditer(line):
                var = (m.group("var") or "").strip()
                if not seems_like_var(var): 
                    continue
                op  = (m.group("op") or "").replace("<=","≤").replace(">=","≥")
                num = m.group("num"); unit = (m.group("unit") or "").lower()
                if not num: 
                    continue
                rows.append({"variable_raw": var, "op": op, "val": num, "unit": unit})
    return pd.DataFrame(rows)

# ------------------- Parser por ESQUEMA (Param/Min/Target/Max/Unidad) -------------------
HEADER_MAP = {
    "parametro": ["parametro","parámetro","parameter","item","descripcion","description","test","characteristic"],
    "min": ["min","mín","minimum","lower"],
    "target": ["target","objetivo","typical","nominal"],
    "max": ["max","máx","maximum","upper","limite sup","limit sup"],
    "unidad": ["unidad","unit","units","u.","measure"],
}

def _best_col_index(cols, wanted):
    cols_norm = [nrm(c) for c in cols]
    best_i, best_s = None, 0
    for i, c in enumerate(cols_norm):
        for w in wanted:
            s = fuzz.partial_ratio(w, c)
            if s > best_s:
                best_i, best_s = i, s
    return best_i if best_s >= 70 else None

def extract_table_schema_first(dfs):
    """Devuelve filas con columnas mapeadas (parametro, min, target, max, unidad)."""
    out = []
    for df in dfs:
        if df.empty: continue
        df = df.fillna("").astype(str)
        header = df.iloc[0].tolist()
        if any(h.strip() for h in header):
            df.columns = header; df = df.iloc[1:]
        cols = list(df.columns)

        c_param = _best_col_index(cols, HEADER_MAP["parametro"])
        c_min   = _best_col_index(cols, HEADER_MAP["min"])
        c_tgt   = _best_col_index(cols, HEADER_MAP["target"])
        c_max   = _best_col_index(cols, HEADER_MAP["max"])
        c_unit  = _best_col_index(cols, HEADER_MAP["unidad"])

        # Sólo si al menos Parametro y (Min o Max)
        if c_param is not None and (c_min is not None or c_max is not None):
            for _, r in df.iterrows():
                row = {
                    "parametro": r.iloc[c_param] if c_param is not None else "",
                    "min": r.iloc[c_min] if c_min is not None else "",
                    "target": r.iloc[c_tgt] if c_tgt is not None else "",
                    "max": r.iloc[c_max] if c_max is not None else "",
                    "unidad": r.iloc[c_unit] if c_unit is not None else "",
                }
                if seems_like_var(row["parametro"]):
                    out.append(row)
    return pd.DataFrame(out)

# ------------------- Reglas por variable (mejor semántica) -------------------
def default_op_for(var_std, vmin, vmax):
    v = nrm(var_std)
    if "humedad" in v:
        if vmax is not None: return "≤", None, vmax
        if vmin is not None: return "≥", vmin, None
    if "% cacao" in v or "% maltitol" in v or "polyol" in v:
        if vmin is not None: return "≥", vmin, None
        if vmax is not None: return "≥", vmax, None
    if "viscosidad" in v or "punto de fusion" in v:
        if vmin is not None and vmax is not None: return "entre", vmin, vmax
    if "vida util" in v:
        if vmin is not None: return "≥", vmin, None
        if vmax is not None: return "≥", vmax, None
    # defecto
    if vmin is not None and vmax is not None and vmin != vmax: return "entre", vmin, vmax
    if vmax is not None: return "≤", None, vmax
    if vmin is not None: return "≥", vmin, None
    return "=", vmin, vmax

# ------------------- Builders (Spec / Provider) -------------------
def build_spec_from_schema(schema_df):
    rows = []
    for _, r in schema_df.iterrows():
        var = std_var(r.get("parametro",""))
        vmin = to_float(r.get("min"))
        vmax = to_float(r.get("max"))
        vtg  = to_float(r.get("target"))
        unit = (r.get("unidad") or "").strip().lower()
        if vmin is None and vmax is None and vtg is not None:
            vmin = vtg; vmax = vtg
        op0, mn0, mx0 = default_op_for(var, vmin, vmax)

        if op0 == "≤":
            val_u, uni = normalize_unit(mx0, unit)
            criterio = f"≤ {val_u} {uni}" if val_u is not None else f"≤ ? {uni}"
            rows.append({"variable": var, "criterio": criterio, "unidad_objetivo": uni, "op": "≤", "min": None, "max": val_u})
        elif op0 == "≥":
            val_u, uni = normalize_unit(mn0, unit)
            criterio = f"≥ {val_u} {uni}" if val_u is not None else f"≥ ? {uni}"
            rows.append({"variable": var, "criterio": criterio, "unidad_objetivo": uni, "op": "≥", "min": val_u, "max": None})
        elif op0 == "entre":
            vmin_u, uni = normalize_unit(mn0, unit)
            vmax_u, uni2 = normalize_unit(mx0, unit)
            uni = uni or uni2
            criterio = f"entre {vmin_u} y {vmax_u} {uni}"
            rows.append({"variable": var, "criterio": criterio, "unidad_objetivo": uni, "op": "entre", "min": vmin_u, "max": vmax_u})
        else:
            val_u, uni = normalize_unit(mn0, unit)  # mn0==mx0
            criterio = f"= {val_u} {uni}"
            rows.append({"variable": var, "criterio": criterio, "unidad_objetivo": uni, "op": "=", "min": val_u, "max": val_u})

    if not rows:
        return pd.DataFrame(columns=["variable","criterio","unidad_objetivo","op","min","max"])
    return pd.DataFrame(rows).drop_duplicates(subset=["variable"], keep="first")

def build_spec_fallback(text, tables):
    df = pd.concat([parse_from_text(text), parse_from_tables(tables)], ignore_index=True)
    if df.empty:
        return pd.DataFrame(columns=["variable","criterio","unidad_objetivo","op","min","max"])

    out = []
    grp = (df.assign(variable=lambda d: d["variable_raw"].apply(std_var))
             .assign(val=lambda d: d["val"].apply(to_float))
             .assign(unit=lambda d: d["unit"].fillna(""))
             .groupby(["variable","unit"], as_index=False)
             .agg(min=("val","min"), max=("val","max")))

    for _, r in grp.iterrows():
        op0, mn0, mx0 = default_op_for(r["variable"], r["min"], r["max"])
        unit = r["unit"]
        if op0 == "entre":
            criterio = f"entre {mn0} y {mx0} {unit}"
        elif op0 == "≤":
            criterio = f"≤ {mx0} {unit}"
        elif op0 == "≥":
            criterio = f"≥ {mn0} {unit}"
        else:
            criterio = f"= {mn0} {unit}"
        out.append({"variable": r["variable"], "criterio": criterio, "unidad_objetivo": unit,
                    "op": op0, "min": mn0 if op0!="≤" else None, "max": mx0 if op0!="≥" else None})
    return pd.DataFrame(out).drop_duplicates(subset=["variable"], keep="first")

VALID_UNITS = {"%","ppm","cp","°c","meses","mg/kg"}

def build_provider(docs):
    """docs = [(name, text, tables), ...]"""
    rows = []
    for name, text, tables in docs:
        schema = extract_table_schema_first(tables)
        if not schema.empty:
            for _, r in schema.iterrows():
                var = std_var(r.get("parametro",""))
                if not seems_like_var(var): continue
                vmin = to_float(r.get("min")); vmax = to_float(r.get("max")); vtg = to_float(r.get("target"))
                unit = (r.get("unidad") or "").strip().lower()
                cand = vmax if vmax is not None else (vmin if vmin is not None else vtg)
                val, uni = normalize_unit(cand, unit)
                if val is None and not uni: continue
                rows.append({"variable": var, "valor": val, "unidad": uni, "fuente": name})

        gen = pd.concat([parse_from_text(text), parse_from_tables(tables)], ignore_index=True)
        for _, r in gen.iterrows():
            var = std_var(r["variable_raw"])
            if not seems_like_var(var): continue
            val, uni = normalize_unit(r["val"], r["unit"])
            if val is None and not uni: continue
            rows.append({"variable": var, "valor": val, "unidad": uni, "fuente": name})

    if not rows:
        return pd.DataFrame(columns=["variable","valor","unidad","fuente"])

    prov = pd.DataFrame(rows)
    prov["unit_score"] = prov["unidad"].apply(lambda u: 0 if (u or "") in VALID_UNITS else 1)
    prov = prov.sort_values(["variable","unit_score","fuente"]).drop_duplicates(subset=["variable"], keep="first")
    return prov.drop(columns=["unit_score"])
# ====== FIN DEL BLOQUE ======
