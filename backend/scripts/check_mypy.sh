#!/usr/bin/env bash
# CI gate: type-check core backend modules with mypy.
# Exit code != 0 fails the build.
#
# Coverage:
#   - shared.py
#   - database.py
#   - storage.py
#   - db_models.py
#   - routes/*.py
#
# Legacy monolith (server.py) is intentionally NOT included until extraction
# into routes/ is complete (see PRD.md).

set -euo pipefail

cd "$(dirname "$0")/.."

mypy --config-file mypy.ini \
  shared.py \
  database.py \
  storage.py \
  db_models.py \
  routes/

echo "✓ mypy gate passed"
