"""
Genera el reporte ejecutivo de ALOHAS como un único HTML autocontenido.

- Lee de los marts de dbt (alohas.db).
- Salida narrativa para público general: prosa + gráficas Plotly interactivas,
  sin código a la vista. El "working" vive en el repo (dbt/, notebooks/).
- Un solo archivo: report/aloha_report.html (Plotly embebido, abre offline).

Uso:  python report/build_report.py
"""

import os
import duckdb
import pandas as pd
import plotly.graph_objects as go
import plotly.io as pio
from plotly.offline import get_plotlyjs

# Ejecutar desde la raíz del repo (donde vive alohas.db)
if os.path.basename(os.getcwd()) == "report":
    os.chdir("..")

DB = "alohas.db"
OUT = "report/aloha_report.html"

# --- Paleta de marca ALOHAS -------------------------------------------------
PRIMARY = "#4A2B33"      # aubergine profundo
PRIMARY_2 = "#603B43"    # aubergine
BG = "#FAF7F2"           # crema
CARD = "#FFFFFF"
ACCENT = "#D28E78"       # terracota cálido (fondos / acentos)
ACCENT_STRONG = "#9E5236"  # terracota oscuro (texto/números, contraste AA)
INK = "#2B2B2B"          # gris carbón
MUTED = "#6B5E5A"
BORDER = "#ECE2DA"
GRID = "#EDE4DB"

CHANNELS = ["online", "wholesale", "retail", "marketplace"]
LABELS = {"online": "Online", "wholesale": "Wholesale", "retail": "Retail", "marketplace": "Marketplace"}
# Paleta cálida/editorial, distinguible y con contraste >=3:1 sobre blanco
COLORS = {"online": "#603B43", "wholesale": "#C2705A", "retail": "#4E6E5D", "marketplace": "#B5832B"}
PERSP = {"ceo": "ceo", "wh": "wh"}
GRAINS = {"M": "Mensual", "Q": "Trimestral", "Y": "Anual"}
DEFAULT_P, DEFAULT_G = "ceo", "Q"

CHART_FONT = "Inter, system-ui, -apple-system, sans-serif"


# --------------------------------------------------------------------------- #
# Datos
# --------------------------------------------------------------------------- #
def load_channel_data(con):
    df = con.execute("""
        select month, channel,
               net_sales_asof_report_eur as ceo,
               net_sales_asof_sale_eur    as wh
        from mart_returns_timing_monthly
        where venta_neta_pre_devolucion_eur > 0
        order by month
    """).fetchdf()
    df["month"] = pd.to_datetime(df["month"])
    return df


def aggregate(df, grain, valcol):
    d = df[["month", "channel", valcol]].copy()
    if grain == "M":
        d["period"] = d["month"]
    elif grain == "Y":
        d["period"] = d["month"].dt.to_period("Y").dt.start_time
    else:  # 'Q'
        d["period"] = d["month"].dt.to_period("Q").dt.start_time
    return d.groupby(["period", "channel"], as_index=False)[valcol].sum()


# --------------------------------------------------------------------------- #
# Gráficas (cada traza lleva meta = {p, g} para el toggle por JS)
# --------------------------------------------------------------------------- #
def fig_trend(df):
    fig = go.Figure()
    for p, valcol in PERSP.items():
        for g in GRAINS:
            agg = aggregate(df, g, valcol)
            for ch in CHANNELS:
                s = agg[agg["channel"] == ch]
                fig.add_trace(go.Scatter(
                    x=s["period"], y=s[valcol], name=LABELS[ch], mode="lines+markers",
                    line=dict(color=COLORS[ch], width=2.5), marker=dict(size=5),
                    meta={"p": p, "g": g}, legendgroup=ch,
                    visible=(p == DEFAULT_P and g == DEFAULT_G),
                    hovertemplate=f"<b>{LABELS[ch]}</b><br>%{{x|%b %Y}}<br>€%{{y:,.0f}}<extra></extra>",
                ))
    fig.update_layout(**_layout(height=460, ytitle="Venta neta (€)"))
    fig.update_yaxes(tickprefix="€", tickformat=",.0f")
    return fig


def fig_pie(df):
    """Participación acumulada de cada canal. Depende solo de perspectiva (foto del periodo completo)."""
    fig = go.Figure()
    for p, valcol in PERSP.items():
        tot = df.groupby("channel")[valcol].sum().reindex(CHANNELS)
        fig.add_trace(go.Pie(
            labels=[LABELS[c] for c in CHANNELS], values=tot.values,
            marker=dict(colors=[COLORS[c] for c in CHANNELS], line=dict(color=CARD, width=2)),
            hole=0.52, sort=False, direction="clockwise",
            textposition="outside", texttemplate="%{label}<br><b>%{percent}</b>",
            textfont=dict(family=CHART_FONT, size=13, color=INK),
            meta={"p": p, "g": "*"}, visible=(p == DEFAULT_P),
            hovertemplate="<b>%{label}</b><br>€%{value:,.0f}<br>%{percent} del total<extra></extra>",
        ))
    fig.update_layout(
        height=440, template="plotly_white", showlegend=False,
        margin=dict(l=20, r=20, t=20, b=20),
        font=dict(family=CHART_FONT, size=13, color=INK),
        paper_bgcolor=CARD, plot_bgcolor=CARD,
        annotations=[dict(text="Venta<br>neta", x=0.5, y=0.5, showarrow=False,
                          font=dict(family=CHART_FONT, size=15, color=MUTED))],
    )
    return fig


def fig_growth(df):
    """Crecimiento últimos 12m vs 12m previos por canal. Depende solo de perspectiva."""
    months = sorted(df["month"].unique())
    last12, prev12 = months[-12:], months[-24:-12]
    fig = go.Figure()
    for p, valcol in PERSP.items():
        l = df[df["month"].isin(last12)].groupby("channel")[valcol].sum()
        pr = df[df["month"].isin(prev12)].groupby("channel")[valcol].sum()
        growth = ((l - pr) / pr * 100).reindex(CHANNELS)
        fig.add_trace(go.Bar(
            x=[LABELS[c] for c in CHANNELS], y=growth.values,
            marker_color=[COLORS[c] for c in CHANNELS],
            text=[f"{v:+.1f}%" for v in growth.values], textposition="outside",
            textfont=dict(color=INK, size=13),
            meta={"p": p, "g": "*"}, visible=(p == DEFAULT_P),
            hovertemplate="<b>%{x}</b><br>Crecimiento %{y:+.1f}%<extra></extra>",
        ))
    fig.update_layout(**_layout(height=400, ytitle="Crecimiento interanual (%)", showlegend=False))
    fig.update_yaxes(ticksuffix="%")
    return fig


