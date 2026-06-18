{#
  Genera una clave sustituta (hash) estable a partir de una lista de campos.
  Equivalente ligero a dbt_utils.generate_surrogate_key, sin añadir el paquete.
  Cross-engine: md5 en DuckDB (devuelve hex), to_hex(md5()) en BigQuery (devuelve BYTES).
#}
{% macro generate_surrogate_key(fields) %}
{%- set concat_expr -%}
{%- for f in fields -%}
coalesce(cast({{ f }} as {{ dbt.type_string() }}), '_null_')
{%- if not loop.last %} || '|' || {% endif -%}
{%- endfor -%}
{%- endset -%}
{%- if target.type == 'bigquery' -%}
to_hex(md5({{ concat_expr }}))
{%- else -%}
md5({{ concat_expr }})
{%- endif -%}
{% endmacro %}
