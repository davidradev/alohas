-- Consistencia: gross_sale debe ser base_price (catálogo) * quantity_sold.
-- Solo evaluable en líneas con producto existente (las huérfanas se cubren
-- con el test relationships). El test falla si la cifra no cuadra.
select s.*
from {{ ref('stg_sales') }} s
join {{ ref('stg_products') }} p
  on s.product_id = p.product_id
where abs(s.gross_sale_eur - (s.quantity_sold * p.base_price_eur)) > 0.01
