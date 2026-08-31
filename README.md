# Dashboard Financiero (Streamlit)

App de Streamlit que reemplaza al Excel: sube tus extractos bancarios cada mes,
revisa los movimientos detectados y consulta 3 dashboards (Patrimonio, Análisis
mensual, Evolución anual) con gráficos interactivos.

## Archivos del proyecto

- `app.py` — interfaz (barra lateral de importación/datos + las 5 pestañas).
- `finanzas.py` — toda la lógica: categorización, parseo de PDF/imágenes, cálculo
  de KPIs y construcción de los gráficos. No depende de Streamlit.
- `requirements.txt` — dependencias Python.
- `packages.txt` — dependencia de sistema (`tesseract-ocr`) para el OCR de imágenes.
- `.streamlit/config.toml` — tema de color de la app.

## 1. Desplegar en Streamlit Community Cloud

1. Crea un repositorio en GitHub (puede ser privado) y sube estos archivos tal
   cual (misma estructura de carpetas, incluida `.streamlit/config.toml`).
2. Entra en [share.streamlit.io](https://share.streamlit.io) con tu cuenta de
   GitHub y pulsa **"New app"**.
3. Selecciona el repositorio, la rama y `app.py` como archivo principal → **Deploy**.
4. La primera vez tardará 1-2 minutos en instalar dependencias (incluido
   `tesseract-ocr` vía `packages.txt`). A partir de ahí tienes una URL fija.

**Privacidad de la app:** por defecto, cualquiera con el enlace puede abrir la
app y ver tus datos si los subes durante esa sesión. Si te importa, en el panel
de la app en Streamlit Cloud activa **"This app requires viewers to log in"**
y añade solo tu email a la lista de acceso. Alternativamente, mantén el
repositorio privado (no afecta a si la app en sí es pública) y no compartas la
URL con nadie.

## 2. Cómo funciona la persistencia (léelo antes de usarla)

Streamlit Community Cloud **no tiene disco persistente**: cada vez que la app
se reinicia (duerme por inactividad, hay un redeploy, etc.) pierde todo lo que
tuviera en memoria. Por eso el histórico de movimientos **no vive en el
servidor**, vive en un archivo que tú guardas:

- Al terminar una sesión, usa **"💾 Descargar tu progreso"** en la barra
  lateral → te descarga un `.zip` con `transacciones.csv`, `categorias.csv`,
  `reglas.csv`, `cuentas.csv`, `saldos.csv` y `presupuesto.csv`.
- Guarda ese `.zip` en tu ordenador o en una carpeta de Google Drive/Dropbox.
- La próxima vez que abras la app, súbelo en **"📂 Tus datos" → "Restaurar
  desde ZIP"** antes de importar el extracto nuevo del mes.

Es el mismo patrón que "guardar el Excel y volver a abrirlo el mes que viene",
solo que el archivo es un `.zip` de CSV en vez de un `.xlsx`.

## 3. Flujo de trabajo mensual

1. Abre la app → restaura tu `.zip` del mes anterior.
2. En **"➕ Importar extracto nuevo"**: elige la cuenta, sube el PDF (o las
   capturas de Edenred como imagen) y pulsa **"Extraer movimientos"**.
3. Revisa la tabla de movimientos detectados — corrige lo que el parser no
   haya interpretado bien (fechas, importes, categoría) y añade a mano lo que
   falte. Pulsa **"Confirmar e incorporar"**.
4. Repite el paso 2-3 para cada cuenta (ING, Trade Republic, Edenred...).
5. Si quieres ver la evolución del patrimonio, registra los saldos actuales de
   tus cuentas en la pestaña **"🏦 Patrimonio"**.
6. Consulta los dashboards.
7. Antes de cerrar, descarga el `.zip` actualizado y guárdalo.

## 4. Sobre el parseo automático de PDF

`finanzas.py` incluye un parser genérico (`parse_statement_text`) que busca
líneas con fecha + importe en formato español. Funciona razonablemente con
extractos tabulares típicos, pero **ningún parser genérico es 100% fiable**
con el PDF concreto de tu banco la primera vez — por eso siempre hay un paso
de revisión manual antes de confirmar la importación. Si ves que se equivoca
sistemáticamente de la misma forma con tus extractos, dime cómo falla y
ajusto las expresiones regulares en `parse_statement_text` para tu formato
exacto de ING / Trade Republic.

Las imágenes (Edenred) usan OCR (`pytesseract` + `tesseract-ocr`, instalado
vía `packages.txt`). El OCR sobre capturas de móvil es más frágil que el texto
de un PDF — si falla, la tabla de revisión aparece vacía para que añadas las
filas a mano (normalmente son pocos tickets al mes).

## 5. Categorización automática

Las reglas viven en la pestaña **"⚙️ Categorías y cuentas"** como una tabla
editable: un patrón (expresión regular) y la categoría a la que apunta,
evaluadas en orden de prioridad. Vienen con un set inicial genérico (nómina,
supermercados, transporte, suscripciones...); edítalas o añade filas nuevas
según tus propios comercios habituales — se aplican automáticamente en la
próxima importación.

A diferencia del Excel, aquí el gráfico de donut de "Gasto por categoría"
simplemente no dibuja las categorías sin gasto ese mes (se filtran antes de
pasarlas a Plotly) — no hace falta ningún truco de formato de número para
evitar que aparezcan porciones al 0%.

## 6. Ejecutarla en local (antes de desplegar, o en vez de desplegar)

```bash
pip install -r requirements.txt
streamlit run app.py
```

Se abre en `http://localhost:8501`. Localmente sí puedes hacer que
`transacciones.csv` etc. se guarden en disco automáticamente si lo prefieres
a la exportación en ZIP — dímelo si quieres que lo adapte para ese caso.
