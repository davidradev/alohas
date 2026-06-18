-- Regla de negocio: las ventas wholesale no llevan impuestos.
-- El test falla si alguna línea wholesale tiene taxes > 0.
select *
from {{ ref('stg_sales') }}
where channel = 'wholesale'
  and taxes_eur > 0
