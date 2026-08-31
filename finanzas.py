# -*- coding: utf-8 -*-
"""
finanzas.py
-----------
Toda la lógica del Dashboard Financiero que no es interfaz:
- Modelos de datos por defecto (categorías, reglas de categorización, cuentas).
- Parseo de extractos bancarios en PDF (ING, Trade Republic, genérico) e imágenes (Edenred).
- Categorización automática por reglas (regex) editables.
- Cálculo de KPIs y construcción de los gráficos (Plotly) para los 3 dashboards.

Nada de este archivo depende de Streamlit: es reutilizable y fácil de testear.
"""
from __future__ import annotations

import hashlib
import io
import re
from datetime import datetime

import pandas as pd
import plotly.graph_objects as go

# --------------------------------------------------------------------------------------
# Paleta de colores (paleta categórica validada para accesibilidad — orden fijo, no ciclar)
# --------------------------------------------------------------------------------------
PALETTE = [
    "#2a78d6",  # azul
    "#eb6834",  # naranja
    "#1baf7a",  # aguamarina
    "#eda100",  # amarillo
    "#e87ba4",  # magenta
    "#008300",  # verde
    "#4a3aa7",  # violeta
    "#e34948",  # rojo
]
COLOR_INGRESO = "#1baf7a"
COLOR_GASTO = "#e34948"
COLOR_AHORRO = "#2a78d6"
COLOR_MUTED = "#898781"
COLOR_GRID = "#e1e0d9"
COLOR_TEXT = "#0b0b0b"
COLOR_TEXT_SECONDARY = "#52514e"

PLOT_FONT = dict(family="system-ui, -apple-system, Segoe UI, sans-serif", color=COLOR_TEXT)


def _base_layout(fig: go.Figure, title: str | None = None, height: int = 380) -> go.Figure:
    fig.update_layout(
        title=dict(text=title, font=dict(size=16, color=COLOR_TEXT)) if title else None,
        font=PLOT_FONT,
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        height=height,
        margin=dict(l=10, r=10, t=50 if title else 20, b=10),
        legend=dict(orientation="h", yanchor="bottom", y=-0.25, x=0, font=dict(size=11)),
        hoverlabel=dict(bgcolor="white", font_size=12),
    )
    fig.update_xaxes(showgrid=False, zeroline=False, linecolor=COLOR_GRID)
    fig.update_yaxes(showgrid=True, gridcolor=COLOR_GRID, zeroline=False)
    return fig


# ========================================================================================
# 1) DATOS POR DEFECTO
# ========================================================================================

def default_categorias() -> pd.DataFrame:
    """Catálogo de categorías por defecto. El usuario puede editarlo libremente en la app."""
    data = [
        ("Salario", "Ingreso"),
        ("Otros ingresos", "Ingreso"),
        ("Bizum recibido", "Ingreso"),
        ("Alimentacion", "Gasto"),
        ("Transporte", "Gasto"),
        ("Vivienda", "Gasto"),
        ("Salud", "Gasto"),
        ("Ropa", "Gasto"),
        ("Deporte", "Gasto"),
        ("Suscripciones", "Gasto"),
        ("Viajes", "Gasto"),
        ("Educacion", "Gasto"),
        ("Ocio", "Gasto"),
        ("Bizum enviado", "Gasto"),
        ("Otros gastos", "Gasto"),
        ("Inversion", "Transferencia"),
        ("Transferencia interna", "Transferencia"),
    ]
    return pd.DataFrame(data, columns=["Categoria", "Tipo"])


