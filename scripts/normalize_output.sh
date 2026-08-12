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
  -e 's/\[generated in [0-9.]+s]/[generated in {{TIME}}s]/g' \
  -e "s/ \(errno=-?[0-9]+, description='[^']*', sqlstate='[^']*'\)//g"
