#!/bin/bash
export PYTHONPATH=.:agent_missions_api
cd agent_missions_api
uv run --with-requirements ../scripts/test_requirements.txt pytest tests/test_history.py -v -s