def default_reglas() -> pd.DataFrame:
    """Reglas de categorización automática: se evalúan en orden (Prioridad ascendente),
    la primera cuyo patrón (regex, sin distinguir mayúsculas) aparezca en el concepto gana."""
    reglas = [
        # Transferencias internas / inversión primero: si no, un ingreso de tu propia cuenta
        # de inversión podría categorizarse como "Salario" u "Otros ingresos".
        (r"traspaso|transferencia.*(propia|misma titularidad)", "Transferencia interna"),
        (r"cuenta naranja|remunerada", "Transferencia interna"),
        (r"compra.*(accion|etf|fondo)|inversion|invesion|trade republic invest|degiro|indexa", "Inversion"),
        (r"nomina|n[oó]mina|payroll", "Salario"),
        (r"bizum de|bizum recibido", "Bizum recibido"),
        (r"bizum a|bizum enviado|bizum para", "Bizum enviado"),
        (r"mercadona|carrefour|lidl|dia %|alcampo|supermercado|eroski|fruteria|panaderia", "Alimentacion"),
        (r"glovo|uber eats|just eat|deliveroo|restaurante|cafeteria|bar el|burger|mcdonald|kfc", "Alimentacion"),
        (r"uber|cabify|renfe|metro|emt|bus |gasolina|repsol|cepsa cepsa|bp |parking|peaje", "Transporte"),
        (r"alquiler|hipoteca|comunidad de propietarios|iberdrola|endesa|naturgy|agua |internet|movistar|vodafone|orange", "Vivienda"),
        (r"farmacia|seguro salud|mutua|dentista|clinica|hospital", "Salud"),
        (r"zara|h&m|inditex|primark|decathlon ropa|el corte ingles moda", "Ropa"),
        (r"gimnasio|decathlon|basic ?fit|padel|futbol", "Deporte"),
        (r"netflix|spotify|hbo|disney|amazon prime|youtube premium|icloud|dropbox|apple\.com", "Suscripciones"),
        (r"booking|airbnb|vueling|ryanair|iberia|renfe ave|hotel", "Viajes"),
        (r"universidad|academia|curso|udemy|coursera", "Educacion"),
        (r"cine|teatro|concierto|steam|playstation|xbox|ocio", "Ocio"),
        (r"seguro|impuesto|hacienda|dgt|multa", "Otros gastos"),
    ]
    return pd.DataFrame(reglas, columns=["Patron", "Categoria"]).reset_index().rename(
        columns={"index": "Prioridad"}
    )[["Prioridad", "Patron", "Categoria"]]


def default_cuentas() -> pd.DataFrame:
    """Catálogo de cuentas por defecto (editable). TipoCuenta se usa para separar
    activos de deudas en el cálculo de patrimonio neto."""
    data = [
        ("ING Corriente", "Banco"),
        ("Trade Republic (efectivo)", "Banco"),
        ("Cartera inversion TR (coste)", "Inversion"),
        ("Edenred (ticket restaurante)", "Efectivo"),
    ]
    return pd.DataFrame(data, columns=["Cuenta", "TipoCuenta"])


def empty_transacciones() -> pd.DataFrame:
    return pd.DataFrame(
        columns=["id", "Fecha", "Cuenta", "Concepto", "Importe", "Categoria", "Tipo", "Origen"]
    )


def empty_saldos() -> pd.DataFrame:
    return pd.DataFrame(columns=["Fecha", "Cuenta", "TipoCuenta", "Saldo", "Notas"])


def empty_presupuesto() -> pd.DataFrame:
    return pd.DataFrame(columns=["Anio", "Mes", "Categoria", "Presupuesto"])


# ========================================================================================
# 2) CATEGORIZACIÓN
# ========================================================================================

def categorize(concepto: str, importe: float, reglas: pd.DataFrame) -> str:
    """Aplica las reglas en orden de prioridad. Si ninguna coincide, usa Bizum u
    'Otros ingresos'/'Otros gastos' como último recurso según el signo del importe."""
    texto = (concepto or "").lower()
    for _, row in reglas.sort_values("Prioridad").iterrows():
        patron = str(row["Patron"])
        try:
            if re.search(patron, texto, flags=re.IGNORECASE):
                return row["Categoria"]
        except re.error:
            continue
    if "bizum" in texto:
        return "Bizum recibido" if importe >= 0 else "Bizum enviado"
    return "Otros ingresos" if importe >= 0 else "Otros gastos"


def tipo_de_categoria(categoria: str, categorias: pd.DataFrame, importe: float) -> str:
    match = categorias.loc[categorias["Categoria"] == categoria, "Tipo"]
    if len(match):
        return match.iloc[0]
    return "Ingreso" if importe >= 0 else "Gasto"


def recategorizar(df: pd.DataFrame, reglas: pd.DataFrame, categorias: pd.DataFrame) -> pd.DataFrame:
    """Recalcula Categoria/Tipo para las filas cuya Categoria esté vacía (no toca las que
    el usuario ya haya corregido a mano)."""
    df = df.copy()
    mask = df["Categoria"].isna() | (df["Categoria"].astype(str).str.strip() == "")
    df.loc[mask, "Categoria"] = df.loc[mask].apply(
        lambda r: categorize(r["Concepto"], r["Importe"], reglas), axis=1
    )
    df["Tipo"] = df.apply(
        lambda r: tipo_de_categoria(r["Categoria"], categorias, r["Importe"]), axis=1
    )
    return df


# ========================================================================================
# 3) PARSEO DE EXTRACTOS (PDF / imágenes)
# ========================================================================================

