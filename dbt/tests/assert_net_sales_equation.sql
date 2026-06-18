-- Regla de negocio: net_sales = gross_sale - taxes (tolerancia 1 céntimo).
-- El test falla si aparece alguna línea que no cuadra.
select *
from {{ ref('stg_sales') }}
where abs(net_sales_eur - (gross_sale_eur - taxes_eur)) > 0.01
