{#
  Ventas por canal y mes. Granularidad: una fila por (sales_month, channel).

  DECISIÓN DE MODELADO: aquí NO filtramos las líneas huérfanas. Para medir el
  desempeño de un canal solo necesitamos canal + fecha + importe, y las ~1.250
  líneas sin producto/envío sí tienen esos tres datos. Excluirlas (como hacía la
  versión inicial con inner join) sesgaba ~270k€ de ventas reales y rompía el
  "comparar like-for-like" que pide el brief. El filtro de integridad referencial
  solo se aplica donde de verdad hace falta el coste (margen de contribución).
#}

with sales as (
    select * from {{ ref('stg_sales') }}
),

monthly as (
    select
        date_trunc('month', created_at) as sales_month,
        channel,
        count(*) as total_lineas_vendidas,
        sum(quantity_sold) as total_unidades_vendidas,
        sum(quantity_returned) as total_unidades_devueltas,
        sum(gross_sale_eur) as venta_bruta_eur,
        sum(taxes_eur) as impuestos_eur,
        sum(net_sales_eur) as venta_neta_pre_devolucion_eur,
        -- Venta Neta Real (restando la proporción de productos devueltos)
        sum(net_sales_eur * (1 - (cast(quantity_returned as double) / quantity_sold))) as venta_neta_real_eur
    from sales
    group by sales_month, channel
)

select
    sales_month,
    channel,
    total_lineas_vendidas,
    total_unidades_vendidas,
    total_unidades_devueltas,
    round(cast(total_unidades_devueltas as double) / total_unidades_vendidas, 4) as tasa_devolucion,
    round(venta_bruta_eur, 2) as venta_bruta_eur,
    round(impuestos_eur, 2) as impuestos_eur,
    round(venta_neta_pre_devolucion_eur, 2) as venta_neta_pre_devolucion_eur,
    round(venta_neta_real_eur, 2) as venta_neta_real_eur
from monthly
order by sales_month desc, channel