_DATE_RE = re.compile(r"\b(\d{1,2})[\/\-\.](\d{1,2})[\/\-\.](\d{2,4})\b")
_AMOUNT_RE = re.compile(r"-?\d{1,3}(?:[.\s]\d{3})*,\d{2}\s?€?|-?\d+,\d{2}\s?€?")


def _parse_importe_es(s: str) -> float | None:
    s = s.strip().replace("€", "").replace(" ", "")
    neg = s.startswith("-")
    s = s.lstrip("-")
    s = s.replace(".", "").replace(",", ".")
    try:
        val = float(s)
    except ValueError:
        return None
    return -val if neg else val


def _parse_fecha(d: str, m: str, y: str) -> str | None:
    if len(y) == 2:
        y = "20" + y
    try:
        return datetime(int(y), int(m), int(d)).strftime("%Y-%m-%d")
    except ValueError:
        return None


def extract_pdf_text(file) -> str:
    import pdfplumber

    text_parts = []
    with pdfplumber.open(file) as pdf:
        for page in pdf.pages:
            t = page.extract_text() or ""
            text_parts.append(t)
    return "\n".join(text_parts)


def parse_statement_text(text: str, cuenta: str) -> pd.DataFrame:
    """Parser genérico línea a línea: busca una fecha al principio de la línea y, tras
    ella, el/los importe(s) en formato español. Funciona razonablemente con extractos
    tabulares de la mayoría de bancos españoles, pero SIEMPRE hay que revisar el
    resultado en la tabla editable antes de confirmar la importación — ningún parser
    genérico es 100% fiable con el PDF de un banco que no ha visto antes."""
    rows = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        date_match = _DATE_RE.match(line) or _DATE_RE.search(line[:12])
        if not date_match:
            continue
        fecha = _parse_fecha(*date_match.groups())
        if not fecha:
            continue
        resto = line[date_match.end():].strip()
        amounts = _AMOUNT_RE.findall(resto)
        if not amounts:
            continue
        importe = _parse_importe_es(amounts[0])
        if importe is None:
            continue
        # El concepto es el texto antes del primer importe encontrado.
        idx = resto.find(amounts[0])
        concepto = resto[:idx].strip(" -|\t")
        if not concepto:
            concepto = "(sin concepto)"
        rows.append({"Fecha": fecha, "Cuenta": cuenta, "Concepto": concepto, "Importe": importe})
    return pd.DataFrame(rows, columns=["Fecha", "Cuenta", "Concepto", "Importe"])


def parse_statement_pdf(file, cuenta: str) -> pd.DataFrame:
    text = extract_pdf_text(file)
    return parse_statement_text(text, cuenta)


def parse_image_ocr(file, cuenta: str) -> pd.DataFrame:
    """Intenta extraer movimientos de una imagen (p.ej. capturas de Edenred) vía OCR.
    Requiere que tesseract esté instalado (ver packages.txt). Si falla, devuelve un
    DataFrame vacío para que el usuario añada las filas a mano."""
    try:
        import pytesseract
        from PIL import Image
    except ImportError:
        return pd.DataFrame(columns=["Fecha", "Cuenta", "Concepto", "Importe"])
    try:
        img = Image.open(file)
        text = pytesseract.image_to_string(img, lang="spa")
    except Exception:
        return pd.DataFrame(columns=["Fecha", "Cuenta", "Concepto", "Importe"])
    return parse_statement_text(text, cuenta)


def make_ids(df: pd.DataFrame) -> pd.Series:
    """Huella única por movimiento (fecha+cuenta+concepto+importe) para poder detectar
    duplicados al reimportar un mes que ya estaba cargado."""

    def _h(row):
        raw = f"{row['Fecha']}|{row['Cuenta']}|{row['Concepto']}|{round(float(row['Importe']), 2)}"
        return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]

    return df.apply(_h, axis=1)


def dedupe(nuevas: pd.DataFrame, existentes: pd.DataFrame) -> tuple[pd.DataFrame, int]:
    if "id" not in nuevas.columns:
        nuevas = nuevas.copy()
        nuevas["id"] = make_ids(nuevas)
    ids_existentes = set(existentes["id"]) if "id" in existentes.columns and len(existentes) else set()
    antes = len(nuevas)
    nuevas = nuevas[~nuevas["id"].isin(ids_existentes)]
    return nuevas, antes - len(nuevas)


# ========================================================================================
# 4) KPIs Y AGREGACIONES
# ========================================================================================

