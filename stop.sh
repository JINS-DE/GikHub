#!/bin/sh

pgrep -f 'gunicorn -k gevent -w 1 app:app' | xargs -r kill