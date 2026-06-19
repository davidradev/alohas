# ALOHAS — Analytics Engineer Study Case

Análisis de ventas por canal, net sales con devoluciones tardías y margen de
contribución para ALOHAS. El corazón del proyecto es una capa **dbt** (staging →
intermediate → marts) con tests, y un reporte en notebook que lee de esos marts.

---

## Cómo navegar el repo

```
.
├── data/                     CSVs sintéticos (extracto del dataset de BigQuery)
├── dbt/                      Proyecto dbt (el núcleo del caso)
│   ├── models/
│   │   ├── staging/          Limpieza + renombrado + sources + tests de origen
│   │   ├── intermediate/     int_shipping_allocation (prorrateo de envío)
│   │   └── marts/            Tablas finales que responden las 3 preguntas
│   ├── snapshots/            snap_sale_order_line (captura el dato mutable)
│   ├── tests/                Tests singulares (reglas de negocio)
│   └── macros/               generate_surrogate_key
├── notebooks/
│   ├── run_sql.ipynb         Auditoría de calidad de datos (working pre-modelado)
│   └── eda_and_insights.ipynb  Notebook exploratorio (queda como working — el reporte ya no se genera desde aquí)
├── report/
│   ├── build_report.py       Script Python: lee de los marts y arma el HTML
│   └── aloha_report.html     Reporte interactivo (abrir en navegador) ← EMPEZAR AQUÍ
└── analytics-engineer-case.pdf  El brief original
```

### Por dónde empezar a leer
1. **`report/aloha_report.html`** — las conclusiones, en el navegador. Empieza con la sección de auditoría ("Antes de empezar") y sigue con las tres preguntas.
2. **`dbt/models/`** — el modelado. Mirar primero `staging/_sources.yml` y `staging/_staging.yml` (grano + tests), luego los marts.
3. **`notebooks/run_sql.ipynb`** — la auditoría de datos previa al modelado (la versión narrada vive en el HTML).

---

## Cómo reproducirlo

Requiere Python 3.12. dbt corre sobre **DuckDB** leyendo los CSV de `data/` (dev);
el mismo proyecto apunta a **BigQuery** en el target `prod`.

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install dbt-duckdb dbt-bigquery duckdb pandas plotly jupysql

# IMPORTANTE: dbt se ejecuta desde la RAÍZ del repo (las rutas a data/ y a la
# BD son relativas a la raíz).
dbt build --project-dir dbt --profiles-dir dbt

# Regenerar el reporte HTML (lee de los marts en alohas.db y escribe
# report/aloha_report.html, autocontenido — Plotly embebido, abre offline):
python3 report/build_report.py
```

`jupysql` solo lo necesitas si vas a re-ejecutar `notebooks/run_sql.ipynb`. Para
generar el reporte basta con `plotly` + `duckdb` + `pandas`.

`alohas.db` (la BD DuckDB) y `dbt/target/` están en `.gitignore` porque son
artefactos de build: se recrean con `dbt build`.

---

## Arquitectura dbt

```
source ─┬─ stg_products ───────────────────────────────────┐
        ├─ stg_shipments ─┐                                 │
        └─ stg_sales ─┬───┴─ int_shipping_allocation ───────┼─ mart_contribution_margin
                      │                                     │ (+ productos)
                      ├─ mart_channel_sales_monthly         │
                      │
                      └─ snap_sale_order_line ─ fct_return ─┬─ mart_returns_timing_monthly
                                                            └─ mart_sales_and_returns_cohort
