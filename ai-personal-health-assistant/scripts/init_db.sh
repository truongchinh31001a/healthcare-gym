#!/usr/bin/env sh
set -eu
cd "$(dirname "$0")/../apps/api"
python -m alembic upgrade head