def _layout(height, ytitle, showlegend=True):
    axis = dict(gridcolor=GRID, linecolor=BORDER, zeroline=False,
                title_font=dict(size=12, color=MUTED), tickfont=dict(size=12, color=MUTED))
    return dict(
        height=height, template="plotly_white", showlegend=showlegend,
        margin=dict(l=72, r=24, t=28, b=46), hovermode="x unified",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0,
                    font=dict(size=12, color=INK)),
        xaxis={**axis, "title": None}, yaxis={**axis, "title": ytitle},
        font=dict(family=CHART_FONT, size=13, color=INK),
        paper_bgcolor=CARD, plot_bgcolor=CARD,
    )


# --------------------------------------------------------------------------- #
# Cifras para la narrativa
# --------------------------------------------------------------------------- #
def narrative_numbers(df, con):
    tot = df.groupby("channel")["ceo"].sum()
    share = (tot / tot.sum() * 100)
    months = sorted(df["month"].unique())
    l = df[df["month"].isin(months[-12:])].groupby("channel")["ceo"].sum()
    pr = df[df["month"].isin(months[-24:-12])].groupby("channel")["ceo"].sum()
    growth = ((l - pr) / pr * 100)
    delta_eur = (l - pr)
    ret = con.execute("""
        select channel, sum(total_unidades_devueltas)*100.0/sum(total_unidades_vendidas) tasa
        from mart_channel_sales_monthly group by 1
    """).fetchdf().set_index("channel")["tasa"]
    n = {c: dict(
        share=share[c], growth=growth[c], ret=ret[c],
        total_eur=tot[c], last12_eur=l[c], delta_eur=delta_eur[c],
    ) for c in CHANNELS}
    n["_gmin"], n["_gmax"] = growth.min(), growth.max()
    n["_total_eur"] = tot.sum()
    n["_last12_eur"] = l.sum()
    n["_prev12_eur"] = pr.sum()
    n["_delta_eur"] = l.sum() - pr.sum()
    n["_growth_total"] = (l.sum() - pr.sum()) / pr.sum() * 100
    # Cuánto del nuevo crecimiento viene de Online vs del resto
    n["_online_share_of_growth"] = delta_eur["online"] / (l.sum() - pr.sum()) * 100
    n["_rest_delta_eur"] = (l.sum() - pr.sum()) - delta_eur["online"]
    n["_rest_total_eur"] = tot.sum() - tot["online"]
    return n


def fmt_eur(v, short=False):
    """Formatea euros: 9.1M€ / 750k€ para resúmenes; 9.119.198€ para texto exacto."""
    if short:
        if abs(v) >= 1_000_000:
            return f"{v/1_000_000:.1f}M€".replace(".", ",")
        if abs(v) >= 1_000:
            return f"{v/1_000:.0f}k€"
        return f"{v:.0f}€"
    s = f"{v:,.0f}".replace(",", ".")
    return f"{s}€"


# --------------------------------------------------------------------------- #
# Componentes HTML
# --------------------------------------------------------------------------- #
def kpi(label, value, sub, value_class=""):
    return f"""
    <div class="kpi">
      <div class="kpi-label">{label}</div>
      <div class="kpi-value {value_class}">{value}</div>
      <div class="kpi-sub">{sub}</div>
    </div>"""


def chart_div(fig, div_id):
    inner = pio.to_html(fig, full_html=False, include_plotlyjs=False, div_id=div_id,
                        config={"displayModeBar": False, "responsive": True})
    return f'<div class="card chart-card">{inner}</div>'


# --------------------------------------------------------------------------- #
# Sección 01
# --------------------------------------------------------------------------- #
def section_q1(con):
    df = load_channel_data(con)
    n = narrative_numbers(df, con)

    kpis = f"""
    <div class="kpi-grid">
      {kpi("Venta neta (24 meses)", fmt_eur(n['_total_eur'], short=True), f"{fmt_eur(n['_last12_eur'], short=True)} en los últimos 12 meses")}
      {kpi("Crecimiento interanual", f"+{n['_growth_total']:.0f}%", f"+{fmt_eur(n['_delta_eur'], short=True)} vs el año anterior", "pos")}
      {kpi("Online", f"{fmt_eur(n['online']['total_eur'], short=True)}", f"{n['online']['share']:.0f}% del total — más que los otros tres canales juntos")}
      {kpi("Devoluciones", f"{n['online']['ret']:.0f}% vs {n['wholesale']['ret']:.0f}%", "Online frente a Wholesale")}
    </div>"""

    prose_intro = f"""
    <p>En 24 meses ALOHAS ha facturado <strong>{fmt_eur(n['_total_eur'], short=True)}</strong>
    de venta neta. <strong>Online</strong> lidera con
    <strong>{fmt_eur(n['online']['total_eur'], short=True)}</strong>
    ({n['online']['share']:.0f}%); <strong>Wholesale</strong>
    ({fmt_eur(n['wholesale']['total_eur'], short=True)}) y <strong>Retail</strong>
    ({fmt_eur(n['retail']['total_eur'], short=True)}) rondan un quinto cada uno;
    <strong>Marketplace</strong> queda residual ({fmt_eur(n['marketplace']['total_eur'], short=True)},
    {n['marketplace']['share']:.0f}%). Toda la sección es venta neta — sin impuestos
    ni devoluciones.</p>
    """

    prose_trend = f"""
    <p>Crecimiento sostenido con pico Nov–Dic. En 12 meses:
    <strong>{fmt_eur(n['_prev12_eur'], short=True)} → {fmt_eur(n['_last12_eur'], short=True)}</strong>
    (<strong>+{fmt_eur(n['_delta_eur'], short=True)}, +{n['_growth_total']:.0f}%</strong>) —
    equivale a más de <strong>tres Marketplaces enteros</strong> añadidos en un año.</p>
    """

    prose_mix = f"""
    <p>Online ({fmt_eur(n['online']['total_eur'], short=True)}) pesa más que los
    otros tres canales juntos ({fmt_eur(n['_rest_total_eur'], short=True)}). Reparto
    estable.</p>
    """

    prose_growth = """
    <p>Banda estrecha de crecimiento entre los cuatro canales. <strong>Motor
    ancho</strong>, sin un único punto de dependencia.</p>
    """

    prose_lens = """
    <div class="note">
      <p><strong>Dos lecturas, según cuándo se cuenta una devolución:</strong></p>
      <ul>
        <li><strong>CEO (financiera):</strong> la devolución se registra el día que ocurre.</li>
        <li><strong>Head of Wholesale (cohorte):</strong> la devolución se descuenta del mes de la venta original.</li>
      </ul>
    </div>
    """

    controls = """
      <div class="controls">
        <label>Perspectiva
          <span class="select-wrap">
            <select id="q1_perspective" onchange="q1Update()">
              <option value="ceo">CEO — visión financiera</option>
              <option value="wh">Head of Wholesale — por cohorte</option>
            </select>
          </span>
        </label>
        <label>Ventana de tiempo
          <span class="select-wrap">
            <select id="q1_grain" onchange="q1Update()">
              <option value="Q" selected>Trimestral</option>
              <option value="M">Mensual</option>
              <option value="Y">Anual</option>
            </select>
          </span>
        </label>
      </div>
    """

    return f"""
    <section id="q1">
      <span class="eyebrow">Pregunta 01</span>
      <h2>Ventas por canal</h2>
      <p class="lead">¿Cómo le va al negocio en cada canal?</p>
      {kpis}
      {prose_intro}
      {controls}

      <h3>Tendencia de venta neta por canal</h3>
      {prose_trend}
      {chart_div(fig_trend(df), "q1_trend")}

      <h3>Participación de cada canal en la venta total</h3>
      {prose_mix}
      {chart_div(fig_pie(df), "q1_mix")}

      <h3>¿Algún canal crece más rápido que los demás?</h3>
      {prose_growth}
      {chart_div(fig_growth(df), "q1_growth")}

      {prose_lens}
    </section>
    """


