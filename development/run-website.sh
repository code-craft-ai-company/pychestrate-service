#!/bin/bash
export PYTHONPATH="$PWD/source/packages:$PWD/source/site:../automojo-webworks/source/packages:../automojo-this-app/source/packages:../automojo-testbase/source/packages:../automojo-configuration/source/packages:../automojo-credentials/source/packages:../automojo-dataprofiles/source/packages:../automojo-errors/source/packages:../pychestrate-core/source/packages:$PYTHONPATH"
python3 source/site/app_pychestrate_main.py
