with source as (
    select * from {{ source('production', 'dim_product') }}
),

renamed as (
    select
        sku as product_id,
        name as product_name,
        category as product_category,
        cast(base_price as double) as base_price_eur,
        cast(cost as double) as unit_cost_eur
    from source
)

select * from renamed
