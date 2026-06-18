{#
  Snapshot SCD-2 de las líneas de venta. El problema del caso: quantity_returned
  se actualiza IN-PLACE cuando llega la devolución (30-90 días después), sin
  insertar fila nueva. Una métrica construida sobre la tabla cruda "miente"
  retroactivamente.

  La estrategia `check` sobre quantity_returned hace que, cada vez que se ejecute
  `dbt snapshot`, si ese valor cambió para una línea, dbt cierre la versión
  anterior (dbt_valid_to) y abra una nueva (dbt_valid_from). Ese dbt_valid_from
  es, en la práctica, la FECHA EN QUE DETECTAMOS LA DEVOLUCIÓN — justo el dato
  que la tabla cruda no guarda. fct_return se construye a partir de aquí.
#}
{% snapshot snap_sale_order_line %}
{{
  config(
    unique_key='sale_line_id',
    strategy='check',
    check_cols=['quantity_returned'],
    target_schema='snapshots'
  )
}}

select
    sale_line_id,
    channel,
    product_id,
    shipment_id,
    quantity_sold,
    quantity_returned,
    net_sales_eur,
    created_at
from {{ ref('stg_sales') }}

{% endsnapshot %}
