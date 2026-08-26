#!/usr/bin/env bash
# Normalize dynamic values in example output for reproducible comparison.
# Usage: normalize_output.sh < actual_output > normalized_output
# Compatible with both GNU sed and BSD sed (macOS).

# Filter out SQLAlchemy cache warnings (stderr leaks)
grep -v '^/.*SAWarning' | \
grep -v '^\s*session\.execute' | \
grep -v '^\s*conn\.execute' | \
grep -v 'sqlalche\.me' | \
grep -v 'inherit_cache' | \
grep -v 'SQL compilation caching' | \
grep -v 'performance implications' | \
grep -v 'set the .inherit_cache' | \
grep -v 'this attribute may be set' | \
# Presentation-only rules (below) scrub inherently dynamic, non-semantic values
# so more examples can be golden-captured. Guardrail: only scrub run-to-run
# noise -- never normalize values that prove behavior (SQL text, row contents,
# exception class, transaction outcome, ordering). New rules added for:
#   - wall-clock timings:      "... in 1.234 seconds" -> "... in {{TIME}}s"
#   - absolute export paths:   "exported to: /abs/dir/file.csv" -> "{{PATH}}/file.csv"
#   - tracemalloc peak memory: "peak_memory=  123.4 KB" -> "peak_memory={{MEM}} KB"
#   - derived memory ratio:    "(largest / smallest): 12.3x" -> "...: {{RATIO}}x"
#   - datetime w/ microseconds: "{{DATE}} 11:03:13.052000" -> "{{DATETIME}}"
#   - bulk-insert perf summary:  "execute(insert, rows): 0.06s" -> "...: {{TIME}}s"
#   - pandas string-dtype spelling: pandas 2.2 renders SQL string columns as
#     "object"; newer pandas (PDEP-14 default) renders them as "str". The lesson
#     under test is table loading, not pandas' dtype spelling. The dtype spelling
#     also shifts the .dtypes Series column alignment (widest value "object"(6)
#     vs "str"(3)), so ALL of 01_read_sql's known dtype lines are canonicalized to
#     a single space and string columns are mapped to "object" (column-anchored,
#     not global, so other examples' dtypes output is untouched).
sed -E \
  -e 's/CUBRID version: [0-9.]+/CUBRID version: {{VERSION}}/g' \
  -e 's/^(Version:[[:space:]]+)[0-9.]+/\1{{VERSION}}/g' \
  -e 's/DBA@[a-zA-Z0-9_.-]+/DBA@{{HOSTNAME}}/g' \
  -e 's/[0-9]{4}-[0-9]{2}-[0-9]{2}/{{DATE}}/g' \
  -e 's/in [0-9]+\.[0-9]+ms/in {{TIME}}ms/g' \
  -e 's/in [0-9]+\.[0-9]+s]/in {{TIME}}s]/g' \
  -e 's/CLASS_OID: [0-9|]+/CLASS_OID: {{OID}}/g' \
  -e 's/B[+]tree: [0-9|]+/B+tree: {{BTREE}}/g' \
  -e 's/OID: [0-9|]+/OID: {{OID}}/g' \
  -e 's/In line [0-9]+, column [0-9]+/In line {{LINE}}, column {{COL}}/g' \
  -e 's/[0-9]{4}-[0-9]{2}-[0-9]{2} [0-9]{2}:[0-9]{2}:[0-9]{2},[0-9]+/{{TIMESTAMP}}/g' \
  -e 's/[{][{]DATE[}][}] [0-9]{2}:[0-9]{2}:[0-9]{2},[0-9]+/{{TIMESTAMP}}/g' \
  -e 's/[{][{]DATE[}][}]T[0-9]{2}:[0-9]{2}:[0-9]{2}\.[0-9]+/{{DATETIME}}/g' \
  -e 's/[{][{]DATE[}][}] [0-9]{2}:[0-9]{2}:[0-9]{2}\.[0-9]+/{{DATETIME}}/g' \
  -e 's/\[generated in [0-9.]+s]/[generated in {{TIME}}s]/g' \
  -e "s/ \(errno=-?[0-9]+, description='[^']*', sqlstate='[^']*'\)//g" \
  -e 's/in [0-9]+\.[0-9]+ seconds/in {{TIME}}s/g' \
  -e 's/in [0-9]+ seconds/in {{TIME}}s/g' \
  -e 's/(execute\(insert, rows\): )[0-9]+\.[0-9]+s/\1{{TIME}}s/g' \
  -e 's/(add_all: )[0-9]+\.[0-9]+s/\1{{TIME}}s/g' \
  -e 's#(exported to: )/[^[:space:]]*/([^/[:space:]]+)#\1{{PATH}}/\2#g' \
  -e 's/(peak_memory=)[[:space:]]*[0-9]+\.[0-9]+ KB/\1{{MEM}} KB/g' \
  -e 's/^(product_id)[[:space:]]+([A-Za-z0-9_]+(\[[^]]+\])?)$/\1 \2/g' \
  -e 's/^(unit_price_cents)[[:space:]]+([A-Za-z0-9_]+(\[[^]]+\])?)$/\1 \2/g' \
  -e 's/^(is_active)[[:space:]]+([A-Za-z0-9_]+(\[[^]]+\])?)$/\1 \2/g' \
  -e 's/^(product_name)[[:space:]]+(object|str|string(\[[^]]+\])?)$/\1 object/g' \
  -e 's/^(category_name)[[:space:]]+(object|str|string(\[[^]]+\])?)$/\1 object/g' \
  -e 's#(memory ratio \(largest / smallest\): )[0-9]+\.[0-9]+x#\1{{RATIO}}x#g'

# NOTE (Oracle B4, opt-in): generated SERIAL / AUTO_INCREMENT ids are NOT
# normalized by default. In most examples the id value proves behavior (it is
# row content), so scrubbing it would hide real regressions. If a specific
# example prints an id that is genuinely incidental, add a narrowly-anchored
# rule scoped to that example's exact label -- do not add a broad integer rule.