# --------------------------------------------------------------------------- #
# Sección 00 — Auditoría de datos
# --------------------------------------------------------------------------- #
def section_audit(con):
    counts = con.execute("""
        with orph_prod as (
          select count(*)::int as c, sum(v.gross_sale_eur) as eur
          from stg_sales v left join stg_products p on v.product_id = p.product_id
          where p.product_id is null
        ),
        orph_ship as (
          select count(*)::int as c, sum(v.gross_sale_eur) as eur
          from stg_sales v left join stg_shipments s on v.shipment_id = s.shipment_id
          where s.shipment_id is null
        ),
        countries as (
          select count(distinct destination_country_code)::int as c from stg_shipments
        )
        select op.c, op.eur, os.c, os.eur, co.c
        from orph_prod op, orph_ship os, countries co
    """).fetchone()
    op_n, op_eur, os_n, os_eur, n_countries = counts
    total_orph_n = op_n + os_n
    total_orph_eur = (op_eur or 0) + (os_eur or 0)

    kpis = f"""
    <div class="kpi-grid">
      {kpi("Tests dbt", "40 / 40", "0 errores · 2 WARN intencionales", "pos")}
      {kpi("Errores matemáticos", "0", "net, taxes y gross cuadran al céntimo", "pos")}
      {kpi("Líneas con FK rota", f"{total_orph_n:,}".replace(",", "."), f"{fmt_eur(total_orph_eur, short=True)} de venta bruta combinada")}
      {kpi("Países sin moneda", str(n_countries), "ninguno con columna currency_code")}
    </div>"""

    findings = f"""
    <h3>Hallazgos</h3>
    <ul class="audit-list">
      <li><strong>{op_n} líneas sin producto</strong> (~{fmt_eur(op_eur, short=True)}) y
      <strong>{os_n} sin envío</strong>, mayormente en Online. <em>Las conservo en Sec 01,
      las excluyo en Sec 03</em> (sin coste no hay margen).</li>
      <li><strong>Consistencia financiera</strong>: net, taxes y gross cuadran al céntimo;
      wholesale sin impuestos.</li>
      <li><strong>Sin negativos ni devoluciones &gt; ventas</strong>.</li>
      <li><strong>Outliers de precio validados</strong>: artículos premium reales (400–550€),
      no error de escala.</li>
    </ul>
    """

    gap = """
    <div class="note">
      <p><strong>Gap de modelado, no de datos:</strong> 8 países (ES, FR, DE, US, IT, UK, PT,
      MX) y <strong>cero columnas de moneda</strong> — todo viene pre-convertido a EUR. En
      producción haría falta <code>currency_code</code> + <code>fx_rate_at_txn</code> para
      auditar el cambio y separar pérdida cambiaria del margen.</p>
    </div>
    """

    roadmap = """
    <details class="decision">
      <summary>Qué dejaría en el roadmap si tuviera más tiempo</summary>
      <div class="decision-body">
        <p><strong>Catálogo enriquecido:</strong> añadir <code>weight_kg</code> y
        <code>currency_code</code> a las tablas fuente. Son los dos gaps que más limitan la
        fidelidad del margen y del análisis multi-país.</p>
        <p><strong>Snapshot con historia real:</strong> correr el snapshot sobre varios cortes
        para que <code>fct_return</code> use fechas reales de devolución en vez del supuesto
        de +60 días.</p>
        <p><strong>Sensibilidad parametrizada:</strong> sacar el 8€/u de procesar devoluciones
        a una variable de dbt y exponer un slider en el reporte.</p>
        <p><strong>Investigar SKUs huérfanos:</strong> ¿catálogo incompleto (modelado) o
        registros basura (datos)? Hoy los aíslo pero no entiendo su origen.</p>
      </div>
    </details>
    """

    return f"""
    <section id="audit">
      <span class="eyebrow">Antes de empezar</span>
      <h2>Lo que encontré en los datos</h2>
      <p class="lead">El dataset es sintético, pero la auditoría es de verdad.</p>
      {kpis}
      {findings}
      {gap}
      {roadmap}
    </section>
    """


# --------------------------------------------------------------------------- #
# Sección 02 — Devoluciones tardías
# --------------------------------------------------------------------------- #
def load_returns_data(con):
    df = con.execute("""
        select month,
               sum(venta_neta_pre_devolucion_eur)        as pre_devolucion,
               sum(net_sales_asof_sale_eur)              as asof_sale,
               sum(net_sales_asof_report_eur)            as asof_report
        from mart_returns_timing_monthly
        group by month
        order by month
    """).fetchdf()
    df["month"] = pd.to_datetime(df["month"])
    return df


def returns_kpis(con):
    return con.execute("""
        with totals as (
          select sum(net_sales_eur) as net_pre from stg_sales
        ),
        ret as (
          select sum(return_value_eur) as total_ret, count(*) as eventos from fct_return
        ),
        diffs as (
          select max(abs(net_sales_asof_sale_eur - net_sales_asof_report_eur)) as max_diff
          from (
            select month,
                   sum(net_sales_asof_sale_eur)   as net_sales_asof_sale_eur,
                   sum(net_sales_asof_report_eur) as net_sales_asof_report_eur
            from mart_returns_timing_monthly group by month
          )
        ),
        online_ret as (
          select sum(return_value_eur) as online_ret
          from fct_return where channel = 'online'
        )
        select t.net_pre, r.total_ret, r.eventos, d.max_diff, o.online_ret
        from totals t, ret r, diffs d, online_ret o
    """).fetchone()


