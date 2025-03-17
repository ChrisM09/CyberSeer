#!/bin/sh

# Locate all PIDs of processes running "dynamicbeat run"
PIDS=$(pgrep -f "dynamicbeat run")

if [ -n "$PIDS" ]; then
    echo "Found the following PIDs for 'dynamicbeat run': $PIDS"
    echo "Killing all instances..."
    for PID in $PIDS; do
        echo "Killing process $PID..."
        kill "$PID"
        if [ $? -eq 0 ]; then
            echo "Process $PID successfully killed."
        else
            echo "Failed to kill process $PID. Check permissions or try again."
        fi
    done
else
    echo "No processes found running 'dynamicbeat run'."
fi