def filtrar_mes(tx: pd.DataFrame, anio: int, mes: int) -> pd.DataFrame:
    if tx.empty:
        return tx
    fechas = pd.to_datetime(tx["Fecha"])
    return tx[(fechas.dt.year == anio) & (fechas.dt.month == mes)]


def kpis_mes(tx_mes: pd.DataFrame) -> dict:
    ingresos = tx_mes.loc[tx_mes["Tipo"] == "Ingreso", "Importe"].sum()
    gastos = -tx_mes.loc[tx_mes["Tipo"] == "Gasto", "Importe"].sum()
    ahorro = ingresos - gastos
    pct = (ahorro / ingresos) if ingresos else 0.0
    return {"ingresos": ingresos, "gastos": gastos, "ahorro": ahorro, "pct_ahorro": pct}


def gasto_por_categoria(tx_mes: pd.DataFrame) -> pd.DataFrame:
    df = tx_mes[tx_mes["Tipo"] == "Gasto"].copy()
    if df.empty:
        return pd.DataFrame(columns=["Categoria", "Real"])
    g = (-df.groupby("Categoria")["Importe"].sum()).reset_index(name="Real")
    return g.sort_values("Real", ascending=False)


# ========================================================================================
# 5) GRÁFICOS (Plotly)
# ========================================================================================

def fig_donut_categorias(gasto_cat: pd.DataFrame) -> go.Figure:
    """Donut de gasto por categoría. A diferencia de una hoja de cálculo, aquí basta con
    no incluir las categorías sin gasto en el DataFrame — no hace falta ningún truco de
    formato de número para que Plotly no dibuje ni etiquete porciones al 0%."""
    df = gasto_cat[gasto_cat["Real"] > 0]
    fig = go.Figure(
        go.Pie(
            labels=df["Categoria"],
            values=df["Real"],
            hole=0.6,
            marker=dict(colors=(PALETTE * 3)[: len(df)], line=dict(color="#fcfcfb", width=2)),
            textinfo="percent",
            textfont=dict(size=12, color=COLOR_TEXT),
            hovertemplate="%{label}: %{value:.2f} € (%{percent})<extra></extra>",
        )
    )
    return _base_layout(fig, "Gasto por categoría", height=380)


def fig_bar_presupuesto(gasto_cat: pd.DataFrame, presupuesto_mes: pd.DataFrame) -> go.Figure:
    df = gasto_cat.merge(presupuesto_mes[["Categoria", "Presupuesto"]], on="Categoria", how="outer").fillna(0)
    df = df[(df["Real"] > 0) | (df["Presupuesto"] > 0)].sort_values("Real", ascending=False)
    fig = go.Figure()
    fig.add_bar(name="Real", x=df["Categoria"], y=df["Real"], marker_color=PALETTE[0])
    fig.add_bar(name="Presupuesto", x=df["Categoria"], y=df["Presupuesto"], marker_color=PALETTE[3])
    fig.update_layout(barmode="group")
    return _base_layout(fig, "Presupuesto vs. gasto real", height=380)


def fig_bar_ingresos_gastos_ahorro(k: dict) -> go.Figure:
    fig = go.Figure(
        go.Bar(
            x=["Ingresos", "Gastos", "Ahorro"],
            y=[k["ingresos"], k["gastos"], k["ahorro"]],
            marker_color=[COLOR_INGRESO, COLOR_GASTO, COLOR_AHORRO],
            text=[f"{v:,.0f} €".replace(",", ".") for v in (k["ingresos"], k["gastos"], k["ahorro"])],
            textposition="outside",
        )
    )
    return _base_layout(fig, "Ingresos vs. gastos vs. ahorro", height=340)


def fig_bar_top5(gasto_cat: pd.DataFrame) -> go.Figure:
    df = gasto_cat.head(5).sort_values("Real")
    fig = go.Figure(
        go.Bar(
            x=df["Real"], y=df["Categoria"], orientation="h",
            marker_color=PALETTE[1],
            text=[f"{v:,.0f} €".replace(",", ".") for v in df["Real"]],
            textposition="outside",
        )
    )
    return _base_layout(fig, "Top 5 categorías de gasto", height=340)


