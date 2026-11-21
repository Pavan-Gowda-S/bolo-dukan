#!/usr/bin/env bash
# Bolo Dukaan: one-command install on a fresh Ubuntu 22.04/24.04 server (Oracle Cloud Always Free works).
#
#   curl -fsSL https://raw.githubusercontent.com/channallikrishnasai/bolo-dukaan/main/deploy/install.sh | sudo bash
#
# It asks for your web address (e.g. bolodukaan.duckdns.org), your DuckDNS token (optional) and your .env,
# then sets up: the app as a service that restarts by itself, Caddy with free HTTPS, the firewall,
# a DuckDNS updater, and a daily database backup (kept 14 days). Safe to run again: it updates in place.
set -euo pipefail

REPO="${BD_REPO:-https://github.com/channallikrishnasai/bolo-dukaan.git}"
BRANCH="${BD_BRANCH:-main}"
APP_DIR=/opt/bolo-dukaan
APP_USER=bolo
PORT=8000
BACKUP_DIR=/var/backups/bolo-dukaan
TEST_MODE="${BD_TEST:-0}"   # 1 = container test: no systemd, no Caddy service, no firewall

say()  { printf '\n\033[1;33m==> %s\033[0m\n' "$*"; }
ok()   { printf '\033[1;32m  ✓ %s\033[0m\n' "$*"; }
die()  { printf '\n\033[1;31m✗ %s\033[0m\n' "$*" >&2; exit 1; }
ask()  { local v; read -r -p "$1" v < /dev/tty || true; printf '%s' "$v"; }

[ "$(id -u)" -eq 0 ] || die "Run with sudo:  curl -fsSL …/install.sh | sudo bash"
command -v apt-get >/dev/null || die "This script needs Ubuntu or Debian."

# ------------------------------------------------------------------ 1. questions
DOMAIN="${BD_DOMAIN:-}"
DUCK_TOKEN="${BD_DUCKDNS_TOKEN:-}"
if [ -z "$DOMAIN" ]; then
  echo
  echo "Your web address, e.g.  bolodukaan.duckdns.org   (no https://)"
  DOMAIN="$(ask 'Web address: ')"
fi
DOMAIN="$(printf '%s' "$DOMAIN" | tr 'A-Z' 'a-z' | sed -e 's#^https\?://##' -e 's#/.*$##' -e 's/[[:space:]]//g')"
printf '%s' "$DOMAIN" | grep -Eq '^[a-z0-9]([a-z0-9-]*[a-z0-9])?(\.[a-z0-9]([a-z0-9-]*[a-z0-9])?)+$' || die "That doesn't look like a web address: '$DOMAIN'"
if [ -z "$DUCK_TOKEN" ] && printf '%s' "$DOMAIN" | grep -q '\.duckdns\.org$' && [ "$TEST_MODE" != 1 ]; then
  DUCK_TOKEN="$(ask 'DuckDNS token (from duckdns.org, Enter to skip): ')"
fi

# ------------------------------------------------------------------ 2. packages
say "Installing Python, git, SQLite and Caddy"
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq python3 python3-venv python3-pip git sqlite3 curl ca-certificates gnupg debian-keyring debian-archive-keyring apt-transport-https cron >/dev/null
if ! command -v caddy >/dev/null; then
  curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' | gpg --dearmor --yes -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
  curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' > /etc/apt/sources.list.d/caddy-stable.list
  apt-get update -qq && apt-get install -y -qq caddy >/dev/null
fi
python3 -c 'import sys; assert sys.version_info >= (3, 10), sys.version' || die "Python 3.10 or newer is needed."
ok "$(python3 --version), $(caddy version | cut -d' ' -f1) Caddy"
[ "$TEST_MODE" = 1 ] || timedatectl set-timezone Asia/Kolkata 2>/dev/null || true

# ------------------------------------------------------------------ 3. app code
say "Getting the app from GitHub"
id -u "$APP_USER" >/dev/null 2>&1 || useradd --system --home "$APP_DIR" --shell /usr/sbin/nologin "$APP_USER"
if [ -d "$APP_DIR/.git" ]; then
  git -C "$APP_DIR" fetch -q origin "$BRANCH" && git -C "$APP_DIR" reset -q --hard "origin/$BRANCH"
