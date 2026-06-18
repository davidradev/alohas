-- Límite físico: cantidades vendidas y venta bruta no pueden ser <= 0 / negativas.
select *
from {{ ref('stg_sales') }}
where quantity_sold <= 0
   or gross_sale_eur < 0
