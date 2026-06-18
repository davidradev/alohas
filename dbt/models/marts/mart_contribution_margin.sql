{#
  Margen de contribución por canal y categoría. Grano: una fila por
  (channel, product_category).

  Recibe el coste de envío ya prorrateado desde int_shipping_allocation y solo se
  ocupa de la lógica financiera. Aplica inner join con productos porque sin coste
  de producto no hay margen (filtrado deliberado de huérfanos, ver mart de canal).

  Asunciones de costes de devolución y producto documentadas en el README.
#}

with line_economics as (
    select * from {{ ref('int_shipping_allocation') }}
),

products as (
    select * from {{ ref('stg_products') }}
),

joined as (
    select
        le.channel,
        p.product_category,
        le.quantity_sold,
        le.quantity_returned,
        le.net_sales_eur,
        le.allocated_shipping_cost_eur,
        p.unit_cost_eur
    from line_economics le
    inner join products p on le.product_id = p.product_id
),

calculated as (
    select
        channel,
        product_category,

        -- Volúmenes
        sum(quantity_sold) as total_unidades_vendidas,
        sum(quantity_returned) as total_unidades_devueltas,

        -- Venta Neta Real (después de devoluciones)
        sum(net_sales_eur * (1 - (cast(quantity_returned as double) / quantity_sold))) as total_venta_neta_real_eur,

        -- Costo de Producto Neto (asumiendo que las devoluciones se reincorporan al stock)
        sum((quantity_sold - quantity_returned) * unit_cost_eur) as total_costo_producto_neto_eur,

        -- Costo de Envíos Prorrateado
        sum(allocated_shipping_cost_eur) as total_costo_envio_eur,

        -- Costo de Devoluciones (Asunción: 8.00 EUR por unidad devuelta, logística inversa)
        sum(quantity_returned * 8.00) as total_costo_retornos_estimado_eur
    from joined
    group by 1, 2
)

select
    channel,
    product_category,
    total_unidades_vendidas,
    total_unidades_devueltas,

    round(total_venta_neta_real_eur, 2) as venta_neta_real_eur,
    round(total_costo_producto_neto_eur, 2) as costo_producto_neto_eur,
    round(total_costo_envio_eur, 2) as costo_envio_eur,
    round(total_costo_retornos_estimado_eur, 2) as costo_retornos_estimado_eur,

    -- Margen de Contribución = Venta Neta Real - Costos Directos
    round(
        total_venta_neta_real_eur
        - total_costo_producto_neto_eur
        - total_costo_envio_eur
        - total_costo_retornos_estimado_eur,
        2
    ) as margen_contribucion_eur,

    -- Porcentaje de Margen de Contribución
    round(
        (total_venta_neta_real_eur
        - total_costo_producto_neto_eur
        - total_costo_envio_eur
        - total_costo_retornos_estimado_eur)
        / total_venta_neta_real_eur,
        4
    ) as porcentaje_margen_contribucion
from calculated
order by margen_contribucion_eur desc
