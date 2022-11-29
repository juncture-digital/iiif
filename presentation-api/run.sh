#/bin/zsh

cd "$(dirname "$0")"
source .venv/bin/activate
uvicorn --reload --port 8088 src.main:app