def fig_returns_by_channel(con):
    """Barra horizontal: tasa de devolución por canal, con € devueltos en hover.
    Cuenta la historia 'Online concentra las devoluciones' en un solo vistazo."""
    df = con.execute("""
        with ret as (
          select channel,
                 sum(return_value_eur) as devuelto_eur,
                 sum(units_returned)   as unidades_devueltas
          from fct_return group by 1
        ),
        sold as (
          select channel,
                 sum(quantity_sold)    as unidades_vendidas,
                 sum(net_sales_eur)    as net_eur
          from stg_sales group by 1
        )
        select s.channel, r.devuelto_eur, r.unidades_devueltas,
               s.unidades_vendidas, s.net_eur,
               r.unidades_devueltas * 100.0 / s.unidades_vendidas as tasa
        from sold s join ret r using (channel)
    """).fetchdf().sort_values("tasa")

    fig = go.Figure()
    fig.add_trace(go.Bar(
        y=[LABELS[c] for c in df["channel"]],
        x=df["tasa"],
        orientation="h",
        marker_color=[COLORS[c] for c in df["channel"]],
        text=[f"{v:.1f}%" for v in df["tasa"]],
        textposition="outside",
        textfont=dict(color=INK, size=13),
        customdata=df[["devuelto_eur", "unidades_devueltas"]].values,
        hovertemplate=(
            "<b>%{y}</b><br>Tasa devolución: %{x:.1f}%"
            "<br>Devuelto: €%{customdata[0]:,.0f}"
            "<br>Unidades: %{customdata[1]:,.0f}<extra></extra>"
        ),
    ))
    fig.update_layout(
        height=300, template="plotly_white", showlegend=False,
        margin=dict(l=20, r=80, t=20, b=40),
        font=dict(family=CHART_FONT, size=13, color=INK),
        paper_bgcolor=CARD, plot_bgcolor=CARD,
        xaxis=dict(ticksuffix="%", gridcolor=GRID, linecolor=BORDER, zeroline=False,
                   tickfont=dict(size=12, color=MUTED), title=None),
        yaxis=dict(linecolor=BORDER, tickfont=dict(size=13, color=INK), title=None),
    )
    return fig


def fig_definitions(df):
    """Bar chart de la divergencia mensual entre las dos métricas.
    Sin texto extra: barra alta = la elección de métrica importa ese mes;
    barra pequeña = las dos métricas coinciden."""
    diff = df["asof_report"] - df["asof_sale"]

    fig = go.Figure()
    fig.add_trace(go.Bar(
        x=df["month"], y=diff,
        marker_color=[PRIMARY if v >= 0 else ACCENT_STRONG for v in diff],
        marker_line_width=0,
        hovertemplate=(
            "<b>%{x|%b %Y}</b><br>"
            "Diferencia: €%{y:+,.0f}"
            "<extra></extra>"
        ),
        showlegend=False,
    ))
    # Trazas vacías solo para que aparezca una leyenda explicativa
    fig.add_trace(go.Bar(
        x=[None], y=[None], marker_color=PRIMARY,
        name="Financiera registra MÁS este mes", showlegend=True,
    ))
    fig.add_trace(go.Bar(
        x=[None], y=[None], marker_color=ACCENT_STRONG,
        name="Cohorte registra MÁS este mes", showlegend=True,
    ))
    fig.update_layout(**_layout(height=380, ytitle="Diferencia (€)"))
    fig.update_yaxes(tickprefix="€", tickformat=",.0f",
                     zeroline=True, zerolinecolor=PRIMARY, zerolinewidth=1)
    fig.update_xaxes(tickformat="%b %Y")
    return fig


def section_q2(con):
    df = load_returns_data(con)
    net_pre, total_ret, eventos, max_diff, online_ret = returns_kpis(con)
    ret_pct = total_ret / net_pre * 100
    online_pct = online_ret / total_ret * 100

    kpis = f"""
    <div class="kpi-grid">
      {kpi("Devuelto en 24 meses", fmt_eur(total_ret, short=True), f"{ret_pct:.0f}% del net pre-devolución")}
      {kpi("Online absorbe", f"{online_pct:.0f}%", f"{fmt_eur(online_ret, short=True)} de los {fmt_eur(total_ret, short=True)} devueltos")}
      {kpi("Líneas devueltas", f"{eventos:,}".replace(",", "."), "una por cada evento de devolución")}
      {kpi("Pico de divergencia", fmt_eur(max_diff, short=True), "diferencia mensual entre las dos métricas")}
    </div>"""

    intro = """
    <p><code>quantity_returned</code> se sobreescribe sobre la venta original — sin
    nueva fila, sin fecha. <strong>Un dashboard hecho hoy mentirá el próximo
    trimestre</strong>.</p>
    """

    returns_chart_intro = """
    <h3>¿Dónde se concentran las devoluciones?</h3>
    <p>Online no solo vende más: devuelve mucho más por cada cosa vendida.</p>
    """

    schema = """
    <h3>Schema propuesto</h3>
    <div class="schema">
      <div class="schema-step">
        <div class="schema-step-label">Fuente</div>
        <div class="schema-step-name">stg_sales</div>
        <div class="schema-step-note">campo mutable</div>
      </div>
      <div class="schema-arrow">→</div>
      <div class="schema-step">
        <div class="schema-step-label">Snapshot SCD-2</div>
        <div class="schema-step-name">snap_sale_order_line</div>
        <div class="schema-step-note">capta cada cambio</div>
      </div>
      <div class="schema-arrow">→</div>
      <div class="schema-step">
        <div class="schema-step-label">Eventos</div>
        <div class="schema-step-name">fct_return</div>
        <div class="schema-step-note">sale_date + return_date</div>
      </div>
      <div class="schema-arrow">→</div>
      <div class="schema-step">
        <div class="schema-step-label">Mart</div>
        <div class="schema-step-name">mart_returns_timing</div>
        <div class="schema-step-note">las dos métricas</div>
      </div>
    </div>
    """

    definitions = """
    <h3>Dos definiciones</h3>
    <div class="defs-grid">
      <div class="def-card">
        <div class="def-card-h">As-of report date</div>
        <div class="def-card-sub">la contabilidad</div>
        <ul>
          <li>Resta en el <strong>mes en que ocurre</strong> la devolución.</li>
          <li>Mes cerrado <strong>no se vuelve a tocar</strong>.</li>
          <li>Para CFO, board, cierre mensual.</li>
        </ul>
      </div>
      <div class="def-card">
        <div class="def-card-h">As-of date of sale</div>
        <div class="def-card-sub">la cohorte</div>
        <ul>
          <li>Resta en el <strong>mes de la venta original</strong>.</li>
          <li><strong>Restata el pasado</strong> al llegar nuevas devoluciones.</li>
          <li>Para marketing, calidad de cohorte/campaña.</li>
        </ul>
      </div>
    </div>
    """

    timing_chart_intro = """
    <h3>¿Cuándo cambia el resultado según qué definición uses?</h3>
    <p>Cerca de cero = las métricas coinciden. Lejos = la elección importa.</p>
    """

    closing = """
    <div class="note">
      <p><strong>El mismo chart, dentro de 6 meses:</strong></p>
      <ul>
        <li><strong>Sobre la tabla cruda:</strong> Q1 era 1,0M€, ahora es 920k€.
        Sin un commit. El pasado se reescribió solo.</li>
        <li><strong>As-of report date:</strong> Q1 hoy = Q1 en 6 meses. Estable.</li>
        <li><strong>As-of date of sale:</strong> Q1 también baja, pero es
        <em>explícito</em>: la métrica dice "balance de cohorte a fecha de hoy".</li>
      </ul>
      <p><strong>Defiendo usar las dos.</strong> Report para finanzas; sale para
      cohorte.</p>
      <details class="decision">
        <summary>Un supuesto que es importante hacer explícito</summary>
        <div class="decision-body">
          <p>El dataset <strong>no trae fecha real de devolución</strong>. En esta
          versión estimo cada devolución como <code>sale_date + 60 días</code> (punto
          medio de la ventana 30–90 días que el brief describe).</p>
          <p>En producción, ese campo se reemplaza por el <code>dbt_valid_from</code>
          del snapshot — la fecha en que detectamos que <code>quantity_returned</code>
          cambió. Esa es la mecánica que el schema habilita; el +60 días es solo el
          puente mientras no exista historia real de snapshot.</p>
        </div>
      </details>
    </div>
    """

    return f"""
    <section id="q2">
      <span class="eyebrow">Pregunta 02</span>
      <h2>Devoluciones tardías</h2>
      <p class="lead">¿Cómo medimos net sales cuando una venta de enero puede devolverse en marzo?</p>
      {kpis}
      {intro}
      {returns_chart_intro}
      {chart_div(fig_returns_by_channel(con), "q2_by_channel")}
      {schema}
      {definitions}
      {timing_chart_intro}
      {chart_div(fig_definitions(df), "q2_definitions")}
      {closing}
    </section>
    """


