#!/bin/sh

cd "$(dirname "$0")" || exit

if [ -d "venv-jungle" ]; then
    . ./venv-jungle/bin/activate
    pgrep -f 'gunicorn -w 4 app:app' | xargs -r kill
    nohup gunicorn -w 4 app:app > /dev/null 2>&1 &
fi