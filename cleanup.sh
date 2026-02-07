#!/bin/bash
pkill -9 -f "python.*bot"
sleep 2
ps aux | grep python | grep -v grep | awk '{print $2}' | xargs kill -9 2>/dev/null || true
sleep 2
echo "All processes killed"