# --------------------------------------------------------------------------- #
# Sección 03 — Margen de contribución
# --------------------------------------------------------------------------- #
CATEGORY_ORDER = ["Shoes", "Outerwear", "Dresses", "Bottoms", "Bags", "Tops", "Swimwear", "Accessories"]
CHANNEL_ORDER_BY_MARGIN = ["wholesale", "retail", "marketplace", "online"]
COST_COLORS = {
    "margen":   PRIMARY,
    "producto": "#B89E94",
    "envio":    ACCENT,
    "ret":      ACCENT_STRONG,
}


def fig_margin_heatmap(con):
    df = con.execute("""
        select channel, product_category,
               porcentaje_margen_contribucion * 100 as margen_pct
        from mart_contribution_margin
    """).fetchdf()
    pivot = (df.pivot(index="channel", columns="product_category", values="margen_pct")
               .reindex(index=CHANNEL_ORDER_BY_MARGIN, columns=CATEGORY_ORDER))

    fig = go.Figure(data=go.Heatmap(
        z=pivot.values,
        x=pivot.columns,
        y=[LABELS[c] for c in pivot.index],
        colorscale=[[0, "#E8C9B8"], [0.5, ACCENT], [1, PRIMARY]],
        text=[[f"{v:.0f}%" for v in row] for row in pivot.values],
        texttemplate="%{text}",
        textfont=dict(color="white", size=13, family=CHART_FONT),
        hovertemplate="<b>%{y} × %{x}</b><br>Margen: %{z:.1f}%<extra></extra>",
        colorbar=dict(ticksuffix="%", tickfont=dict(size=11, color=MUTED),
                      thickness=12, len=0.85),
        zmin=35, zmax=60,
    ))
    fig.update_layout(
        height=300, template="plotly_white",
        margin=dict(l=20, r=20, t=20, b=40),
        font=dict(family=CHART_FONT, size=13, color=INK),
        paper_bgcolor=CARD, plot_bgcolor=CARD,
        xaxis=dict(side="bottom", tickfont=dict(size=12, color=MUTED), title=None),
        yaxis=dict(tickfont=dict(size=13, color=INK), title=None, autorange="reversed"),
    )
    return fig


def fig_cost_structure(con):
    df = con.execute("""
        select channel,
               sum(costo_producto_neto_eur) as producto,
               sum(costo_envio_eur)         as envio,
               sum(costo_retornos_estimado_eur) as ret,
               sum(margen_contribucion_eur) as margen
        from mart_contribution_margin
        group by 1
    """).fetchdf()
    df["total"] = df[["producto", "envio", "ret", "margen"]].sum(axis=1)
    for c in ["producto", "envio", "ret", "margen"]:
        df[f"{c}_pct"] = df[c] / df["total"] * 100
    df = df.set_index("channel").reindex(CHANNEL_ORDER_BY_MARGIN).reset_index()

    fig = go.Figure()
    parts = [
        ("margen", "Margen"),
        ("producto", "Coste producto"),
        ("envio", "Envío"),
        ("ret", "Procesar devoluciones"),
    ]
    for key, label in parts:
        fig.add_trace(go.Bar(
            y=[LABELS[c] for c in df["channel"]],
            x=df[f"{key}_pct"],
            orientation="h",
            name=label,
            marker_color=COST_COLORS[key],
            customdata=df[[key]].values,
            hovertemplate=f"<b>{label}</b><br>"
                          "%{x:.1f}% · €%{customdata[0]:,.0f}<extra></extra>",
        ))
    fig.update_layout(
        barmode="stack",
        height=280, template="plotly_white",
        margin=dict(l=20, r=20, t=20, b=40),
        font=dict(family=CHART_FONT, size=13, color=INK),
        paper_bgcolor=CARD, plot_bgcolor=CARD,
        legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0,
                    font=dict(size=12, color=INK)),
        xaxis=dict(ticksuffix="%", gridcolor=GRID, linecolor=BORDER, zeroline=False,
                   tickfont=dict(size=12, color=MUTED), title=None, range=[0, 100]),
        yaxis=dict(linecolor=BORDER, tickfont=dict(size=13, color=INK), title=None,
                   autorange="reversed"),
    )
    return fig


def margin_kpis(con):
    return con.execute("""
        with totals as (
          select sum(venta_neta_real_eur) as venta,
                 sum(margen_contribucion_eur) as margen,
                 sum(costo_envio_eur) as envio
          from mart_contribution_margin
        ),
        by_ch as (
          select channel,
                 sum(margen_contribucion_eur) * 100.0 / sum(venta_neta_real_eur) as pct
          from mart_contribution_margin group by 1
        )
        select t.venta, t.margen, t.envio,
               (select pct from by_ch where channel='wholesale') as wh_pct,
               (select pct from by_ch where channel='online')    as on_pct
        from totals t
    """).fetchone()


