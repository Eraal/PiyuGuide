# TURN Server Setup (coturn) for PiyuGuide Video Counseling

A TURN server is REQUIRED for reliable video sessions across different ISPs, mobile networks, CGNAT and restrictive firewalls. STUN alone will cause black video or one-way media in many real-world cases.

## 1. Summary

| Item | Why It Matters |
|------|----------------|
| STUN | Discovers public reflexive addresses (fails with symmetric NAT) |
| TURN | Relays media when direct P2P path fails |
| TLS Port 5349 / 443 | Traversal through corporate/firewall blocked UDP |
| Multiple Transports | Improves success matrix (UDP preferred, TCP/TLS fallback) |

## 2. Choose Deployment Method

You can: (A) Install coturn directly on your main server, or (B) Deploy on a separate small VM (recommended for scale or security isolation).

## 3. Install coturn (Ubuntu/Debian Example)
```bash
apt update
apt install coturn -y
sed -i 's/#TURNSERVER_ENABLED=0/TURNSERVER_ENABLED=1/' /etc/default/coturn
```

## 4. DNS Records
Create an A record: `turn.yourdomain.com` → public IP of the TURN server.
(Optionally also `stun.yourdomain.com`, though not required.)

## 5. TLS Certificates (Optional but Recommended)
If using certbot / Let's Encrypt on same host:
```bash
apt install certbot -y
certbot certonly --standalone -d turn.yourdomain.com
```
Certificates will be at:
```
/etc/letsencrypt/live/turn.yourdomain.com/fullchain.pem
/etc/letsencrypt/live/turn.yourdomain.com/privkey.pem
```

## 6. Minimal `/etc/turnserver.conf`
```
listening-port=3478
tls-listening-port=5349
fingerprint
use-auth-secret
static-auth-secret=REPLACE_WITH_RANDOM_32_BYTE_HEX
realm=piyuguide.live
# Quotas / limits
total-quota=300
bps-capacity=0
stale-nonce
# Security
no-loopback-peers
no-multicast-peers
# Certificates (comment out if not using TLS yet)
cert=/etc/letsencrypt/live/turn.yourdomain.com/fullchain.pem
pkey=/etc/letsencrypt/live/turn.yourdomain.com/privkey.pem
```
Generate a random static-auth-secret:
```bash
python3 - <<'PY'
import secrets
print(secrets.token_hex(16))
PY
```
Replace `REPLACE_WITH_RANDOM_32_BYTE_HEX` with that value.

## 7. Start / Enable Service
```bash
systemctl enable coturn
systemctl restart coturn
journalctl -u coturn -f
```

## 8. Firewall Rules
Allow inbound:
- UDP 3478
- TCP 3478
- TCP 5349 (TLS)
- (Optional fallback) TCP 443 forwarded to 5349 if corporate firewalls block 5349

## 9. Application Environment Variables
Pick ONE approach:

### Option A: Explicit JSON
Set `ICE_SERVERS_JSON` to a JSON string (single line):
```
[{"urls":["stun:stun.l.google.com:19302"]},{"urls":["turn:turn.yourdomain.com:3478?transport=udp","turn:turn.yourdomain.com:3478?transport=tcp","turns:turn.yourdomain.com:5349?transport=tcp"],"username":"turnuser","credential":"strongpass"}]
```

### Option B: Host Components (Simpler)
```
TURN_HOST=turn.yourdomain.com
TURN_USERNAME=turnuser
TURN_PASSWORD=strongpass
```
The app expands to:
```
[
  {"urls":["stun:turn.yourdomain.com:3478"]},
  {"urls":["turn:turn.yourdomain.com:3478?transport=udp","turn:turn.yourdomain.com:3478?transport=tcp","turns:turn.yourdomain.com:5349?transport=tcp"],"username":"turnuser","credential":"strongpass"}
]
```

### Option C (Legacy Single URL)
```
TURN_URL=turn:turn.yourdomain.com:3478
TURN_USERNAME=turnuser
TURN_PASSWORD=strongpass
```

## 10. Dynamic / Time-Limited Credentials (Optional Upgrade)
For higher security use `use-auth-secret` and generate ephemeral credentials:
```
username = unix_timestamp + random
HMAC(username, static-auth-secret) -> credential
```
Return these from an authenticated endpoint so browsers only get short-lived TURN access.

## 11. Validation (Chrome / Edge)
Open a call → Go to `chrome://webrtc-internals`:
- Find the active PeerConnection.
- Confirm selected candidate pair has `relay` (type) if peers are on different networks.
- If only `host`/`srflx` appear and remote media black: TURN not used / misconfigured.

## 12. Troubleshooting
| Symptom | Likely Cause | Action |
|---------|-------------|--------|
| Black video cross-ISP | No TURN relay | Verify env vars; check coturn logs |
| Long connection time | Packet loss / blocked UDP | Ensure TCP/TLS listeners; firewall rules |
| Works then freezes after network change | No ICE restart logic | Ensure JS calls createOffer({iceRestart:true}) |
| 401 in coturn logs | Bad credentials | Match username/password with env values |
| No relay candidates | Firewall or DNS issue | Confirm ports open; dig turn.yourdomain.com |

## 13. Production Hardening
- Set `no-tcp-relay` only if certain UDP always available (usually don't).
- Monitor logs for abuse (excess allocations).
- Rotate credentials or move to ephemeral HMAC-based.

## 14. Removal / Reset
```
systemctl stop coturn
mv /etc/turnserver.conf /etc/turnserver.conf.bak
systemctl start coturn
```

---
After configuring, restart your app (systemd) so the new environment variables are picked up:
```
sudo systemctl restart piyuguide
```

Once relay candidates appear and bitrate > 0 in stats, the TURN setup is successful.
