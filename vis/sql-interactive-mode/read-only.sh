#!/bin/sh
scriptdir=$(dirname "$(readlink -f "$0")")
vis_path="$scriptdir/../../vis.py"
exec "$vis_path" "$(basename "$scriptdir")" "$@" \
    --path '^(sql-mode/|sql-interactive-mode/[^/]*$)' --group '^$'
