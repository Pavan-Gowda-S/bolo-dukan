# Put Bolo Dukaan live for free (always on)

**Result:** `https://<yourname>.duckdns.org` runs 24×7 with every part of the app: owner dashboard, table QR codes, waiter portal, kitchen TV, payments, games, supermarket, storage room. It costs ₹0 and has HTTPS, automatic restart and daily backups.

**Time:** about 30 minutes. You only do steps 1 and 2 by hand; the install script does the rest.

## Two free ways

| | **A. Your PC + ngrok (no card)** | **B. Oracle Cloud server (card check, never charged)** |
|---|---|---|
| Sign-up | ngrok with Google | DuckDNS + Oracle Cloud |
| Address | `https://yourname.ngrok-free.dev` (permanent) | `https://yourname.duckdns.org` (permanent) |
| Live when | your PC is on and awake | always, 24×7 |
| Visitors see | a one-time ngrok "Visit site" page | the site directly |
| Setup | 5 minutes | 30 minutes |

# A. No card: your PC + ngrok (5 minutes)
1. Double-click **`go-live.bat`** in the project folder.
2. The first time, it walks you through three things:
   - **Installing ngrok:** answer **Y**; it uses Microsoft's `winget`.
   - **Your ngrok token:** sign up free at https://dashboard.ngrok.com/signup with Google, copy the token from https://dashboard.ngrok.com/get-started/your-authtoken and paste it.
   - **Your permanent address:** open https://dashboard.ngrok.com/domains, copy your free address (e.g. `yourname.ngrok-free.dev`) and paste it.
3. It starts the app and the link, checks that it is reachable from the internet, and opens it. It also offers to **start automatically every time you log in to Windows**.
4. Print the QR codes again from **Setup → QR codes**. They now open the live address from any phone, on any network.

| Task | How |
|---|---|
| Stop the live site | `go-live.bat -Stop` |
| Stop the start-at-login | `go-live.bat -NoAutoStart` |
| Logs | `data\live.log`, `data\live-errors.log`, `data
grok.log` |

Keep the PC awake: **Settings → System → Power → Sleep → Never** (when plugged in). On this PC, use `http://localhost:8001` or the live link; logging in through the Wi-Fi IP over plain http won't work once the live address is set.

# B. Always on: Oracle Cloud Always Free

## 1. Free web address (DuckDNS, 2 minutes)
1. Open https://www.duckdns.org and sign in with Google or GitHub.
2. Type a name, e.g. `bolodukaan`, and click **add domain**. Your address is `bolodukaan.duckdns.org`.
3. Keep the page open; you need the **token** shown at the top in step 3.

## 2. Free server (Oracle Cloud Always Free, about 15 minutes)
1. Sign up at https://signup.cloud.oracle.com. Oracle asks for a card **only to check you are a real person**. "Always Free" resources are never charged.
2. **Create a VM instance**:
   - **Image:** Canonical **Ubuntu 24.04**.
   - **Shape:** `VM.Standard.A1.Flex` (Ampere, 1 OCPU and 6 GB is plenty) or `VM.Standard.E2.1.Micro`. Both are marked *Always Free eligible*.
   - **SSH keys:** choose *Generate a key pair* and download the private key.
   - Click **Create** and wait until it says *Running*. Copy the **Public IP address**.
3. **Open the web ports:**
   - Go to Instance → **Subnet** → **Default Security List** → **Add Ingress Rules**.
   - Source `0.0.0.0/0`, TCP, destination port **80**. Add a second rule for port **443**.
4. In DuckDNS, paste the **Public IP** next to your domain and click **update ip**.

## 3. One command (5 minutes)
Connect from your PC (Windows already has `ssh`), using the key you downloaded:

```powershell
ssh -i path\to\ssh-key.key ubuntu@YOUR_PUBLIC_IP
```

On the server, run:

```bash
curl -fsSL https://raw.githubusercontent.com/channallikrishnasai/bolo-dukaan/main/deploy/install.sh | sudo bash
```

It asks three things:

| Question | What to type |
|---|---|
| Web address | `bolodukaan.duckdns.org` |
| DuckDNS token | the token from step 1 (keeps the address pointing at the server) |
| .env | open your PC's `.env` in Notepad, copy all of it, paste, press Enter, then **Ctrl+D** |

At the end it prints **✓ LIVE: https://bolodukaan.duckdns.org**.

## 4. Use it
- **Owner:** `https://bolodukaan.duckdns.org/owner/signup`. Create your restaurant, then **Setup → QR codes → print**. The QR codes now open the live site from any phone, on any network.
- **Waiters:** Dashboard → **🧑‍🍳 Staff**: add a waiter and share their login link.
- **Kitchen TV:** Dashboard → **📺 Kitchen display**: open the link on the TV or tablet.
- **Storage room:** Dashboard → **📦 Storage room**.
- **Supermarket shop:** `https://bolodukaan.duckdns.org/s/<your-store>`.

Data on your PC (localhost) is separate. The live site starts empty, so sign up again there.

## Looking after it

| Task | Command (on the server) |
|---|---|
| Get the newest version after a GitHub push | `sudo bolo-update` (backs up first) |
| Change a key or feature switch | `sudo nano /opt/bolo-dukaan/.env` then `sudo systemctl restart bolo-dukaan` |
| See the live log | `sudo journalctl -u bolo-dukaan -f` |
| Back up now | `sudo bolo-backup` (also runs every night at 03:30, 14 days kept in `/var/backups/bolo-dukaan`) |
| Restore a backup | `sudo systemctl stop bolo-dukaan; gunzip -c /var/backups/bolo-dukaan/db-DATE.sqlite.gz > /opt/bolo-dukaan/data/bolo_dukaan.db; sudo chown bolo:bolo /opt/bolo-dukaan/data/bolo_dukaan.db; sudo systemctl start bolo-dukaan` |

## Payments and AI on the live site
- **Cashfree:** payment return links use the live address automatically. Keep `CASHFREE_ENV=sandbox` for testing. Switch to production keys only after Cashfree approves your account; they may ask you to whitelist `bolodukaan.duckdns.org` in their dashboard.
- **Google sign-in (optional):** add `https://bolodukaan.duckdns.org` under *Authorised JavaScript origins* in Google Cloud Console.
- **Sarvam / Gemini:** these work as-is with the same keys.

## If something is wrong

| You see | Fix |
|---|---|
| "isn't reachable yet" at the end | Check that ports 80 and 443 are in Oracle's Security List (step 2.3) and that DuckDNS shows the server's IP. Caddy finishes HTTPS by itself once it can be reached. |
| "The app didn't start" | The script prints the log. Usually a broken line in `.env`; fix it with `sudo nano /opt/bolo-dukaan/.env` and restart. |
| Mic doesn't work on phones | It needs `https://`, which the live site has. |

## Why not Vercel / Render free?
The app keeps orders, bills and uploads in a database file on disk. Vercel has no lasting disk, and Render's free disk is wiped on every deploy, so orders would vanish. The Oracle Always Free server keeps everything and never sleeps.
