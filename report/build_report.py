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
    ret = con.execute("""
        select channel, sum(total_unidades_devueltas)*100.0/sum(total_unidades_vendidas) tasa
        from mart_channel_sales_monthly group by 1
    """).fetchdf().set_index("channel")["tasa"]
    n = {c: dict(share=share[c], growth=growth[c], ret=ret[c]) for c in CHANNELS}
    n["_gmin"], n["_gmax"] = growth.min(), growth.max()
    return n


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
      {kpi("Participación Online", f"{n['online']['share']:.0f}%", "de la venta neta total")}
      {kpi("Crecimiento interanual", f"+{n['_gmin']:.0f}–{n['_gmax']:.0f}%", "los cuatro canales, en paralelo", "pos")}
      {kpi("Rotación de mix", "Estable", "sin cambios de reparto (&lt;0,3 pp)")}
      {kpi("Devoluciones", f"{n['online']['ret']:.0f}% vs {n['wholesale']['ret']:.0f}%", "Online frente a Wholesale")}
    </div>"""

    prose_intro = f"""
    <p>El negocio se apoya sobre todo en un canal: <strong>Online concentra el
    {n['online']['share']:.0f}%</strong> de la venta neta. Wholesale y Retail
    aportan algo menos de un quinto cada uno ({n['wholesale']['share']:.0f}% y
    {n['retail']['share']:.0f}%), y Marketplace queda como canal menor
    ({n['marketplace']['share']:.0f}%).</p>

    <p>Todas las cifras de esta sección son <strong>venta neta</strong>: ya
    descuentan impuestos y devoluciones. Comparar la venta bruta entre canales
    engaña, porque Wholesale no lleva impuestos y Online absorbe la mayoría de las
    devoluciones — mezclar esas dos cosas haría parecer a unos canales mejores de
    lo que son.</p>
    """

    prose_trend = """
    <p>La tendencia confirma un negocio en crecimiento, con el pico estacional de
    noviembre–diciembre repitiéndose los dos años. Las proporciones entre canales
    se mantienen estables a lo largo del tiempo: no se ve un canal comiéndole
    terreno a otro, sino los cuatro creciendo en paralelo.</p>
    """

    prose_mix = """
    <p>Visto como participación del total acumulado de los dos años, Online supera
    por sí solo la mitad de la venta neta y los demás canales se reparten el resto.
    Y como vimos en la tendencia, este reparto es estable en el tiempo: el
    crecimiento no depende de un cambio de mix arriesgado, viene de que <em>todo</em>
    el negocio crece a la vez.</p>
    """

    prose_growth = f"""
    <p>Y eso es justo lo que muestra el crecimiento interanual: los cuatro canales
    crecen en una banda estrecha, entre <strong>+{n['_gmin']:.0f}% y
    +{n['_gmax']:.0f}%</strong>. Online es marginalmente el que más acelera
    (+{n['online']['growth']:.1f}%), pero la diferencia con el resto es pequeña.
    La lectura honesta no es "tal canal se está disparando", sino "<strong>el motor
    de crecimiento es ancho y sano</strong>", sin un único punto de dependencia ni
    una fuga evidente.</p>
    """

    prose_lens = """
    <div class="note">
      <p><strong>Dos formas de leer estas cifras — elige arriba la perspectiva.</strong>
      La única diferencia entre ambas es <em>cuándo</em> se cuenta una devolución, y
      eso cambia a qué mes se le resta:</p>
      <ul>
        <li><strong>CEO (visión financiera):</strong> la devolución se registra el día
        en que ocurre. Un mes ya cerrado no se vuelve a tocar — es la lectura correcta
        para resultados financieros.</li>
        <li><strong>Head of Wholesale (visión por cohorte):</strong> la devolución se
        descuenta del mes en que se hizo la venta original. Sirve para responder "¿de
        qué meses salieron los productos que luego se devolvieron?", útil para evaluar
        la calidad de cada campaña de ventas.</li>
      </ul>
      <p>En Wholesale las dos vistas son casi idénticas (apenas hay devoluciones);
      en Online es donde más se separan.</p>
    </div>
    """

    controls = """
      <div class="controls">
        <label>Perspectiva
          <span class="select-wrap">
            <select id="q1_perspective" onchange="q1Update()">
              <option value="ceo">CEO — visión financiera (devolución el día que ocurre)</option>
              <option value="wh">Head of Wholesale — por cohorte (devolución el día de la compra)</option>
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
                    text-transform:uppercase; display:flex; flex-direction:column; gap:7px; }}
  .select-wrap {{ position:relative; display:inline-block; }}
  .select-wrap::after {{ content:""; position:absolute; right:14px; top:50%; width:8px; height:8px;
                        border-right:2px solid var(--primary-2); border-bottom:2px solid var(--primary-2);
                        transform:translateY(-70%) rotate(45deg); pointer-events:none; }}
  .controls select {{ font-family:Inter,sans-serif; font-size:14px; font-weight:500; text-transform:none;
                     letter-spacing:0; padding:9px 38px 9px 13px; border:1.5px solid var(--border);
                     border-radius:9px; background:var(--bg); color:var(--ink); min-width:290px;
                     cursor:pointer; appearance:none; -webkit-appearance:none;
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

  @media (max-width:560px) {{
    body {{ padding:36px 16px 80px; }} header h1 {{ font-size:32px; }}
    .controls select {{ min-width:100%; }}
  }}
  @media (prefers-reduced-motion: reduce) {{ * {{ transition:none !important; animation:none !important; }} }}
</style>
"""


def build():
    con = duckdb.connect(DB, read_only=True)
    body = section_q1(con)
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