def fig_line_diario(tx_mes: pd.DataFrame, anio: int, mes: int) -> go.Figure:
    import calendar

    n_dias = calendar.monthrange(anio, mes)[1]
    gastos_dia = pd.Series(0.0, index=range(1, n_dias + 1))
    df = tx_mes[tx_mes["Tipo"] == "Gasto"].copy()
    if not df.empty:
        df["dia"] = pd.to_datetime(df["Fecha"]).dt.day
        agg = -df.groupby("dia")["Importe"].sum()
        gastos_dia.update(agg)
    acumulado = gastos_dia.cumsum()
    fig = go.Figure(
        go.Scatter(
            x=list(acumulado.index), y=acumulado.values, mode="lines",
            line=dict(color=PALETTE[0], width=2), fill="tozeroy",
            fillcolor="rgba(42,120,214,0.12)",
            hovertemplate="Día %{x}: %{y:.2f} € acumulado<extra></extra>",
        )
    )
    fig.update_xaxes(title="Día del mes")
    fig.update_yaxes(title="€ acumulado")
    return _base_layout(fig, "Evolución del gasto en el mes (acumulado)", height=340)


def fig_donut_patrimonio(saldos_actuales: pd.DataFrame) -> go.Figure:
    df = saldos_actuales[saldos_actuales["Saldo"] != 0]
    fig = go.Figure(
        go.Pie(
            labels=df["Cuenta"], values=df["Saldo"].abs(), hole=0.6,
            marker=dict(colors=(PALETTE * 3)[: len(df)], line=dict(color="#fcfcfb", width=2)),
            textinfo="percent", textfont=dict(size=12, color=COLOR_TEXT),
            hovertemplate="%{label}: %{value:.2f} € (%{percent})<extra></extra>",
        )
    )
    return _base_layout(fig, "Distribución del patrimonio", height=380)


def fig_line_patrimonio(saldos_hist: pd.DataFrame) -> go.Figure:
    if saldos_hist.empty:
        return _base_layout(go.Figure(), "Evolución del patrimonio", height=340)
    df = saldos_hist.copy()
    df["Fecha"] = pd.to_datetime(df["Fecha"])
    activos = df[df["TipoCuenta"] != "Tarjeta de credito"].groupby("Fecha")["Saldo"].sum()
    deuda = df[df["TipoCuenta"] == "Tarjeta de credito"].groupby("Fecha")["Saldo"].sum()
    neto = activos.sub(deuda, fill_value=0)
    fig = go.Figure(
        go.Scatter(
            x=neto.index, y=neto.values, mode="lines+markers",
            line=dict(color=PALETTE[0], width=2), marker=dict(size=8),
            hovertemplate="%{x|%b %Y}: %{y:,.2f} €<extra></extra>",
        )
    )
    return _base_layout(fig, "Evolución del patrimonio neto", height=340)


def fig_bar_anual(tabla_anual: pd.DataFrame) -> go.Figure:
    fig = go.Figure()
    fig.add_bar(name="Ingresos", x=tabla_anual["Mes"], y=tabla_anual["Ingresos"], marker_color=COLOR_INGRESO)
    fig.add_bar(name="Gastos", x=tabla_anual["Mes"], y=tabla_anual["Gastos"], marker_color=COLOR_GASTO)
    fig.add_bar(name="Ahorro", x=tabla_anual["Mes"], y=tabla_anual["Ahorro"], marker_color=COLOR_AHORRO)
    fig.update_layout(barmode="group")
    return _base_layout(fig, "Ingresos, gastos y ahorro por mes", height=400)


def fig_line_anual(tabla_anual: pd.DataFrame) -> go.Figure:
    fig = go.Figure()
    for col, color in [("Ingresos", COLOR_INGRESO), ("Gastos", COLOR_GASTO), ("Ahorro", COLOR_AHORRO)]:
        fig.add_scatter(
            x=tabla_anual["Mes"], y=tabla_anual[col], mode="lines+markers", name=col,
            line=dict(color=color, width=2), marker=dict(size=7),
        )
    return _base_layout(fig, "Evolución mensual (línea)", height=400)


def tabla_anual(tx: pd.DataFrame, anio: int) -> pd.DataFrame:
    meses = ["Ene", "Feb", "Mar", "Abr", "May", "Jun", "Jul", "Ago", "Sep", "Oct", "Nov", "Dic"]
    rows = []
    for m in range(1, 13):
        tx_mes = filtrar_mes(tx, anio, m)
        k = kpis_mes(tx_mes)
        rows.append({"Mes": meses[m - 1], "Ingresos": k["ingresos"], "Gastos": k["gastos"], "Ahorro": k["ahorro"]})
    return pd.DataFrame(rows)


# ========================================================================================
# 6) EXPORTACIÓN
# ========================================================================================

def to_zip_bytes(dfs: dict[str, pd.DataFrame]) -> bytes:
    import zipfile

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, df in dfs.items():
            zf.writestr(f"{name}.csv", df.to_csv(index=False))
    return buf.getvalue()
