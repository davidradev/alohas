{#
  Tabla de eventos de devolución. Grano: una fila por línea de venta con
  devoluciones. Convierte el quantity_returned mutable (atado a la línea de
  venta) en un EVENTO con su propia fecha, que es lo que permite calcular net
  sales bajo cualquiera de las dos definiciones (as-of sale / as-of report).

  Fuente: el snapshot, no la tabla cruda. En producción, la fecha del evento
  sería dbt_valid_from de la versión donde quantity_returned aumentó.
#}

with snapshot_history as (
    select * from {{ ref('snap_sale_order_line') }}
),

-- Versión vigente de cada línea (quantity_returned acumulado a hoy)
current_state as (
    select *
    from snapshot_history
    where dbt_valid_to is null
),

returns as (
    select
        sale_line_id,
        channel,
        product_id,
        cast(created_at as date) as sale_date,
        quantity_returned as units_returned,

        -- Valor reembolsado: neto por unidad * unidades devueltas
        round((net_sales_eur / nullif(quantity_sold, 0)) * quantity_returned, 2) as return_value_eur,

        -- ASUNCIÓN: el dataset no trae fecha real de devolución. Estimamos el
        -- punto medio de la ventana 30-90 días (=60). En producción, esto se
        -- reemplazaría por dbt_valid_from del snapshot (fecha real de detección).
        cast({{ dbt.dateadd('day', 60, 'created_at') }} as date) as return_date_est

    from current_state
    where quantity_returned > 0
)

select * from returns