```

Tests: `unique` / `not_null` / `relationships` / `accepted_values` en el esquema,
más 5 tests singulares con las reglas de negocio (`net = gross - taxes`, wholesale
sin impuestos, devoluciones ≤ ventas, etc.). `dbt build` corre 40 nodos.

---

## Decisiones de modelado y supuestos

**Grano.** Cada modelo declara su grano en su descripción (`_sources.yml`,
`_staging.yml`, `_marts.yml`). La tabla cruda de ventas no trae PK, así que en
staging construyo una clave sustituta estable (`sale_line_id`) hasheando los
campos **inmutables** de la línea — excluyo `quantity_returned` justamente porque
es el que cambia.

**Líneas huérfanas (decisión por pregunta, no global).** Hay ~750 líneas con un
`sku` sin match en el catálogo (~203k€ de venta bruta) y ~500 sin envío. No las
trato igual en todos lados:
- En **ventas por canal** las **conservo**: para medir un canal solo necesito
  canal + fecha + importe, y las huérfanas los tienen. Excluirlas escondía ~230k€
  de net sales reales y rompía el "comparar like-for-like".
- En **margen de contribución** las **descarto** (inner join): sin coste de
  producto/envío no hay margen que calcular.
Los tests `relationships` dejan los huérfanos documentados como `warn` (problema
de datos conocido, no bloqueante).

**Multi-país sin moneda (gap de modelado).** El negocio envía a 8 países (ES, FR,
DE, US, IT, UK, PT, MX) pero ninguna tabla trae `currency_code` ni `fx_rate`.
Todo viene pre-convertido a EUR aguas arriba. Hoy es imposible auditar el tipo
de cambio aplicado ni separar pérdida cambiaria del margen real. El reporte lo
flagea explícitamente en la sección de auditoría.

**Devoluciones tardías (Pregunta 2).** `quantity_returned` es mutable: se
reescribe sobre la línea original cuando llega la devolución (30-90 días después).
Mi diseño:
- Un **snapshot** (`snap_sale_order_line`, estrategia `check` sobre
  `quantity_returned`) captura cada cambio con su `dbt_valid_from`. En producción,
  ese timestamp ES la fecha real de la devolución.
- `fct_return` convierte ese dato mutable en una **tabla de eventos** (un row por
  devolución, con `sale_date` y `return_date`).
- `mart_returns_timing_monthly` materializa las **dos definiciones**:
  - *net sales as-of date of sale*: la devolución resta en el mes de la venta.
    Mide calidad de cohorte, pero **reescribe el pasado**.
  - *net sales as-of report date*: la devolución resta en el mes en que ocurre.
    No toca meses cerrados → es la definición **contable** que defiendo para
    reporting financiero.

  *Supuesto:* el dataset no trae fecha de devolución, así que estimo el punto
  medio de la ventana (venta + 60 días). En producción se reemplaza por el
  `dbt_valid_from` del snapshot. En este CSV sintético `quantity_returned` ya
  viene en su valor final, así que lo que el modelo demuestra es la **mecánica**
  y la **diferencia de atribución temporal**, no la maduración real.

**Margen de contribución (Pregunta 3).** Margen = venta neta real − coste de
producto neto − envío prorrateado − coste de devolución. Supuestos:
- *Envío:* lo prorrateo entre las líneas de un mismo envío según su % de venta
  bruta dentro del envío. **Decisión opinable** — sin `weight_kg` en el catálogo
  no se puede repartir por peso (lo correcto). El reporte muestra esta decisión
  en un disclosure colapsable junto al supuesto.
- *Devoluciones / producto:* asumo que la unidad devuelta **se reincorpora al
  stock** (no pierdo su coste de producto, solo descuento las unidades netas).
- *Coste de devolución:* **8,00€ por unidad devuelta** (recibir, inspeccionar,
  re-empacar). Es el supuesto más opinable: a 15€/u, Online baja ~1 pp;
  Wholesale apenas se mueve (devuelve solo el 4%).

---

## Hallazgos de calidad de datos

De `run_sql.ipynb` (y surfaceado en la sección de auditoría del HTML):
- **Claves primarias:** 100% limpias (sin duplicados en `sku` ni `shipment_id`).
- **Integridad referencial:** 750 ventas sin producto y 500 sin envío. Las 750
  sin producto se concentran en Online (435) y suman ~203k€ de venta bruta.
- **Consistencia financiera:** perfecta — `gross = base_price × qty`, `net = gross
  − taxes`, wholesale con impuestos en 0.
- **Límites físicos:** sin negativos, sin devoluciones > ventas.
- **Precios atípicos (IQR):** los precios altos son artículos premium reales
  (~400-550€), no errores de escala. El catálogo está sano.
- **Multi-país sin `currency_code` ni `fx_rate`:** 8 países distintos, todo
  pre-convertido a EUR. Es un gap de **modelado**, no de datos — pero limita lo
  que se puede auditar sobre el tipo de cambio.

---

## Las tres preguntas, en corto

0. **Auditoría primero.** 1.250 líneas con FK rota (~325k€ de venta bruta) que
   conservo en Q1 y excluyo en Q3. 8 países sin columna de moneda — gap de
   modelado dejado flageado en el reporte y en este README.
1. **Canal.** Online concentra el 56% de la venta neta (5,1M€ de 9,1M€) con
   crecimiento de +18% interanual. Los cuatro canales crecen en banda estrecha:
   motor ancho, no dependencia de uno solo. El reporte expone toggle CEO /
   cohorte para mostrar cuándo cuenta la devolución.
2. **Net sales con devoluciones tardías.** Snapshot SCD-2 → `fct_return`
   (eventos con `sale_date` + `return_date`) → mart con las dos métricas lado a
   lado. Defiendo *as-of report date* para reporting financiero (no reescribe el
   pasado) y *as-of date of sale* para análisis de cohorte.
3. **Margen de contribución.** Online aporta más margen absoluto (2,1M€) pero
   Wholesale gana en eficiencia (55,5% vs 42,6%). El ranking se da la vuelta
   también en categorías: Bags cae del 3º al 5º al pasar de venta a margen %;
   Shoes salta al 1º.

---

## Qué haría con más tiempo

- **Catálogo enriquecido:** añadir `weight_kg` y `currency_code` a `dim_product`
  y al grano de venta. Son los dos gaps que más limitan la fidelidad del cálculo
  de margen y el análisis multi-país.
- **Snapshots con historia real:** correr el snapshot sobre varios cortes para
  que `fct_return` use fechas de devolución reales en vez del supuesto de +60 días.
- **Sensibilidad del coste de devolución:** sacar el 8,00€ a una variable de
  `dbt` (`vars:`) y exponer un slider en el reporte para ver el rango de margen
  por canal/categoría en tiempo real.
- **Investigar los SKU huérfanos:** ¿son catálogo incompleto (problema de
  modelado) o basura (problema de datos)? Hoy solo los aíslo.
- **Exposures de dbt + CI** que corra `dbt build` en cada push.
