#!/bin/bash
# ══════════════════════════════════════════════════════════════
# Anagram Quest — DigitalOcean Droplet Setup Script
# Run as root on a fresh Ubuntu 22.04 $10/month droplet
# ══════════════════════════════════════════════════════════════

set -e
export DEBIAN_FRONTEND=noninteractive

echo "═══ 1. System Update ═══"
apt update && apt upgrade -y -o Dpkg::Options::="--force-confold"
apt install -y python3 python3-venv python3-pip nginx certbot python3-certbot-nginx git ufw

echo "═══ 2. Firewall ═══"
ufw allow OpenSSH
ufw allow 'Nginx Full'
ufw --force enable

echo "═══ 3. Clone Repository ═══"
mkdir -p /opt/anagram-quest
cd /opt/anagram-quest
git clone https://github.com/divyanshailani/anagram-quest-server.git .

echo "═══ 4. Python Virtual Environment ═══"
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

echo "═══ 5. Create systemd Service ═══"
cat > /etc/systemd/system/anagram-quest.service << 'EOF'
[Unit]
Description=Anagram Quest Game Master
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=/opt/anagram-quest
ExecStart=/opt/anagram-quest/venv/bin/uvicorn main:app --host 127.0.0.1 --port 8000 --workers 2
Restart=always
RestartSec=5
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable anagram-quest
systemctl start anagram-quest

echo "═══ 6. Nginx Reverse Proxy ═══"
cat > /etc/nginx/sites-available/anagram-quest << 'EOF'
server {
    listen 80;
    server_name _;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        # SSE-specific settings
        proxy_set_header Connection '';
        proxy_buffering off;
        proxy_cache off;
        proxy_read_timeout 300s;
        chunked_transfer_encoding off;
    }
}
EOF

ln -sf /etc/nginx/sites-available/anagram-quest /etc/nginx/sites-enabled/
rm -f /etc/nginx/sites-enabled/default
nginx -t && systemctl restart nginx

echo ""
echo "═══ ✅ DEPLOYMENT COMPLETE ═══"
echo "Game Master running at: http://$(curl -s ifconfig.me):80"
echo ""
echo "Next steps:"
echo "  1. Point a domain/subdomain to this IP"
echo "  2. Run: certbot --nginx -d yourdomain.com"
echo "  3. Update Vercel env: NEXT_PUBLIC_GAME_SERVER=https://yourdomain.com"
