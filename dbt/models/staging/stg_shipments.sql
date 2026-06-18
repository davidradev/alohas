with source as (
    select * from {{ source('production', 'fct_shipment') }}
),

renamed as (
    select
        shipment_id,
        shipping_method,
        cast(shipping_cost as double) as shipping_cost_eur,
        country as destination_country_code
    from source
)

select * from renamed
