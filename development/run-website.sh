#!/bin/bash
export PYTHONPATH="$PWD/source/packages:$PWD/source/site:$PYTHONPATH"
poetry run python source/site/app_pychestrate_main.py
