with sales as (
    select * from {{ ref('stg_sales') }}
),

products as (
    select * from {{ ref('stg_products') }}
),

shipments as (
    select * from {{ ref('stg_shipments') }}
),

joined as (
    -- Usamos inner join para limpiar datos corruptos y asegurar consistencia
    select
        s.channel,
        s.quantity_sold,
        s.quantity_returned,
        s.gross_sale_eur,
        s.net_sales_eur,
        s.created_at
    from sales s
    inner join products p on s.product_id = p.product_id
    inner join shipments sh on s.shipment_id = sh.shipment_id
),

cohorts as (
    select
        date_trunc('month', created_at) as cohorte_mes_venta,
        channel,
        sum(quantity_sold) as total_unidades_vendidas,
        sum(quantity_returned) as total_unidades_devueltas,
        -- Venta neta de la cohorte acumulada (métrica "as-of date of sale")
        sum(net_sales_eur * (1 - (cast(quantity_returned as double) / quantity_sold))) as venta_neta_cohorte_eur
    from joined
    group by 1, 2
)

select
    cohorte_mes_venta,
    channel,
    total_unidades_vendidas,
    total_unidades_devueltas,
    round(cast(total_unidades_devueltas as double) / total_unidades_vendidas, 4) as tasa_devolucion_cohorte,
    round(venta_neta_cohorte_eur, 2) as venta_neta_cohorte_eur
from cohorts
order by cohorte_mes_venta desc, channel
