"""
═══════════════════════════════════════════════════════════════════════════════
DASHBOARD DE RESERVAS MATEMÁTICAS DE VIDA INDIVIDUAL
───────────────────────────────────────────────────────────────────────────────
Motor: Funciones de conmutación GAUSS + Aproximación de Woolhouse (2° orden)
Valida:  ₀V = 0  ·  ₙV = C/0  ·  V_pros ≡ V_retro  ∀ t ∈ [0, n]
═══════════════════════════════════════════════════════════════════════════════
"""

import pandas as pd
import numpy as np
import streamlit as st
import plotly.graph_objects as go
from pathlib import Path

# ══════════════════════════════════════════════════════════════════════════════
# 0  CONFIGURACIÓN DE PÁGINA
# ══════════════════════════════════════════════════════════════════════════════
st.set_page_config(
    page_title="Reservas Matemáticas · Dashboard",
    page_icon="📐",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown("""
<style>
[data-testid="stMetricValue"]  { font-size: 1.05rem; font-weight: 700; }
[data-testid="stMetricLabel"]  { font-size: 0.72rem; color: #9ca3af; }
[data-testid="stMetricDelta"]  { font-size: 0.72rem; }
div[data-testid="column"] > div { gap: 0.25rem; }
</style>
""", unsafe_allow_html=True)

# ══════════════════════════════════════════════════════════════════════════════
# 1  CARGA Y CONSTRUCCIÓN DE CONMUTATIVOS
# ══════════════════════════════════════════════════════════════════════════════

def _detectar_excel() -> str:
    folder = Path(__file__).parent
    for p in (folder / "data" / "tabla_mortalidad.xlsx",
              folder / "tabla_mortalidad.xlsx"):
        if p.exists():
            return str(p)
    for ext in ("xlsx", "xlsm", "xls"):
        hit = list(folder.rglob(f"*actuarial*.{ext}"))
        if hit:
            return str(hit[0])
    return str(folder / "tabla_mortalidad.xlsx")


@st.cache_data
def cargar_base(path: str) -> dict[str, pd.DataFrame]:
    result: dict[str, pd.DataFrame] = {}
    for hoja in ("Hombres", "Mujeres"):
        df = pd.read_excel(path, sheet_name=hoja)
        df.columns = [c.strip() for c in df.columns]
        missing = {"x", "q(x)", "l(x)", "d(x)"} - set(df.columns)
        if missing:
            raise ValueError(f"Hoja '{hoja}': faltan columnas {missing}.")
        df["x"]    = df["x"].astype(int)
        for col in ("q(x)", "l(x)", "d(x)"):
            df[col] = df[col].astype(float)
        result[hoja] = df
    return result


def construir_conmutados(df_base: pd.DataFrame, i: float) -> pd.DataFrame:
    """
    D_x = v^x · l_x          N_x = Σ_{k≥x} D_k
    C_x = v^{x+1} · d_x      M_x = Σ_{k≥x} C_k
    """
    df  = df_base.sort_values("x").copy().set_index("x")
    v   = 1.0 / (1.0 + i)
    xs  = df.index.to_numpy(dtype=int)
    lx  = df["l(x)"].to_numpy(dtype=float)
    dx  = df["d(x)"].to_numpy(dtype=float)
    Dx  = (v ** xs) * lx
    Cx  = (v ** (xs + 1)) * dx
    df["Dx"] = Dx
    df["Cx"] = Cx
    df["Nx"] = np.cumsum(Dx[::-1])[::-1]
    df["Mx"] = np.cumsum(Cx[::-1])[::-1]
    return df


# ── Accesores escalares ───────────────────────────────────────────────────────
def _g(t: pd.DataFrame, age: int, col: str) -> float:
    if age not in t.index:
        raise KeyError(f"Edad {age} fuera de rango (0–{t.index.max()}).")
    return float(t.loc[age, col])

D  = lambda t, x: _g(t, x, "Dx")
N  = lambda t, x: _g(t, x, "Nx")
M  = lambda t, x: _g(t, x, "Mx")
lx = lambda t, x: _g(t, x, "l(x)")


# ══════════════════════════════════════════════════════════════════════════════
# 2  FUNCIONES ACTUARIALES (por unidad, C = 1)
# ══════════════════════════════════════════════════════════════════════════════

def nEx(t, x, n):          return D(t, x+n) / D(t, x)

# Seguros
def A_vida_entera(t, x):       return M(t, x) / D(t, x)
def A_temporal(t, x, n):       return (M(t, x) - M(t, x+n)) / D(t, x)
def A_dotal_puro(t, x, n):     return D(t, x+n) / D(t, x)
def A_dotal_mixto(t, x, n):    return (M(t, x) - M(t, x+n) + D(t, x+n)) / D(t, x)

# Anualidades anticipadas (ä)
def a_temporal(t, x, n):       return (N(t, x) - N(t, x+n)) / D(t, x)
def a_vitalicia(t, x):         return N(t, x) / D(t, x)

# Ajuste de Woolhouse de 2° orden
_adj = lambda k: (k - 1) / (2 * k)

def a_temporal_k(t, x, n, k):
    return a_temporal(t, x, n) - _adj(k) * (1 - nEx(t, x, n))

def a_vitalicia_k(t, x, k):
    return a_vitalicia(t, x) - _adj(k)


# ══════════════════════════════════════════════════════════════════════════════
# 3  MOTOR DE RESERVAS — generar_cuadro_reservas()
# ══════════════════════════════════════════════════════════════════════════════

_PRODS = {
    "MUE_TEMPORAL":    "Temporal · A¹ₓ:n̄|",
    "SOB_DOTAL_MIXTO": "Dotal Mixto (Endowment) · Aₓ:n̄|",
    "MUE_VIDA_ENTERA": "Vida Entera · Aₓ",
    "SOB_DOTAL":       "Dotal Puro · ₙEₓ",
}


def generar_cuadro_reservas(
    tabla:   pd.DataFrame,
    x: int, n: int, m: int, k: int,
    PPA:     float,    # prima pura anual en $ (incluye capital)
    PPA_k:   float,    # prima pura anual equiv. fraccionada en $ (incluye capital)
    capital: float,
    producto: str,
) -> pd.DataFrame:
    """
    Proyecta _tV para t = 0, 1, …, n  (ó ω-x para Vida Entera).

    Internamente convierte PPA y PPA_k a valores por-unidad (÷ capital)
    para mantener consistencia dimensional con VP_Ben (que es por-unidad).

    Columnas del resultado:
      t · x+t · VP_Ben · VP_Pri Anual · VP_Pri Fracc ·
      V_PU · V_PNA · V_PNF · V_Retro · Δ(PNA−Retro)

    Validaciones integradas (todas deben dar ≈ 0):
      • ₀V = 0           (Principio de Equivalencia)
      • ₙV = C  o  0     (condición terminal)
      • Δ(PNA−Retro) = 0 (prospectiva ≡ retrospectiva)
    """
    omega = int(tabla.index.max())
    max_t = (omega - x - 1) if producto == "MUE_VIDA_ENTERA" else n

    t_arr = np.arange(0, max_t + 1, dtype=int)
    ages  = x + t_arr
    valid = ages <= omega
    t_arr, ages = t_arr[valid], ages[valid]

    # ── Vectores de conmutativos ──────────────────────────────────────────────
    Dxt = tabla.loc[ages, "Dx"].values.astype(float)
    Nxt = tabla.loc[ages, "Nx"].values.astype(float)
    Mxt = tabla.loc[ages, "Mx"].values.astype(float)

    # Constantes escalares en los límites n y m
    x_n  = min(x + n, omega)
    x_m  = min(x + m, omega)
    Dxn  = float(tabla.loc[x_n, "Dx"]) if x_n in tabla.index else 0.0
    Mxn  = float(tabla.loc[x_n, "Mx"]) if x_n in tabla.index else 0.0
    Nxm  = float(tabla.loc[x_m, "Nx"]) if x_m in tabla.index else 0.0
    Dxm  = float(tabla.loc[x_m, "Dx"]) if x_m in tabla.index else 1e-15
    Mx0  = float(tabla.loc[x,   "Mx"])
    Nx0  = float(tabla.loc[x,   "Nx"])

    # Primas por-unidad (÷ capital)
    ppa_u  = PPA   / capital
    ppa_ku = PPA_k / capital

    # ── Paso A: VP_Ben (por unidad de capital, prospectivo) ───────────────────
    if   producto == "MUE_VIDA_ENTERA": VP_Ben = Mxt / Dxt
    elif producto == "MUE_TEMPORAL":    VP_Ben = (Mxt - Mxn) / Dxt
    elif producto == "SOB_DOTAL":       VP_Ben = Dxn / Dxt
    elif producto == "SOB_DOTAL_MIXTO": VP_Ben = (Mxt - Mxn + Dxn) / Dxt
    else:                               VP_Ben = np.zeros(len(t_arr))

    # ── Paso B: VP_Pri (por unidad de capital, prospectivo) ───────────────────
    # t < m → existen primas futuras; t ≥ m → ya pagó todo
    mask = t_arr < m

    # ä_{x+t : m-t|} = (N(x+t) - N(x+m)) / D(x+t)   [factor de anualidad restante]
    ann = np.where(mask, (Nxt - Nxm) / Dxt, 0.0)

    # Ajuste de Woolhouse: (k-1)/(2k) · (1 − D(x+m)/D(x+t))
    woo = np.where(mask, _adj(k) * (1.0 - Dxm / Dxt), 0.0)

    VP_Pri_A = np.where(mask, ppa_u  * ann,          0.0)  # por unidad, prima anual
    VP_Pri_F = np.where(mask, ppa_ku * (ann - woo),  0.0)  # por unidad, prima fracc.

    # ── Paso C: Tres curvas de reserva prospectiva ────────────────────────────
    V_PU  = VP_Ben * capital                              # Sin primas futuras
    V_PNA = (VP_Ben - VP_Pri_A) * capital                 # Prima nivelada anual
    V_PNF = (VP_Ben - VP_Pri_F) * capital                 # Prima nivelada fraccionada

    # ── Paso D: Reserva retrospectiva (para auditoría) ────────────────────────
    # Primas acumuladas: ppa_u · ä_{x : min(t,m)|} acumulado a x+t
    # = ppa_u · (N(x) − N(x+min(t,m))) / D(x+t)
    cap_ages = np.clip(x + np.minimum(t_arr, m), 0, omega)
    Nx_cap   = np.array([float(tabla.at[int(a), "Nx"]) for a in cap_ages])
    Primas_acum = ppa_u * (Nx0 - Nx_cap) / Dxt          # por unidad

    # Siniestros acumulados: (M(x) − M(x+t)) / D(x+t)  — solo en seguros de muerte
    if producto in ("MUE_VIDA_ENTERA", "MUE_TEMPORAL", "SOB_DOTAL_MIXTO"):
        Sin_pag = (Mx0 - Mxt) / Dxt
    else:  # SOB_DOTAL: no hay beneficio por muerte
        Sin_pag = np.zeros(len(t_arr))

    V_Retro = (Primas_acum - Sin_pag) * capital
    Delta   = V_PNA - V_Retro

    return pd.DataFrame({
        "t":             t_arr,
        "x+t":           ages,
        "VP_Ben":        VP_Ben,
        "VP_Pri Anual":  VP_Pri_A,
        "VP_Pri Fracc":  VP_Pri_F,
        "V_PU":          V_PU,
        "V_PNA":         V_PNA,
        "V_PNF":         V_PNF,
        "V_Retro":       V_Retro,
        "Δ(PNA−Retro)":  Delta,
    })


# ══════════════════════════════════════════════════════════════════════════════
# 4  SIDEBAR — Parámetros
# ══════════════════════════════════════════════════════════════════════════════
ARCHIVO_DEFAULT = _detectar_excel()

with st.sidebar:
    st.header("⚙️ Parámetros de la Póliza")
    archivo = st.text_input("Ruta del Excel", value=ARCHIVO_DEFAULT)

try:
    base_data = cargar_base(archivo)
except Exception as e:
    st.error(f"No se pudo cargar la tabla: {e}")
    st.stop()

with st.sidebar:
    sexo  = st.selectbox("Sexo", ["Hombres", "Mujeres"])
    i_pct = st.number_input("Tasa técnica i (%)", 0.01, 100.0, 5.0, 0.25)
    i     = i_pct / 100.0

tabla = construir_conmutados(base_data[sexo], i=i)
omega = int(tabla.index.max())

with st.sidebar:
    st.caption(f"✦ {sexo}  ·  Edades 0–{omega}  ·  i = {i_pct:.2f}%")
    st.markdown("---")

    producto = st.selectbox(
        "Producto",
        list(_PRODS.keys()),
        format_func=lambda k: _PRODS[k],
    )

    st.markdown("---")
    x       = int(st.number_input("Edad de emisión (x)", 0, omega - 2, min(35, omega - 2), 1))
    capital = st.number_input("Capital asegurado (C)", 1.0, value=100_000.0, step=1_000.0)

    # Plazo de cobertura n
    requiere_n = (producto != "MUE_VIDA_ENTERA")
    if requiere_n:
        n_max = omega - x
        n = int(st.number_input("Plazo de cobertura n (años)", 1, n_max, min(20, n_max), 1))
    else:
        n = omega - x
        st.info(f"Cobertura vitalicia: n = ω − x = {n} años")

    # Plazo de pago m (≤ n)
    m_max = n
    m = int(st.number_input(
        "Plazo de pago m (años)", 1, m_max, min(20, m_max), 1,
        help="m ≤ n. Si m = n: pago nivelado continuo.",
    ))
    m = min(m, n)

    # Frecuencia k
    K_MAP = {1: "1 · Anual", 2: "2 · Semestral", 4: "4 · Trimestral",
             12: "12 · Mensual", 52: "52 · Semanal"}
    k = st.selectbox(
        "Frecuencia de pago k (pagos/año)",
        list(K_MAP.keys()), index=3,
        format_func=lambda v: K_MAP[v],
    )

    st.markdown("---")
    calcular = st.button("📊 Calcular Reservas", type="primary", use_container_width=True)


# ══════════════════════════════════════════════════════════════════════════════
# 5  CABECERA PRINCIPAL
# ══════════════════════════════════════════════════════════════════════════════
st.title("📐 Dashboard de Reservas Matemáticas")
st.caption(
    f"Motor: Conmutativos GAUSS · Woolhouse 2° orden · {sexo} · i = {i_pct:.2f}% "
    f"· Convención: Cₓ = v^(x+1) · dₓ"
)

# ── Pantalla de bienvenida (antes del primer cómputo) ─────────────────────────
if not calcular:
    st.markdown("---")
    w1, w2 = st.columns(2)

    with w1:
        st.subheader("🎯 Curvas que proyecta este dashboard")
        st.markdown("""
| Curva | Modalidad de prima | Comportamiento esperado |
|:---|:---|:---|
| 🟠 **V_PU** | Prima Única | Inicia en PPU, decrece suavemente |
| 🟦 **V_PNA** | Nivelada Anual | Parte de 0, crece hasta convergencia |
| 🔷 **V_PNF** | Nivelada Fraccionada (Woolhouse) | Paralela a V_PNA |
| 🟡 **V_Retro** | Retrospectiva (auditoría) | Coincide exactamente con V_PNA |

V_PU y V_PNA convergen en t = m (fin del período de primas) y permanecen
iguales hasta el vencimiento, confirmando la consistencia del modelo.
""")

    with w2:
        st.subheader("📐 Condiciones de límite verificadas")
        st.latex(r"{}_{0}V = 0 \quad \text{(Principio de Equivalencia)}")
        st.latex(r"{}_{n}V = C \quad \text{(Dotal / Endowment: al vencimiento)}")
        st.latex(r"{}_{n}V = 0 \quad \text{(Temporal: al vencimiento)}")
        st.latex(r"{}_{t}V^{\text{pros}} = {}_{t}V^{\text{retro}} \quad \forall\, t \in [0, n]")

    st.info("👈 Configure los parámetros en el panel lateral y presione **Calcular Reservas**.")

    with st.expander("🔎 Vista previa de conmutativos"):
        st.dataframe(
            tabla[["q(x)", "l(x)", "d(x)", "Dx", "Cx", "Nx", "Mx"]].head(25),
            use_container_width=True,
        )
    st.stop()


# ══════════════════════════════════════════════════════════════════════════════
# 6  CÓMPUTO PRINCIPAL
# ══════════════════════════════════════════════════════════════════════════════
try:
    # ── Validaciones de rango ─────────────────────────────────────────────────
    if x + m > omega:
        st.error(f"x + m = {x+m} > ω = {omega}. Reduzca m en el panel lateral.")
        st.stop()
    if requiere_n and x + n > omega:
        st.error(f"x + n = {x+n} > ω = {omega}. Reduzca n en el panel lateral.")
        st.stop()

    # ── Valor actuarial por unidad (VPA, C = 1) ───────────────────────────────
    if   producto == "MUE_VIDA_ENTERA": val_u = A_vida_entera(tabla, x)
    elif producto == "MUE_TEMPORAL":    val_u = A_temporal(tabla, x, n)
    elif producto == "SOB_DOTAL":       val_u = A_dotal_puro(tabla, x, n)
    elif producto == "SOB_DOTAL_MIXTO": val_u = A_dotal_mixto(tabla, x, n)

    PPU = val_u * capital   # Prima Pura Única ($)

    # ── Anualidades para el período de primas ─────────────────────────────────
    if x + m >= omega:                          # caso vitalicio (límite máximo)
        a_an = a_vitalicia(tabla, x)
        a_fr = a_vitalicia_k(tabla, x, k)
    else:                                       # temporal (caso usual)
        a_an = a_temporal(tabla, x, m)
        a_fr = a_temporal_k(tabla, x, m, k)

    if a_an <= 0 or a_fr <= 0:
        raise ValueError("Anualidad de primas ≤ 0. Verifique los parámetros.")

    PPA   = PPU / a_an   # Prima Pura Anual ($)
    PPA_k = PPU / a_fr   # Prima Pura Anualizada Fraccionada ($)

    # ── Generar cuadro de reservas ────────────────────────────────────────────
    df = generar_cuadro_reservas(
        tabla=tabla, x=x, n=n, m=m, k=k,
        PPA=PPA, PPA_k=PPA_k,
        capital=capital, producto=producto,
    )

    nombre_prod = _PRODS[producto]

    # ════════════════════════════════════════════════════════════════════════════
    # 7  KPIs — Cuatro tarjetas de métricas clave
    # ════════════════════════════════════════════════════════════════════════════
    st.subheader(f"🔖 {nombre_prod}")
    st.markdown(
        f"**Parámetros:** x = {x} · n = {n} · m = {m} · k = {k} · "
        f"i = {i_pct:.2f}% · {sexo}"
    )
    st.markdown("---")

    k1, k2, k3, k4 = st.columns(4)

    k1.metric(
        label="💰 Capital Asegurado (C)",
        value=f"${capital:,.2f}",
    )
    k2.metric(
        label="⚡ Prima Única (PPU)",
        value=f"${PPU:,.4f}",
        delta=f"= {val_u * 100:.4f}% de C   ·   VPA = {val_u:.8f}",
        delta_color="off",
    )
    k3.metric(
        label="📅 Prima Anual Nivelada (PPA)",
        value=f"${PPA:,.4f}",
        delta=f"ä_x:m̄| = {a_an:.8f}",
        delta_color="off",
    )
    k4.metric(
        label=f"🗓️ Prima Fracc. Anualizada (k = {k})",
        value=f"${PPA_k:,.4f}",
        delta=f"${PPA_k / k:,.4f} / pago   ·   ä^({k}) = {a_fr:.8f}",
        delta_color="off",
    )

    st.markdown("---")

    # ════════════════════════════════════════════════════════════════════════════
    # 8  GRÁFICO PLOTLY — Evolución comparativa de reservas
    # ════════════════════════════════════════════════════════════════════════════
    st.subheader("📈 Evolución Comparativa de Reservas Matemáticas")

    COL = {
        "PU":    "#FF6B35",   # naranja
        "PNA":   "#2EC4B6",   # teal
        "PNF":   "#A8DADC",   # azul pálido
        "Retro": "#FFD166",   # amarillo
    }

    fig = go.Figure()

    fig.add_trace(go.Scatter(
        x=df["t"], y=df["V_PU"],
        name="V_PU · Prima Única",
        line=dict(color=COL["PU"], width=2.8),
        mode="lines",
        hovertemplate="<b>V_PU</b>  t=%{x}<br><b>$%{y:,.2f}</b><extra></extra>",
    ))

    fig.add_trace(go.Scatter(
        x=df["t"], y=df["V_PNA"],
        name="V_PNA · Prima Anual",
        line=dict(color=COL["PNA"], width=2.8),
        mode="lines",
        hovertemplate="<b>V_PNA</b>  t=%{x}<br><b>$%{y:,.2f}</b><extra></extra>",
    ))

    fig.add_trace(go.Scatter(
        x=df["t"], y=df["V_PNF"],
        name=f"V_PNF · Prima Fracc. k={k}",
        line=dict(color=COL["PNF"], width=2.0, dash="dash"),
        mode="lines",
        hovertemplate="<b>V_PNF</b>  t=%{x}<br><b>$%{y:,.2f}</b><extra></extra>",
    ))

    fig.add_trace(go.Scatter(
        x=df["t"], y=df["V_Retro"],
        name="V_Retro · Retrospectiva (validación)",
        line=dict(color=COL["Retro"], width=1.5, dash="dot"),
        mode="lines",
        hovertemplate="<b>V_Retro</b>  t=%{x}<br><b>$%{y:,.2f}</b><extra></extra>",
        visible="legendonly",   # oculta por defecto; se activa desde la leyenda
    ))

    # ── Anotaciones estructurales ─────────────────────────────────────────────
    t_max_chart = int(df["t"].max())

    # Línea vertical en t = m (fin del período de primas niveladas)
    if m < t_max_chart:
        fig.add_vline(
            x=m,
            line_dash="dot",
            line_color="rgba(255,255,255,0.28)",
            annotation_text=f"  t = m = {m}  (fin de primas niveladas)",
            annotation_font=dict(color="rgba(200,200,200,0.65)", size=11),
            annotation_position="top left",
        )

    # Línea horizontal en C (sólo para dotales)
    if producto in ("SOB_DOTAL_MIXTO", "SOB_DOTAL"):
        fig.add_hline(
            y=capital,
            line_dash="dot",
            line_color="rgba(255,255,255,0.22)",
            annotation_text=f"  C = ${capital:,.0f}",
            annotation_font=dict(color="rgba(200,200,200,0.55)", size=11),
            annotation_position="top left",
        )

    fig.update_layout(
        template="plotly_dark",
        title=dict(
            text=f"_tV  ·  {nombre_prod}  ·  x={x}, n={n}, m={m}, k={k}, i={i_pct:.2f}%",
            font=dict(size=13, color="white"),
        ),
        xaxis=dict(
            title="Duración de la póliza  t  (años)",
            showgrid=True,
            gridcolor="rgba(255,255,255,0.06)",
            tickmode="linear",
            dtick=max(1, t_max_chart // 15),
        ),
        yaxis=dict(
            title="Reserva matemática  ($)",
            showgrid=True,
            gridcolor="rgba(255,255,255,0.06)",
            tickprefix="$",
            tickformat=",.0f",
        ),
        legend=dict(
            orientation="h",
            yanchor="bottom", y=1.02,
            xanchor="right",  x=1,
            font=dict(size=12),
        ),
        hovermode="x unified",
        height=540,
        plot_bgcolor="rgba(0,0,0,0)",
        paper_bgcolor="rgba(0,0,0,0)",
        margin=dict(l=60, r=30, t=65, b=55),
    )

    st.plotly_chart(fig, use_container_width=True)

    # ════════════════════════════════════════════════════════════════════════════
    # 9  VALIDACIÓN TEÓRICA — Tres indicadores
    # ════════════════════════════════════════════════════════════════════════════
    st.subheader("✅ Indicadores de Validación Teórica")

    row0      = df.iloc[0]
    rowN      = df.iloc[-1]
    max_delta = df["Δ(PNA−Retro)"].abs().max()
    tol       = max(capital * 1e-4, 0.01)

    vc1, vc2, vc3 = st.columns(3)

    # ── Check 1: ₀V = 0  (Principio de Equivalencia) ─────────────────────────
    v0  = float(row0["V_PNA"])
    ok0 = abs(v0) <= tol
    vc1.metric(
        label="₀V  (Principio de Equivalencia)",
        value=f"${v0:+.6f}",
        delta="≈ 0.00  ✓  Correcto" if ok0 else f"⚠  |₀V| = {abs(v0):.4f} ≠ 0",
        delta_color="off" if ok0 else "inverse",
    )

    # ── Check 2: Condición terminal ───────────────────────────────────────────
    vN, tN = float(rowN["V_PNA"]), int(rowN["t"])

    if producto in ("SOB_DOTAL_MIXTO", "SOB_DOTAL"):
        exp_N, label_N = capital, f"ₙV = C = ${capital:,.2f}"
    elif producto == "MUE_TEMPORAL":
        exp_N, label_N = 0.0, "ₙV = 0.00"
    else:  # Vida Entera
        exp_N, label_N = None, "Reserva en ω−1 (vida entera)"

    okN = (exp_N is None) or (abs(vN - exp_N) <= tol)
    vc2.metric(
        label=f"ₙV  (t = {tN})",
        value=f"${vN:,.4f}",
        delta=f"{label_N}  {'✓' if okN else '⚠  Revisar'}",
        delta_color="off" if okN else "inverse",
    )

    # ── Check 3: Prospectiva ≡ Retrospectiva ──────────────────────────────────
    ok_eq = max_delta <= tol
    vc3.metric(
        label="Máx |V_PNA − V_Retro|",
        value=f"${max_delta:.2e}",
        delta="Equivalencia verificada  ✓" if ok_eq else "⚠  Revisar base técnica",
        delta_color="off" if ok_eq else "inverse",
    )

# ════════════════════════════════════════════════════════════════════════════
    # 10  CUADRO DE AMORTIZACIÓN ACTUARIAL
    # ════════════════════════════════════════════════════════════════════════════
    st.markdown("---")
    st.subheader("📋 Cuadro de Amortización Actuarial")

    # Usamos configuración nativa de Streamlit (Evita Segmentation Faults de Pandas Style)
    st.dataframe(
        df,
        width="stretch",
        height=430,
        hide_index=True,
        column_config={
            "t": st.column_config.NumberColumn("t", format="%d"),
            "x+t": st.column_config.NumberColumn("x+t", format="%d"),
            "VP_Ben": st.column_config.NumberColumn("VP_Ben", format="%.6f"),
            "VP_Pri Anual": st.column_config.NumberColumn("VP_Pri Anual", format="%.6f"),
            "VP_Pri Fracc": st.column_config.NumberColumn("VP_Pri Fracc", format="%.6f"),
            "V_PU": st.column_config.NumberColumn("V_PU", format="$%.2f"),
            "V_PNA": st.column_config.NumberColumn("V_PNA", format="$%.2f"),
            "V_PNF": st.column_config.NumberColumn("V_PNF", format="$%.2f"),
            "V_Retro": st.column_config.NumberColumn("V_Retro", format="$%.2f"),
            "Δ(PNA−Retro)": st.column_config.NumberColumn("Δ(PNA−Retro)", format="%.2e"),
        }
    )

    # Nota sobre columnas por-unidad
    with st.expander("ℹ️ Acerca de las columnas VP_Ben y VP_Pri"):
        # Asegúrate de que la r minúscula esté justo antes de las comillas triples
        st.markdown(r"""
**VP_Ben** y **VP_Pri** son valores *por unidad de capital* (adimensionales).
Representan las funciones actuariales evaluadas en la edad alcanzada x+t:

| Columna | Fórmula | Descripción |
|:---|:---|:---|
| `VP_Ben` | Varía según producto | Valor Presente Actuarial de beneficios futuros por unidad |
| `VP_Pri Anual` | ppa_u · ä_{x+t:m−t\|} | Valor Presente de primas futuras (anual) por unidad |
| `VP_Pri Fracc` | ppa_ku · ä^{(k)}_{x+t:m−t\|} | Valor Presente de primas futuras (fraccionada) por unidad |

Las reservas en $ se obtienen multiplicando **(VP_Ben − VP_Pri) × C**.
""")

    # Botón de descarga CSV
    csv_bytes = df.to_csv(index=False).encode("utf-8")
    st.download_button(
        label=f"⬇️ Descargar CSV  ·  {producto}_x{x}_n{n}_m{m}_k{k}",
        data=csv_bytes,
        file_name=f"reservas_{producto}_x{x}_n{n}_m{m}_k{k}.csv",
        mime="text/csv",
        use_container_width=True,
    )

    # Nota sobre columnas por-unidad
    with st.expander("ℹ️ Acerca de las columnas VP_Ben y VP_Pri"):
        st.markdown("""
**VP_Ben** y **VP_Pri** son valores *por unidad de capital* (adimensionales).
Representan las funciones actuariales evaluadas en la edad alcanzada x+t:

| Columna | Fórmula | Descripción |
|:---|:---|:---|
| `VP_Ben` | Varía según producto | Valor Presente Actuarial de beneficios futuros por unidad |
| `VP_Pri Anual` | ppa_u · ä\_{x+t:m−t\\|} | Valor Presente de primas futuras (anual) por unidad |
| `VP_Pri Fracc` | ppa_ku · ä^{(k)}\_{x+t:m−t\\|} | Valor Presente de primas futuras (fraccionada) por unidad |

Las reservas en $ se obtienen multiplicando **(VP_Ben − VP_Pri) × C**.
""")

    # Botón de descarga CSV
    csv_bytes = df.to_csv(index=False).encode("utf-8")
    st.download_button(
        label=f"⬇️ Descargar CSV  ·  {producto}_x{x}_n{n}_m{m}_k{k}",
        data=csv_bytes,
        file_name=f"reservas_{producto}_x{x}_n{n}_m{m}_k{k}.csv",
        mime="text/csv",
        use_container_width=True,
    )

except Exception as exc:
    st.error(f"❌ Error en el cómputo: {exc}")
    with st.expander("Traza del error"):
        st.exception(exc)


# ══════════════════════════════════════════════════════════════════════════════
# FOOTER — Vista previa de conmutativos (siempre visible)
# ══════════════════════════════════════════════════════════════════════════════
st.markdown("---")
with st.expander("🔎 Vista previa de la tabla de mortalidad y conmutativos"):
    st.dataframe(
        tabla[["q(x)", "l(x)", "d(x)", "Dx", "Cx", "Nx", "Mx"]].head(30),
        use_container_width=True,
    )
