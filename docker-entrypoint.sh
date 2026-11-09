#!/bin/sh
set -e
case "$ROLE" in
  api)  exec uvicorn api.main:app --host 0.0.0.0 --port "$PORT" ;;
  web)  exec streamlit run web/app.py --server.port "$PORT" --server.address 0.0.0.0 \
          --server.headless true --browser.gatherUsageStats false ;;
  eval) exec python -m eval.run_eval "$@" ;;
  *)    exec "$@" ;;
esac
