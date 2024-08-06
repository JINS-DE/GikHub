#!/bin/sh

cd "$(dirname "$0")" || exit
export ENVIRONMENT=development
if [ -d "venv-jungle" ]; then
    . ./venv-jungle/bin/activate
    flask --app app run --debug
fi