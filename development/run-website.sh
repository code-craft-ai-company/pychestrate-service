#!/bin/bash
export PYTHONPATH="$PWD/source/packages:$PWD/source/site:../codecraftai-webworks/source/packages:../codecraftai-this-app/source/packages:../codecraftai-testbase/source/packages:../codecraftai-configuration/source/packages:../codecraftai-credentials/source/packages:../codecraftai-dataprofiles/source/packages:../codecraftai-errors/source/packages:../pychestrate-core/source/packages:$PYTHONPATH"
python3 source/site/app_pychestrate_main.py