else
  mkdir -p "$APP_DIR" && git clone -q --branch "$BRANCH" "$REPO" "$APP_DIR.tmp"
  cp -a "$APP_DIR.tmp/." "$APP_DIR/" && rm -rf "$APP_DIR.tmp"
fi
python3 -m venv "$APP_DIR/.venv"
"$APP_DIR/.venv/bin/pip" install -q --upgrade pip
"$APP_DIR/.venv/bin/pip" install -q -r "$APP_DIR/requirements.txt"
mkdir -p "$APP_DIR/data"
ok "Code at $APP_DIR ($(git -C "$APP_DIR" log --oneline -1))"

# ------------------------------------------------------------------ 4. .env (your keys; never in git)
say "Settings (.env)"
ENV="$APP_DIR/.env"
if [ ! -s "$ENV" ]; then
  if [ -n "${BD_ENV_FILE:-}" ] && [ -f "$BD_ENV_FILE" ]; then
    cp "$BD_ENV_FILE" "$ENV"
  elif [ "$TEST_MODE" = 1 ]; then
    cp "$APP_DIR/.env.example" "$ENV"
  else
    echo "Paste the whole contents of your .env file (from your PC), then press Enter and Ctrl+D."
    echo "(Press Ctrl+D straight away to start from .env.example and fill keys in later with: sudo nano $ENV)"
    cat > "$ENV.paste" < /dev/tty || true
    if [ -s "$ENV.paste" ]; then mv "$ENV.paste" "$ENV"; else rm -f "$ENV.paste"; cp "$APP_DIR/.env.example" "$ENV"; fi
  fi
fi
sed -i 's/\r$//' "$ENV"
set_env() { if grep -q "^$1=" "$ENV"; then sed -i "s#^$1=.*#$1=$2#" "$ENV"; else printf '\n%s=%s\n' "$1" "$2" >> "$ENV"; fi; }
set_env PUBLIC_URL "https://$DOMAIN"
chown -R "$APP_USER:$APP_USER" "$APP_DIR"
chmod 600 "$ENV"
ok "PUBLIC_URL=https://$DOMAIN (QR codes, payment return links and receipts use this)"

# ------------------------------------------------------------------ 5. service
say "App service (starts on boot, restarts if it crashes)"
cat > /etc/systemd/system/bolo-dukaan.service <<EOF
[Unit]
Description=Bolo Dukaan
After=network-online.target
Wants=network-online.target

[Service]
User=$APP_USER
WorkingDirectory=$APP_DIR
ExecStart=$APP_DIR/.venv/bin/python run.py --host 127.0.0.1 --port $PORT --no-browser
Restart=always
RestartSec=3
Environment=PYTHONUNBUFFERED=1
NoNewPrivileges=true
ProtectSystem=full
ReadWritePaths=$APP_DIR/data

[Install]
WantedBy=multi-user.target
EOF

cat > /etc/caddy/Caddyfile <<EOF
# Bolo Dukaan: free HTTPS certificate from Let's Encrypt, renewed by Caddy automatically.
$DOMAIN {
	encode gzip
	request_body {
		max_size 25MB
	}
	reverse_proxy 127.0.0.1:$PORT
}
EOF

if [ "$TEST_MODE" = 1 ]; then
  ok "Test mode: skipping systemd, Caddy service and firewall"
else
  systemctl daemon-reload
  systemctl enable -q --now bolo-dukaan
  systemctl restart bolo-dukaan
  # ---------------------------------------------------------------- 6. firewall (Oracle images block 80/443 in iptables)
  say "Opening ports 80 and 443"
  for p in 80 443; do
    iptables -C INPUT -p tcp --dport "$p" -j ACCEPT 2>/dev/null || iptables -I INPUT 5 -p tcp -m state --state NEW --dport "$p" -j ACCEPT 2>/dev/null || iptables -I INPUT -p tcp --dport "$p" -j ACCEPT
  done
  if command -v netfilter-persistent >/dev/null; then netfilter-persistent save >/dev/null 2>&1 || true; fi
  if command -v ufw >/dev/null && ufw status | grep -q active; then ufw allow 80/tcp >/dev/null; ufw allow 443/tcp >/dev/null; fi
  ok "Ports open on this server (also open them in Oracle's Security List, see DEPLOY.md)"
