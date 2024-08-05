#!/bin/sh

pgrep -f 'gunicorn -w 4 app:app' | xargs -r kill