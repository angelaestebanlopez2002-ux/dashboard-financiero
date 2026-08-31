# -*- coding: utf-8 -*-
"""
Dashboard Financiero — app de Streamlit
----------------------------------------
Sube tus extractos bancarios cada mes, revisa los movimientos detectados,
y consulta tus 3 dashboards: Patrimonio, Análisis mensual y Evolución anual.

IMPORTANTE sobre persistencia: Streamlit Community Cloud NO guarda archivos
entre reinicios de la app. Por eso todo tu histórico vive en esta sesión y
se descarga/sube como CSV — ver el bloque "Tus datos" en la barra lateral y
el README del proyecto para el flujo de trabajo mensual completo.
"""
import io
from datetime import date

import pandas as pd
import streamlit as st

import finanzas as fz

st.set_page_config(page_title="Dashboard Financiero", page_icon="💶", layout="wide")

MESES = ["Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio", "Julio",
         "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre"]

# ----------------------------------------------------------------------------------
# Estado inicial
# ----------------------------------------------------------------------------------
def _init_state():
    defaults = {
        "transacciones": fz.empty_transacciones(),
        "categorias": fz.default_categorias(),
        "reglas": fz.default_reglas(),
        "cuentas": fz.default_cuentas(),
        "saldos": fz.empty_saldos(),
        "presupuesto": fz.empty_presupuesto(),
        "pendientes": None,  # DataFrame de movimientos extraídos, en revisión
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v


_init_state()


def _read_csv_upload(file, cols=None) -> pd.DataFrame:
    df = pd.read_csv(file)
    if cols:
        for c in cols:
            if c not in df.columns:
                df[c] = None
        df = df[cols]
    return df


# ====================================================================================
# BARRA LATERAL
# ====================================================================================
with st.sidebar:
    st.title("💶 Dashboard Financiero")

    with st.expander("📂 Tus datos (cargar progreso guardado)", expanded=len(st.session_state["transacciones"]) == 0):
        st.caption(
            "Esta app no guarda nada entre sesiones. Sube aquí el ZIP o los CSV que "
            "descargaste la última vez para continuar donde lo dejaste."
        )
        zip_up = st.file_uploader("Restaurar desde ZIP (recomendado)", type=["zip"], key="zip_up")
        if zip_up is not None:
            import zipfile

            with zipfile.ZipFile(zip_up) as zf:
                names = zf.namelist()
                if "transacciones.csv" in names:
                    with zf.open("transacciones.csv") as f:
                        st.session_state["transacciones"] = pd.read_csv(f)
                if "categorias.csv" in names:
                    with zf.open("categorias.csv") as f:
                        st.session_state["categorias"] = pd.read_csv(f)
                if "reglas.csv" in names:
                    with zf.open("reglas.csv") as f:
                        st.session_state["reglas"] = pd.read_csv(f)
                if "cuentas.csv" in names:
                    with zf.open("cuentas.csv") as f:
                        st.session_state["cuentas"] = pd.read_csv(f)
                if "saldos.csv" in names:
                    with zf.open("saldos.csv") as f:
                        st.session_state["saldos"] = pd.read_csv(f)
                if "presupuesto.csv" in names:
                    with zf.open("presupuesto.csv") as f:
                        st.session_state["presupuesto"] = pd.read_csv(f)
            st.success("Datos restaurados desde el ZIP.")

        with st.popover("...o sube los CSV sueltos"):
            tx_up = st.file_uploader("transacciones.csv", type="csv", key="tx_up")
            if tx_up is not None:
                st.session_state["transacciones"] = pd.read_csv(tx_up)
            cat_up = st.file_uploader("categorias.csv", type="csv", key="cat_up")
            if cat_up is not None:
                st.session_state["categorias"] = pd.read_csv(cat_up)
            reg_up = st.file_uploader("reglas.csv", type="csv", key="reg_up")
            if reg_up is not None:
                st.session_state["reglas"] = pd.read_csv(reg_up)
            cue_up = st.file_uploader("cuentas.csv", type="csv", key="cue_up")
            if cue_up is not None:
                st.session_state["cuentas"] = pd.read_csv(cue_up)
            sal_up = st.file_uploader("saldos.csv", type="csv", key="sal_up")
            if sal_up is not None:
                st.session_state["saldos"] = pd.read_csv(sal_up)

        if st.button("🗑️ Empezar de cero", use_container_width=True):
            for k in ["transacciones", "categorias", "reglas", "cuentas", "saldos", "presupuesto"]:
                del st.session_state[k]
            _init_state()
            st.rerun()

    st.divider()

    with st.expander("➕ Importar extracto nuevo", expanded=False):
        cuenta_sel = st.selectbox(
            "Cuenta de destino",
            list(st.session_state["cuentas"]["Cuenta"]) + ["+ Nueva cuenta..."],
        )
        if cuenta_sel == "+ Nueva cuenta...":
            cuenta_sel = st.text_input("Nombre de la nueva cuenta")

        tipo_archivo = st.radio("Tipo de archivo", ["PDF (texto)", "Imagen (OCR, ej. capturas Edenred)"], horizontal=False)
        up = st.file_uploader(
            "Extracto / captura",
            type=["pdf"] if tipo_archivo.startswith("PDF") else ["png", "jpg", "jpeg"],
            accept_multiple_files=True,
        )
        if st.button("🔍 Extraer movimientos", use_container_width=True) and up and cuenta_sel:
            # Si es una cuenta que no estaba en el catálogo (p.ej. escrita en
            # "+ Nueva cuenta..."), la damos de alta automáticamente para que
            # también aparezca en la pestaña Cuentas y en el formulario de saldos
            # de Patrimonio. El usuario puede corregir su TipoCuenta después.
            if cuenta_sel not in list(st.session_state["cuentas"]["Cuenta"]):
                nueva_cuenta = pd.DataFrame([{"Cuenta": cuenta_sel, "TipoCuenta": "Banco"}])
                st.session_state["cuentas"] = pd.concat(
                    [st.session_state["cuentas"], nueva_cuenta], ignore_index=True
                )
            piezas = []
            for f in up:
                if tipo_archivo.startswith("PDF"):
                    piezas.append(fz.parse_statement_pdf(f, cuenta_sel))
                else:
                    piezas.append(fz.parse_image_ocr(f, cuenta_sel))
            extraido = pd.concat(piezas, ignore_index=True) if piezas else pd.DataFrame()
            if extraido.empty:
                st.warning(
                    "No se detectó ningún movimiento automáticamente. Esto es habitual con "
                    "formatos de extracto no vistos antes (o imágenes sin OCR disponible). "
                    "Añade las filas a mano en la tabla de revisión de abajo."
                )
                extraido = pd.DataFrame(columns=["Fecha", "Cuenta", "Concepto", "Importe"])
                extraido.loc[0] = [date.today().isoformat(), cuenta_sel, "", 0.0]
            extraido = fz.recategorizar(
                extraido.assign(Categoria="", Origen="import"),
                st.session_state["reglas"], st.session_state["categorias"],
            )
            st.session_state["pendientes"] = extraido
            st.success(f"{len(extraido)} movimiento(s) detectado(s). Revísalos abajo antes de confirmar ⬇️")

    st.divider()

    with st.expander("💾 Descargar tu progreso", expanded=False):
        st.caption("Guarda este ZIP (en tu ordenador o Google Drive) para poder continuar el mes que viene.")
        zip_bytes = fz.to_zip_bytes({
            "transacciones": st.session_state["transacciones"],
            "categorias": st.session_state["categorias"],
            "reglas": st.session_state["reglas"],
            "cuentas": st.session_state["cuentas"],
            "saldos": st.session_state["saldos"],
            "presupuesto": st.session_state["presupuesto"],
        })
        st.download_button(
            "⬇️ Descargar todo (.zip)", data=zip_bytes,
            file_name=f"dashboard_financiero_{date.today().isoformat()}.zip",
            mime="application/zip", use_container_width=True,
        )

# ====================================================================================
# PANEL DE REVISIÓN DE MOVIMIENTOS PENDIENTES (aparece tras "Extraer movimientos")
# ====================================================================================
if st.session_state["pendientes"] is not None:
    st.subheader("📋 Revisa los movimientos antes de incorporarlos")
    st.caption(
        "Corrige fecha, concepto, importe o categoría si el parser se ha equivocado, "
        "borra filas duplicadas y añade las que falten. Nada se guarda en el histórico "
        "hasta que pulses «Confirmar»."
    )
    edited = st.data_editor(
        st.session_state["pendientes"],
        num_rows="dynamic",
        use_container_width=True,
        column_config={
            "Importe": st.column_config.NumberColumn(format="%.2f €"),
            "Categoria": st.column_config.SelectboxColumn(options=list(st.session_state["categorias"]["Categoria"])),
        },
        key="editor_pendientes",
    )
    col1, col2, col3 = st.columns([1, 1, 4])
    with col1:
        confirmar = st.button("✅ Confirmar e incorporar", type="primary")
    with col2:
        descartar = st.button("✖️ Descartar")
    if confirmar:
        nuevas = edited.dropna(subset=["Fecha", "Importe"]).copy()
        nuevas["id"] = fz.make_ids(nuevas)
        nuevas, n_dup = fz.dedupe(nuevas, st.session_state["transacciones"])
        nuevas["Tipo"] = nuevas.apply(
            lambda r: fz.tipo_de_categoria(r["Categoria"], st.session_state["categorias"], r["Importe"]), axis=1
        )
        st.session_state["transacciones"] = pd.concat(
            [st.session_state["transacciones"], nuevas], ignore_index=True
        )
        st.session_state["pendientes"] = None
        msg = f"{len(nuevas)} movimiento(s) incorporado(s)."
        if n_dup:
            msg += f" ({n_dup} descartado(s) por estar ya en el histórico)."
        st.success(msg)
        st.rerun()
    if descartar:
        st.session_state["pendientes"] = None
        st.rerun()
    st.divider()

# ====================================================================================
# CUERPO: 5 PESTAÑAS
# ====================================================================================
tx = st.session_state["transacciones"]
if not tx.empty:
    tx = fz.recategorizar(tx, st.session_state["reglas"], st.session_state["categorias"])
    st.session_state["transacciones"] = tx

tab_patrimonio, tab_mensual, tab_anual, tab_movs, tab_config = st.tabs(
    ["🏦 Patrimonio", "📅 Análisis mensual", "📈 Evolución anual", "📋 Movimientos", "⚙️ Categorías y cuentas"]
)

# ---------------------------------------------------------------- Patrimonio -------
with tab_patrimonio:
    st.header("Patrimonio")
    saldos = st.session_state["saldos"]

    with st.expander("➕ Registrar saldos de cuentas a fecha de hoy"):
        st.caption("Un dato mensual por cuenta basta para ver la evolución del patrimonio.")
        cuentas_df = st.session_state["cuentas"]
        with st.form("form_saldos"):
            fecha_saldo = st.date_input("Fecha", value=date.today())
            valores = {}
            for _, row in cuentas_df.iterrows():
                valores[row["Cuenta"]] = st.number_input(
                    f"{row['Cuenta']} ({row['TipoCuenta']})", value=0.0, step=10.0, format="%.2f"
                )
            if st.form_submit_button("Guardar saldos"):
                nuevas_filas = pd.DataFrame([
                    {"Fecha": fecha_saldo.isoformat(), "Cuenta": c, "TipoCuenta": cuentas_df.loc[cuentas_df["Cuenta"] == c, "TipoCuenta"].iloc[0], "Saldo": v, "Notas": ""}
                    for c, v in valores.items()
                ])
                st.session_state["saldos"] = pd.concat([saldos, nuevas_filas], ignore_index=True)
                st.success("Saldos guardados.")
                st.rerun()

    if saldos.empty:
        st.info("Todavía no has registrado ningún saldo. Usa el formulario de arriba para empezar.")
    else:
        ultima_fecha = saldos["Fecha"].max()
        actuales = saldos[saldos["Fecha"] == ultima_fecha]
        activos = actuales.loc[actuales["TipoCuenta"] != "Tarjeta de credito", "Saldo"].sum()
        deuda = actuales.loc[actuales["TipoCuenta"] == "Tarjeta de credito", "Saldo"].sum()
        neto = activos - deuda

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Patrimonio neto", f"{neto:,.2f} €".replace(",", "."))
        c2.metric("Activos", f"{activos:,.2f} €".replace(",", "."))
        c3.metric("Deuda", f"{deuda:,.2f} €".replace(",", "."))
        c4.metric("Último dato", ultima_fecha)

        col_a, col_b = st.columns(2)
        col_a.plotly_chart(fz.fig_donut_patrimonio(actuales), use_container_width=True)
        col_b.plotly_chart(fz.fig_line_patrimonio(saldos), use_container_width=True)

        with st.expander("Detalle por cuenta"):
            st.dataframe(actuales[["Cuenta", "TipoCuenta", "Saldo"]], use_container_width=True, hide_index=True)

# ------------------------------------------------------------ Análisis mensual -----
with tab_mensual:
    st.header("Análisis mensual")
    if tx.empty:
        st.info("Importa algún extracto para ver este dashboard.")
    else:
        fechas = pd.to_datetime(tx["Fecha"])
        anios_disp = sorted(fechas.dt.year.unique(), reverse=True)
        colf1, colf2 = st.columns(2)
        anio_sel = colf1.selectbox("Año", anios_disp, key="anio_mensual")
        mes_sel_nombre = colf2.selectbox("Mes", MESES, index=date.today().month - 1, key="mes_mensual")
        mes_sel = MESES.index(mes_sel_nombre) + 1

        tx_mes = fz.filtrar_mes(tx, anio_sel, mes_sel)
        k = fz.kpis_mes(tx_mes)
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Ingresos del mes", f"{k['ingresos']:,.2f} €".replace(",", "."))
        c2.metric("Gastos del mes", f"{k['gastos']:,.2f} €".replace(",", "."))
        c3.metric("Ahorro del mes", f"{k['ahorro']:,.2f} €".replace(",", "."))
        c4.metric("% ahorro sobre ingresos", f"{k['pct_ahorro']*100:,.1f} %".replace(",", "."))

        gasto_cat = fz.gasto_por_categoria(tx_mes)
        pres_mes = st.session_state["presupuesto"]
        pres_mes = pres_mes[(pres_mes["Anio"] == anio_sel) & (pres_mes["Mes"] == mes_sel)] if not pres_mes.empty else pres_mes

        col1, col2 = st.columns(2)
        col1.plotly_chart(fz.fig_donut_categorias(gasto_cat), use_container_width=True)
        col2.plotly_chart(fz.fig_bar_presupuesto(gasto_cat, pres_mes if not pres_mes.empty else pd.DataFrame(columns=["Categoria", "Presupuesto"])), use_container_width=True)

        col3, col4 = st.columns(2)
        col3.plotly_chart(fz.fig_bar_ingresos_gastos_ahorro(k), use_container_width=True)
        col4.plotly_chart(fz.fig_bar_top5(gasto_cat), use_container_width=True)

        st.plotly_chart(fz.fig_line_diario(tx_mes, anio_sel, mes_sel), use_container_width=True)

# --------------------------------------------------------------- Evolución anual ---
with tab_anual:
    st.header("Evolución anual")
    if tx.empty:
        st.info("Importa algún extracto para ver este dashboard.")
    else:
        fechas = pd.to_datetime(tx["Fecha"])
        anios_disp = sorted(fechas.dt.year.unique(), reverse=True)
        anio_sel2 = st.selectbox("Año", anios_disp, key="anio_anual")
        tabla = fz.tabla_anual(tx, anio_sel2)

        c1, c2, c3 = st.columns(3)
        c1.metric("Ingresos anuales", f"{tabla['Ingresos'].sum():,.2f} €".replace(",", "."))
        c2.metric("Gastos anuales", f"{tabla['Gastos'].sum():,.2f} €".replace(",", "."))
        c3.metric("Ahorro anual", f"{tabla['Ahorro'].sum():,.2f} €".replace(",", "."))

        st.plotly_chart(fz.fig_bar_anual(tabla), use_container_width=True)
        st.plotly_chart(fz.fig_line_anual(tabla), use_container_width=True)
        st.dataframe(tabla, use_container_width=True, hide_index=True)

# ------------------------------------------------------------------- Movimientos ---
with tab_movs:
    st.header("Movimientos")
    st.caption("Edita directamente cualquier movimiento (por ejemplo, para corregir una categoría). Los cambios se guardan solos, en cuanto sales de la celda — no hace falta ningún botón.")
    edited_tx = st.data_editor(
        tx.sort_values("Fecha", ascending=False) if not tx.empty else tx,
        num_rows="dynamic",
        use_container_width=True,
        height=500,
        column_config={
            "Importe": st.column_config.NumberColumn(format="%.2f €"),
            "Categoria": st.column_config.SelectboxColumn(options=list(st.session_state["categorias"]["Categoria"])),
            "Tipo": st.column_config.SelectboxColumn(options=["Ingreso", "Gasto", "Transferencia"]),
        },
        key="editor_movimientos",
    )
    # Igual que en las tablas de Categorías/Reglas/Cuentas/Presupuesto: se reescribe
    # el estado en cada ejecución con lo que devuelva el editor, sin esperar a que
    # se pulse ningún botón — así una corrección de categoría se refleja de
    # inmediato en los dashboards (y queda incluida al descargar el ZIP).
    if "id" in edited_tx.columns and len(edited_tx):
        missing = edited_tx["id"].isna() | (edited_tx["id"].astype(str).str.strip() == "")
        if missing.any():
            edited_tx.loc[missing, "id"] = fz.make_ids(edited_tx.loc[missing])
    st.session_state["transacciones"] = edited_tx

# --------------------------------------------------------- Categorías y cuentas ----
with tab_config:
    st.header("Categorías, reglas de auto-categorización, cuentas y presupuesto")

    st.subheader("Categorías")
    st.session_state["categorias"] = st.data_editor(
        st.session_state["categorias"], num_rows="dynamic", use_container_width=True,
        column_config={"Tipo": st.column_config.SelectboxColumn(options=["Ingreso", "Gasto", "Transferencia"])},
        key="editor_categorias",
    )

    st.subheader("Reglas de categorización automática")
    st.caption(
        "Se aplican en orden de Prioridad (la primera cuyo patrón encaje con el concepto, gana). "
        "El patrón es una expresión regular sencilla; por ejemplo `mercadona|carrefour` categoriza "
        "cualquier concepto que contenga una de esas dos palabras."
    )
    st.session_state["reglas"] = st.data_editor(
        st.session_state["reglas"].sort_values("Prioridad"), num_rows="dynamic", use_container_width=True,
        column_config={
            "Categoria": st.column_config.SelectboxColumn(options=list(st.session_state["categorias"]["Categoria"])),
        },
        key="editor_reglas",
    )

    st.subheader("Cuentas")
    st.session_state["cuentas"] = st.data_editor(
        st.session_state["cuentas"], num_rows="dynamic", use_container_width=True,
        column_config={"TipoCuenta": st.column_config.SelectboxColumn(options=["Banco", "Efectivo", "Inversion", "Tarjeta de credito"])},
        key="editor_cuentas",
    )

    st.subheader("Presupuesto mensual por categoría")
    st.session_state["presupuesto"] = st.data_editor(
        st.session_state["presupuesto"], num_rows="dynamic", use_container_width=True,
        column_config={
            "Categoria": st.column_config.SelectboxColumn(options=list(st.session_state["categorias"]["Categoria"])),
            "Mes": st.column_config.NumberColumn(min_value=1, max_value=12, step=1),
        },
        key="editor_presupuesto",
    )