def section_q3(con):
    venta, margen, envio, wh_pct, on_pct = margin_kpis(con)
    margen_pct = margen / venta * 100
    gap_pp = wh_pct - on_pct

    kpis = f"""
    <div class="kpi-grid">
      {kpi("Margen de contribución 24m", fmt_eur(margen, short=True), f"{margen_pct:.0f}% sobre venta neta", "pos")}
      {kpi("Mejor canal", f"{wh_pct:.0f}%", "Wholesale lidera en %")}
      {kpi("Gap Wholesale vs Online", f"{gap_pp:.0f} pp", f"{wh_pct:.1f}% vs {on_pct:.1f}%")}
      {kpi("Coste asumido por devolución", "8€/u", "supuesto más opinable")}
    </div>"""

    intro = """
    <p>Lo que sobra de cada venta tras quitar tres costes: producto, envío y
    procesar devoluciones.</p>
    """

    assumptions = """
    <div class="note">
      <p><strong>Tres reglas y una exclusión:</strong></p>
      <ul>
        <li><strong>Envío repartido por paquete</strong>: si un envío lleva varias
        prendas, cada una asume una parte proporcional a su precio. Un bolso de
        400€ paga más envío que una camiseta de 30€ del mismo paquete.
          <details class="decision">
            <summary>¿Por qué repartir por precio y no por peso?</summary>
            <div class="decision-body">
              <p>Lo ideal sería repartir por <strong>peso o volumen</strong> — es
              lo que el carrier realmente factura. El catálogo (<code>dim_product</code>)
              no incluye peso ni dimensiones, así que usé el precio como atajo:
              el artículo caro absorbe más.</p>
              <p>Es una decisión defendible cuando falta información, no la
              "correcta". Al nivel agregado canal × categoría apenas mueve el
              resultado (envío es ~2,3% de la venta neta).</p>
              <p><strong>Con más tiempo:</strong> añadir <code>weight_kg</code> a
              <code>dim_product</code> y repartir por <code>(peso × unidades)</code>
              dentro del paquete.</p>
            </div>
          </details>
        </li>
        <li><strong>La devolución vuelve al stock</strong>: no pierdo su coste de
        producto, solo descuento las unidades netas (vendidas − devueltas).</li>
        <li><strong>Procesar una devolución: 8€/u</strong> (recibir, inspeccionar,
        re-empacar). Supuesto más opinable: a 15€/u, Online bajaría ~1 pp.</li>
        <li><strong>Excluyo huérfanos</strong>: ~1.250 líneas (~270k€) sin producto
        o sin envío. Sin coste no hay margen que calcular. En Sección 01 sí
        cuentan.</li>
      </ul>
    </div>
    """

    heatmap_intro = """
    <h3>¿Qué combinaciones dejan más margen?</h3>
    <p>Cuanto más oscuro, mejor. <strong>Wholesale</strong> gana cualquier fila;
    <strong>Shoes</strong> y <strong>Outerwear</strong> cualquier columna. Peor
    combo: Online × Accessories (37%).</p>
    """

    flip = """
    <h3>El mismo negocio, dos rankings distintos</h3>
    <p>Pasamos de venta a margen % y los rankings cambian. Por canal,
    <strong>Online</strong> cae del 1º al 4º. Por categoría, <strong>Bags</strong>
    sale del top 4 y <strong>Shoes</strong> salta al 1º.</p>

    <div class="rank-section-label">Por canal</div>
    <div class="rankings-grid">
      <div class="rank-col">
        <div class="rank-col-h">Por venta neta</div>
        <ol>
          <li><span class="rk-name"><strong>Online</strong></span><span class="rk-val">5,1M€</span></li>
          <li><span class="rk-name">Wholesale</span><span class="rk-val">1,8M€</span></li>
          <li><span class="rk-name">Retail</span><span class="rk-val">1,7M€</span></li>
          <li><span class="rk-name">Marketplace</span><span class="rk-val">0,4M€</span></li>
        </ol>
      </div>
      <div class="rank-col">
        <div class="rank-col-h">Por margen %</div>
        <ol>
          <li><span class="rk-name"><strong>Wholesale</strong></span><span class="rk-val">55,5%</span></li>
          <li><span class="rk-name">Retail</span><span class="rk-val">42,9%</span></li>
          <li><span class="rk-name">Marketplace</span><span class="rk-val">42,8%</span></li>
          <li><span class="rk-name">Online</span><span class="rk-val">42,6%</span></li>
        </ol>
      </div>
    </div>

    <div class="rank-section-label">Por categoría (top 4)</div>
    <div class="rankings-grid">
      <div class="rank-col">
        <div class="rank-col-h">Por venta neta</div>
        <ol>
          <li><span class="rk-name">Outerwear</span><span class="rk-val">2,58M€</span></li>
          <li><span class="rk-name">Dresses</span><span class="rk-val">1,51M€</span></li>
          <li><span class="rk-name"><strong>Bags</strong></span><span class="rk-val">1,47M€</span></li>
          <li><span class="rk-name">Shoes</span><span class="rk-val">1,14M€</span></li>
        </ol>
      </div>
      <div class="rank-col">
        <div class="rank-col-h">Por margen %</div>
        <ol>
          <li><span class="rk-name"><strong>Shoes</strong></span><span class="rk-val">48%</span></li>
          <li><span class="rk-name">Outerwear</span><span class="rk-val">47%</span></li>
          <li><span class="rk-name">Dresses</span><span class="rk-val">46%</span></li>
          <li><span class="rk-name">Bottoms</span><span class="rk-val">44%</span></li>
        </ol>
      </div>
    </div>
    """

    cost_intro = """
    <h3>¿A dónde se va cada euro vendido?</h3>
    <p>El producto se lleva la mitad de cada euro. Envío + devoluciones &lt;5%.
    La palanca está en el producto, no en la logística.</p>
    """

    closing = """
    <div class="note">
      <p><strong>Quién gana dinero, en una hoja:</strong></p>
      <ul>
        <li><strong>Más margen absoluto:</strong> Online (2,07M€) + Outerwear (1,21M€).</li>
        <li><strong>Más eficiencia en %:</strong> Wholesale (55,5%) + Shoes (48%).</li>
        <li><strong>Combo ganador:</strong> Wholesale × Shoes (58%). Peor: Online × Accessories (37%).</li>
        <li><strong>Palanca:</strong> Online tiene techo de mejora alto bajando su tasa de devolución; Wholesale ya está optimizado.</li>
      </ul>
    </div>
    """

    return f"""
    <section id="q3">
      <span class="eyebrow">Pregunta 03</span>
      <h2>Margen de contribución</h2>
      <p class="lead">¿Qué canales ganan dinero de verdad — no solo en la gráfica de ingresos?</p>
      {kpis}
      {intro}
      {assumptions}
      {heatmap_intro}
      {chart_div(fig_margin_heatmap(con), "q3_heatmap")}
      {flip}
      {cost_intro}
      {chart_div(fig_cost_structure(con), "q3_cost")}
      {closing}
    </section>
    """


JS = """
<script>
function q1Update() {
  var p = document.getElementById('q1_perspective').value;
  var g = document.getElementById('q1_grain').value;
  ['q1_trend', 'q1_mix', 'q1_growth'].forEach(function (id) {
    var gd = document.getElementById(id);
    if (!gd || !gd.data) return;
    var vis = gd.data.map(function (t) {
      var okG = (t.meta.g === '*' || t.meta.g === g);
      return (t.meta.p === p && okG);
    });
    Plotly.restyle(gd, { visible: vis });
  });
}
document.addEventListener('DOMContentLoaded', q1Update);
</script>
"""

