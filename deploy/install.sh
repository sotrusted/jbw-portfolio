#!/usr/bin/env bash
# Run once on the server with sudo:   sudo bash ~/jbw-portfolio/deploy/install.sh
# Installs the systemd unit and nginx site. Other sites are untouched; nginx is only reloaded
# if its configuration test passes.
set -o errexit
cd "$(dirname "$0")"

install -m 644 jbw.service /etc/systemd/system/jbw.service
install -m 644 nginx-jbw /etc/nginx/sites-available/jbw
ln -sf /etc/nginx/sites-available/jbw /etc/nginx/sites-enabled/jbw

systemctl daemon-reload
systemctl enable --now jbw.service
nginx -t
systemctl reload nginx
systemctl --no-pager --lines 0 status jbw.service

echo
echo "Installed. Once josephbochettowalsh.com points at this server, get the certificate with:"
echo "  sudo certbot --nginx -d josephbochettowalsh.com -d www.josephbochettowalsh.com"
