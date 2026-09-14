#!/bin/sh
set -eu

site_directory=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
exec bunx http-server "$site_directory" -a 0.0.0.0 -p "${1:-8765}" -c-1
