with source as (
    select * from {{ source('production', 'fct_sale_order_line') }}
),

renamed as (
    select
        -- La tabla cruda no tiene PK. Construimos una clave estable a partir de
        -- los campos INMUTABLES de la línea (excluimos quantity_returned, que es
        -- el campo que cambia). Así el snapshot puede seguir cada línea en el tiempo.
        {{ generate_surrogate_key(['channel', 'sku', 'shipment_id', 'quantity_sold', 'gross_sale', 'created_at']) }} as sale_line_id,
        channel,
        sku as product_id,
        shipment_id,
        cast(quantity_sold as integer) as quantity_sold,
        cast(quantity_returned as integer) as quantity_returned,
        cast(gross_sale as double) as gross_sale_eur,
        cast(taxes as double) as taxes_eur,
        cast(net_sales as double) as net_sales_eur,
        cast(created_at as timestamp) as created_at
    from source
)

select * from renamed
