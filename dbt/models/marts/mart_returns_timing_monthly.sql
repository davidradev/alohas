{#
  El corazón de la Pregunta 2: muestra las DOS definiciones defendibles de net
  sales lado a lado, por mes y canal.

  - net_sales_asof_sale:   la devolución resta en el MES DE LA VENTA original.
                           Mide la calidad real de la cohorte vendida, pero
                           RESTATA el pasado: el número de un mes sigue bajando
                           durante 90 días mientras llegan sus devoluciones.
  - net_sales_asof_report: la devolución resta en el MES EN QUE OCURRE.
                           Una vez cerrado un mes, no se vuelve a tocar — es la
                           definición contable/financiera que no reescribe el
                           histórico.

  Con fct_return (un evento con sale_date y return_date) las dos definiciones
  son un simple group by por una columna de fecha distinta.
#}

with sales as (
    select * from {{ ref('stg_sales') }}
),

returns as (
    select * from {{ ref('fct_return') }}
),

-- Venta neta PRE-devolución, atribuida al mes de la venta
gross_by_sale_month as (
    select
        date_trunc('month', created_at) as month,
        channel,
        sum(net_sales_eur) as gross_net_sales_eur
    from sales
    group by 1, 2
),

-- Devoluciones atribuidas al MES DE LA VENTA original
returns_by_sale_month as (
    select
        date_trunc('month', sale_date) as month,
        channel,
        sum(return_value_eur) as returns_eur
    from returns
    group by 1, 2
),

-- Devoluciones atribuidas al MES EN QUE OCURRE LA DEVOLUCIÓN
returns_by_return_month as (
    select
        date_trunc('month', return_date_est) as month,
        channel,
        sum(return_value_eur) as returns_eur
    from returns
    group by 1, 2
),

-- Spine de meses×canal: incluye meses futuros que solo tienen devoluciones
-- (ventas que ya pararon pero cuyos retornos siguen llegando).
spine as (
    select month, channel from gross_by_sale_month
    union
    select month, channel from returns_by_return_month
)

select
    sp.month,
    sp.channel,
    round(coalesce(g.gross_net_sales_eur, 0), 2) as venta_neta_pre_devolucion_eur,
    round(coalesce(rs.returns_eur, 0), 2) as devoluciones_por_mes_venta_eur,
    round(coalesce(rr.returns_eur, 0), 2) as devoluciones_por_mes_devolucion_eur,

    -- Definición 1: as-of date of sale (restata el pasado)
    round(coalesce(g.gross_net_sales_eur, 0) - coalesce(rs.returns_eur, 0), 2) as net_sales_asof_sale_eur,

    -- Definición 2: as-of report date (no reescribe meses cerrados)
    round(coalesce(g.gross_net_sales_eur, 0) - coalesce(rr.returns_eur, 0), 2) as net_sales_asof_report_eur

from spine sp
left join gross_by_sale_month   g  on sp.month = g.month  and sp.channel = g.channel
left join returns_by_sale_month rs on sp.month = rs.month and sp.channel = rs.channel
left join returns_by_return_month rr on sp.month = rr.month and sp.channel = rr.channel
order by sp.month, sp.channel