CSS = f"""
<style>
  @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&family=Playfair+Display:wght@500;600;700&display=swap');

  :root {{
    --primary:{PRIMARY}; --primary-2:{PRIMARY_2}; --bg:{BG}; --card:{CARD};
    --accent:{ACCENT}; --accent-strong:{ACCENT_STRONG}; --ink:{INK};
    --muted:{MUTED}; --border:{BORDER};
  }}
  * {{ box-sizing:border-box; }}
  body {{
    font-family:Inter,system-ui,-apple-system,sans-serif; color:var(--ink);
    background:var(--bg); max-width:920px; margin:0 auto; padding:56px 24px 110px;
    line-height:1.7; font-size:16.5px; -webkit-font-smoothing:antialiased;
  }}
  h1,h2,h3 {{ font-family:'Playfair Display',Georgia,serif; font-weight:600; letter-spacing:-.01em; }}

  header {{ border-bottom:3px solid var(--primary); padding-bottom:22px; margin-bottom:14px; }}
  header .brand {{ letter-spacing:.4em; font-size:12px; color:var(--primary-2); font-weight:700;
                  font-family:Inter,sans-serif; }}
  header h1 {{ font-size:40px; margin:14px 0 6px; color:var(--primary); line-height:1.1; }}
  header p {{ color:var(--muted); margin:0; font-size:15px; }}
  header .byline {{ margin-top:10px; font-size:13px; letter-spacing:.02em; color:var(--accent-strong); }}

  .eyebrow {{ display:inline-block; font-size:12px; font-weight:600; letter-spacing:.16em;
             text-transform:uppercase; color:var(--accent-strong); margin-top:40px; }}
  h2 {{ color:var(--primary); font-size:30px; margin:6px 0 4px; }}
  h3 {{ font-size:22px; margin-top:40px; color:var(--primary-2); }}
  p.lead {{ font-size:19px; color:var(--muted); font-style:italic; margin:0 0 8px;
           font-family:'Playfair Display',serif; }}
  p {{ margin:14px 0; }}
  strong {{ color:#1a1212; font-weight:600; }}
  em {{ color:var(--primary-2); }}

  /* KPI cards */
  .kpi-grid {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(180px,1fr));
              gap:16px; margin:26px 0 30px; }}
  .kpi {{ background:var(--card); border:1px solid var(--border); border-radius:14px;
         padding:18px 20px; box-shadow:0 1px 3px rgba(74,43,51,.05); }}
  .kpi-label {{ font-size:11.5px; font-weight:600; letter-spacing:.08em; text-transform:uppercase;
               color:var(--muted); }}
  .kpi-value {{ font-family:'Playfair Display',serif; font-size:34px; font-weight:600;
               color:var(--primary); margin:6px 0 2px; line-height:1; }}
  .kpi-value.pos {{ color:var(--accent-strong); }}
  .kpi-sub {{ font-size:13px; color:var(--muted); }}

  /* Controls */
  .controls {{ display:flex; gap:20px; flex-wrap:wrap; background:var(--card);
              border:1px solid var(--border); border-radius:14px; padding:16px 18px; margin:8px 0 6px;
              box-shadow:0 1px 3px rgba(74,43,51,.05); }}
  .controls label {{ font-size:12px; font-weight:600; letter-spacing:.04em; color:var(--muted);
                    text-transform:uppercase; display:flex; flex-direction:column; gap:7px;
                    min-width:0; flex:1 1 280px; }}
  .select-wrap {{ position:relative; display:block; width:100%; min-width:0; }}
  .select-wrap::after {{ content:""; position:absolute; right:14px; top:50%; width:8px; height:8px;
                        border-right:2px solid var(--primary-2); border-bottom:2px solid var(--primary-2);
                        transform:translateY(-70%) rotate(45deg); pointer-events:none; }}
  .controls select {{ font-family:Inter,sans-serif; font-size:14px; font-weight:500; text-transform:none;
                     letter-spacing:0; padding:9px 38px 9px 13px; border:1.5px solid var(--border);
                     border-radius:9px; background:var(--bg); color:var(--ink);
                     width:100%; max-width:100%; min-width:0;
                     cursor:pointer; appearance:none; -webkit-appearance:none;
                     text-overflow:ellipsis;
                     transition:border-color .18s ease, box-shadow .18s ease; }}
  .controls select:hover {{ border-color:var(--accent); }}
  .controls select:focus-visible {{ outline:none; border-color:var(--accent-strong);
                                    box-shadow:0 0 0 3px rgba(210,142,120,.35); }}

  /* Chart cards */
  .card.chart-card {{ background:var(--card); border:1px solid var(--border); border-radius:16px;
                     padding:14px 14px 6px; margin:16px 0 8px; box-shadow:0 1px 4px rgba(74,43,51,.06); }}

  /* Note callout */
  .note {{ background:var(--card); border:1px solid var(--border); border-left:4px solid var(--accent);
          border-radius:0 14px 14px 0; padding:6px 24px; margin:34px 0; font-size:15.5px;
          box-shadow:0 1px 3px rgba(74,43,51,.05); }}
  .note ul {{ margin:10px 0; padding-left:20px; }} .note li {{ margin:7px 0; }}
  section {{ margin-bottom:26px; }}

  /* Divisor entre secciones top-level (no aplica a la primera) */
  section:not(:first-of-type) {{
    margin-top:80px;
    padding-top:56px;
    border-top:3px solid var(--primary);
  }}
  section:not(:first-of-type) .eyebrow {{ margin-top:0; }}

  /* Inline code */
  code {{ font-family:'JetBrains Mono', ui-monospace, SFMono-Regular, Menlo, monospace;
         font-size:14px; background:var(--bg); padding:1px 6px; border-radius:5px;
         color:var(--primary-2); border:1px solid var(--border); }}

  /* Schema diagram (horizontal flow) */
  .schema {{ display:flex; align-items:stretch; gap:8px; margin:18px 0 8px;
            flex-wrap:wrap; }}
  .schema-step {{ flex:1 1 0; min-width:150px; background:var(--card); border:1px solid var(--border);
                 border-radius:12px; padding:12px 14px; box-shadow:0 1px 3px rgba(74,43,51,.05); }}
  .schema-step-label {{ font-size:10.5px; font-weight:600; letter-spacing:.1em; text-transform:uppercase;
                       color:var(--accent-strong); }}
  .schema-step-name {{ font-family:'JetBrains Mono', ui-monospace, monospace; font-size:13.5px;
                      font-weight:600; color:var(--primary); margin-top:4px; word-break:break-all; }}
  .schema-step-note {{ font-size:12.5px; color:var(--muted); margin-top:6px; }}
  .schema-arrow {{ align-self:center; font-size:20px; color:var(--accent-strong); font-weight:300; }}

  /* Two-column definitions */
  .defs-grid {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(260px,1fr));
               gap:16px; margin:18px 0 12px; }}
  .def-card {{ background:var(--card); border:1px solid var(--border); border-top:4px solid var(--primary);
              border-radius:12px; padding:18px 22px; box-shadow:0 1px 3px rgba(74,43,51,.05); }}
  .def-card:nth-child(2) {{ border-top-color:var(--accent-strong); }}
  .def-card-h {{ font-family:'Playfair Display',serif; font-size:21px; font-weight:600; color:var(--primary); }}
  .def-card:nth-child(2) .def-card-h {{ color:var(--accent-strong); }}
  .def-card-sub {{ font-size:12px; font-weight:600; letter-spacing:.1em; text-transform:uppercase;
                  color:var(--muted); margin-top:2px; }}
  .def-card ul {{ margin:12px 0 0; padding-left:18px; }}
  .def-card li {{ margin:6px 0; font-size:14.5px; }}

  /* Rankings comparison (Q3) */
  .rankings-grid {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(240px,1fr));
                   gap:16px; margin:14px 0 8px; }}
  .rank-col {{ background:var(--card); border:1px solid var(--border); border-top:4px solid var(--primary-2);
              border-radius:12px; padding:14px 18px; box-shadow:0 1px 3px rgba(74,43,51,.05); }}
  .rank-col:nth-child(2) {{ border-top-color:var(--accent-strong); }}
  .rank-col-h {{ font-size:12px; font-weight:600; letter-spacing:.1em; text-transform:uppercase;
                color:var(--muted); margin-bottom:6px; }}
  .rank-col ol {{ margin:0; padding-left:22px; }}
  .rank-col li {{ display:flex; justify-content:space-between; align-items:baseline;
                 padding:4px 0; font-size:15px; }}
  .rank-col li .rk-val {{ font-family:'JetBrains Mono', ui-monospace, monospace;
                          font-size:13.5px; color:var(--muted); }}
  .rank-col li:first-child .rk-val {{ color:var(--primary); font-weight:600; }}
  .rank-section-label {{ font-size:11.5px; font-weight:600; letter-spacing:.12em;
                        text-transform:uppercase; color:var(--muted);
                        margin:18px 0 8px; }}

  /* Audit findings list */
  .audit-list {{ padding-left:22px; margin:8px 0 16px; }}
  .audit-list li {{ margin:10px 0; font-size:15.5px; }}

  /* Disclosable decision card (<details>) */
  .decision {{ margin:10px 0 4px; border:1px solid var(--border); border-radius:8px;
              background:var(--bg); }}
  .decision summary {{ cursor:pointer; padding:8px 14px; font-size:13px; font-weight:600;
                      color:var(--accent-strong); letter-spacing:.02em; user-select:none;
                      list-style:none; transition:color .15s ease; }}
  .decision summary::-webkit-details-marker {{ display:none; }}
  .decision summary::before {{ content:"▸"; display:inline-block; margin-right:7px;
                              font-size:11px; transition:transform .15s ease; }}
  .decision[open] summary::before {{ transform:rotate(90deg); }}
  .decision summary:hover {{ color:var(--primary); }}
  .decision-body {{ padding:6px 16px 12px; font-size:14px; border-top:1px solid var(--border);
                   background:var(--card); border-radius:0 0 8px 8px; }}
  .decision-body p {{ margin:8px 0; }}

  /* ============================================================
     RESPONSIVE — tablets en portrait y móviles
     ============================================================ */
  @media (max-width:720px) {{
    body {{ padding:36px 16px 80px; font-size:15.5px; line-height:1.6; }}
    header {{ padding-bottom:16px; }}
    header h1 {{ font-size:28px; }}
    header p {{ font-size:14px; }}
    header .byline {{ font-size:12.5px; }}

    h2 {{ font-size:24px; }}
    h3 {{ font-size:19px; margin-top:32px; }}
    p.lead {{ font-size:16.5px; }}
    p {{ margin:12px 0; }}

    /* Divisor entre secciones — menos agresivo en móvil */
    section:not(:first-of-type) {{ margin-top:50px; padding-top:32px; border-top-width:2px; }}

    /* KPIs */
    .kpi-grid {{ gap:10px; margin:20px 0 24px; }}
    .kpi {{ padding:14px 16px; }}
    .kpi-label {{ font-size:10.5px; }}
    .kpi-value {{ font-size:28px; }}
    .kpi-sub {{ font-size:12.5px; }}

    /* Controls (selects de Q1) */
    .controls {{ gap:14px; padding:14px 16px; }}
    .controls label {{ flex:1 1 100%; }}

    /* Chart cards — menos padding para dar espacio al chart */
    .card.chart-card {{ padding:8px 6px 4px; margin:12px 0 6px; }}

    /* Schema diagram — apila vertical y oculta flechas horizontales */
    .schema {{ flex-direction:column; gap:8px; }}
    .schema-step {{ min-width:0; width:100%; padding:10px 14px; }}
    .schema-arrow {{ display:none; }}

    /* Two-column cards: garantiza que colapsen a 1 col cuando hace falta */
    .defs-grid {{ gap:12px; }}
    .def-card {{ padding:14px 16px; }}
    .def-card-h {{ font-size:18px; }}
    .def-card li {{ font-size:13.5px; }}

    .rankings-grid {{ gap:12px; }}
    .rank-col {{ padding:12px 14px; }}
    .rank-col li {{ font-size:14px; }}

    /* Notes y disclosures */
    .note {{ padding:4px 16px; margin:24px 0; font-size:14.5px; }}
    .decision-body {{ padding:6px 14px 10px; font-size:13.5px; }}

    /* Listas de auditoría */
    .audit-list li {{ font-size:14.5px; }}
  }}

  /* Móvil pequeño (iPhone SE y similares) */
  @media (max-width:400px) {{
    body {{ padding:28px 14px 70px; font-size:15px; }}
    header h1 {{ font-size:24px; }}
    h2 {{ font-size:21px; }}
    h3 {{ font-size:17px; }}
    p.lead {{ font-size:15.5px; }}
    .kpi-value {{ font-size:24px; }}
    .eyebrow {{ font-size:11px; letter-spacing:.14em; }}
  }}

  @media (prefers-reduced-motion: reduce) {{ * {{ transition:none !important; animation:none !important; }} }}
</style>
"""


def build():
    con = duckdb.connect(DB, read_only=True)
    body = section_audit(con) + section_q1(con) + section_q2(con) + section_q3(con)
    con.close()

    html = f"""<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>ALOHAS — Reporte de negocio</title>
<script>{get_plotlyjs()}</script>
{CSS}
</head>
<body>
<header>
  <div class="brand">A L O H A S</div>
  <h1>Cómo se mide el negocio</h1>
  <p>Ventas por canal · devoluciones · margen de contribución</p>
  <p class="byline">Reporte preparado por <strong>David Rosales Argüello</strong></p>
</header>
{body}
{JS}
</body>
</html>"""

    with open(OUT, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"Escrito {OUT} ({os.path.getsize(OUT)/1e6:.1f} MB)")


if __name__ == "__main__":
    build()
