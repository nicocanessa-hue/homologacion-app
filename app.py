def normalize_fisicoquimicos(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return df

    # 1) Colapsar duplicados típicos
    df = coalesce_by_stem(df, [
        "PARÁMETRO", "UNIDAD", "MÉTODO UTILIZADO",
        "PERIODICIDAD DE CONTROL", "CoA (Sí/No)", "ESPECIFICACIÓN"
    ])

    # 2) Detectar columnas que contengan min/target/max
    def find_col(keywords):
        for c in df.columns:
            cl = nrm(c)
            if any(k in cl for k in keywords):
                return c
        return None

    min_col = find_col(["min", "mín"])
    tar_col = find_col(["target", "objetivo"])
    max_col = find_col(["max", "máx", "máximo"])

    # 3) Crear columnas normalizadas
    df["MIN"] = df[min_col] if min_col else ""
    df["TARGET"] = df[tar_col] if tar_col else ""
    df["MAX"] = df[max_col] if max_col else ""

    # 4) Renombrar columna de parámetro si viene con otro nombre
    if "PARÁMETRO" not in df.columns:
        for c in df.columns:
            if "param" in nrm(c):
                df = df.rename(columns={c: "PARÁMETRO"})
                break

    # 5) Selección final de columnas
    keep = [c for c in [
        "PARÁMETRO","MIN","TARGET","MAX",
        "UNIDAD","MÉTODO UTILIZADO","PERIODICIDAD DE CONTROL","CoA (Sí/No)"
    ] if c in df.columns]

    out = df[keep].copy()
    out = out[out.apply(lambda r: r.astype(str).str.strip().any(), axis=1)].reset_index(drop=True)
    return out
