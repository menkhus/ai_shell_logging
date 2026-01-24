#!/bin/bash
# launchd_user_jobs.sh - Show non-Apple launchd jobs (your stuff + third-party)
#
# Filters out com.apple.* to see what YOU and third-party apps have registered.
#
# Usage: ./launchd_user_jobs.sh

echo "========================================"
echo "USER & THIRD-PARTY LAUNCHD JOBS"
echo "(excluding com.apple.*)"
echo "========================================"
echo ""
echo "PID	Status	Label"
echo "---	------	-----"
launchctl list | grep -v "^PID" | grep -vi "com\.apple\." | sort -t'	' -k3
echo ""
echo "========================================"
echo "Total: $(launchctl list | grep -vi 'com\.apple\.' | grep -v '^PID' | wc -l | tr -d ' ') jobs"
echo "========================================"
