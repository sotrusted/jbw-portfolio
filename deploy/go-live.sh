#!/usr/bin/env bash
# Run from your own terminal on the Mac:   ~/jbw-portfolio/deploy/go-live.sh
# Opens an SSH session to the server and runs the installer with sudo (it will ask for the
# server password). Safe to re-run.
exec ssh -t 23.94.179.21 'sudo bash ~/jbw-portfolio/deploy/install.sh'
