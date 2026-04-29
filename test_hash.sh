find "cv_api" -type f ! -name "VERSION" ! -name "HASH" ! -path "*/__pycache__/*" ! -path "*/.venv/*" ! -path "*/node_modules/*" ! -path "*/dist/*" -exec shasum {} + | sort | shasum | awk '{print $1}'
