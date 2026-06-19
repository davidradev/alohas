{#
  Prorratea el coste de cada envío entre las líneas de venta que lo componen,
  proporcionalmente a la venta bruta de cada línea dentro del envío.
  Granularidad: una fila por línea de venta CON envío existente.

  Aislar esto del mart de margen lo mantiene legible (capas, no una query gigante)
  y deja el prorrateo testeable y reutilizable. El inner join con envíos filtra
  aquí las líneas sin envío, porque sin coste de envío no hay margen que calcular.
#}

with sales as (
    select * from {{ ref('stg_sales') }}
),

shipments as (
    select * from {{ ref('stg_shipments') }}
),

-- Total de venta bruta por envío, base del reparto
sales_with_totals as (
    select
        s.*,
        sum(s.gross_sale_eur) over (partition by s.shipment_id) as shipment_total_gross_sale_eur
    from sales s
)

select
    s.sale_line_id,
    s.channel,
    s.product_id,
    s.shipment_id,
    s.quantity_sold,
    s.quantity_returned,
    s.gross_sale_eur,
    s.net_sales_eur,
    sh.shipping_cost_eur,

    -- Coste de envío asignado según la participación de la línea en la venta bruta del envío
    case
        when s.shipment_total_gross_sale_eur > 0
        then (s.gross_sale_eur / s.shipment_total_gross_sale_eur) * sh.shipping_cost_eur
        else 0
    end as allocated_shipping_cost_eur

from sales_with_totals s
inner join shipments sh on s.shipment_id = sh.shipment_id
