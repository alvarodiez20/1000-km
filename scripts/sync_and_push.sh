#!/usr/bin/env bash
# Sincroniza con Garmin, recalcula el resumen y sube los datos al repositorio.
# Pensado para ejecutarse en tu ordenador (IP residencial) cada pocas horas.
set -euo pipefail
cd "$(dirname "$0")/.."
if [ -f .venv/bin/activate ]; then source .venv/bin/activate; fi

mil sync --dias "${MC_DIAS:-14}"

git add data/activities.json data/profile.json data/summary.json plan 2>/dev/null || true
if git diff --cached --quiet; then
  echo "Sin cambios."
  exit 0
fi
git commit -m "datos: sincronización Garmin $(date +%F)"
git push