fi

# ------------------------------------------------------------------ 7. DuckDNS + backups
mkdir -p /etc/bolo-dukaan "$BACKUP_DIR"
chmod 700 /etc/bolo-dukaan
if [ -n "$DUCK_TOKEN" ]; then
  SUB="${DOMAIN%.duckdns.org}"
  printf 'https://www.duckdns.org/update?domains=%s&token=%s&ip=' "$SUB" "$DUCK_TOKEN" > /etc/bolo-dukaan/duckdns.url
  chmod 600 /etc/bolo-dukaan/duckdns.url
  cat > /usr/local/bin/bolo-duckdns <<'EOS'
#!/usr/bin/env bash
# Keeps the DuckDNS name pointing at this server (token stays in a root-only file, never on the command line).
printf 'url = "%s"
' "$(cat /etc/bolo-dukaan/duckdns.url)" | curl -fsS -K - 2>/dev/null
EOS
  chmod 755 /usr/local/bin/bolo-duckdns
  echo "*/5 * * * * root /usr/local/bin/bolo-duckdns >/dev/null 2>&1" > /etc/cron.d/bolo-duckdns
  if /usr/local/bin/bolo-duckdns | grep -q OK; then ok "DuckDNS points $DOMAIN at this server"; else echo "  ! DuckDNS said no: check the token and the name ($SUB)"; fi
fi
install -m 755 "$APP_DIR/deploy/backup.sh" /usr/local/bin/bolo-backup
install -m 755 "$APP_DIR/deploy/update.sh" /usr/local/bin/bolo-update
echo "30 3 * * * root /usr/local/bin/bolo-backup >/dev/null 2>&1" > /etc/cron.d/bolo-backup
ok "Daily backup at 03:30 to $BACKUP_DIR (14 days kept). Update any time with: sudo bolo-update"

if [ "$TEST_MODE" != 1 ]; then
  systemctl enable -q caddy && systemctl restart caddy
  systemctl enable -q cron 2>/dev/null || true
  # ---------------------------------------------------------------- 8. check
  say "Checking the app"
  for i in $(seq 1 20); do curl -fsS "http://127.0.0.1:$PORT/api/health" >/dev/null 2>&1 && break; sleep 1; done
  curl -fsS "http://127.0.0.1:$PORT/api/health" >/dev/null || { journalctl -u bolo-dukaan -n 30 --no-pager; die "The app didn't start (log above)."; }
  ok "App is running"
  for i in $(seq 1 30); do curl -fsS "https://$DOMAIN/api/health" >/dev/null 2>&1 && break; sleep 3; done
  if curl -fsS "https://$DOMAIN/api/health" >/dev/null 2>&1; then
    ok "LIVE: https://$DOMAIN"
  else
    echo "  ! https://$DOMAIN isn't reachable yet. Usually: the domain doesn't point here yet, or ports 80/443"
    echo "    aren't open in Oracle's Security List. Fix that and Caddy finishes HTTPS by itself (no rerun needed)."
  fi
fi

cat <<EOF

  ┌──────────────────────────────────────────────────────────────┐
    Bolo Dukaan is installed.
    Owner sign-up / login : https://$DOMAIN/owner/signup
    Dashboard             : https://$DOMAIN/dashboard
    Then: Setup → QR codes → print them. Waiter & kitchen links
    are on the dashboard (🧑‍🍳 Staff, 📺 Kitchen display).
    Edit keys: sudo nano $ENV   then: sudo systemctl restart bolo-dukaan
    Logs:      sudo journalctl -u bolo-dukaan -f
  └──────────────────────────────────────────────────────────────┘
EOF
