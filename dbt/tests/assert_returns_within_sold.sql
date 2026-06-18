-- Límite físico: no se puede devolver más de lo vendido en la línea.
-- El test falla si quantity_returned > quantity_sold.
select *
from {{ ref('stg_sales') }}
where quantity_returned > quantity_sold
