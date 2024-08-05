#!/bin/sh

ssh jungle-entrance-exam -- 'cd ~/git/jungle-entrance-exam && git clean -fd && git fetch && git reset --hard origin/master && ./run.sh'