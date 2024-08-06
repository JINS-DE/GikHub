#!/bin/sh

cd "$(dirname "$0")" || exit

if [ -d "venv-jungle" ]; then
    . ./venv-jungle/bin/activate
    pgrep -f 'gunicorn -k gevent -w 1 app:app' | xargs -r kill
    nohup gunicorn -k gevent -w 1 app:app > /dev/null 2>&1 &
fi