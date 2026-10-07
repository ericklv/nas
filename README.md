# Home Automation

Automation using docker compose in your NAS (raspberry pi, orange pi, nuc or delorean lol)

##  Steps

- Install docker
- Install docker compose
- Configure Github user if you need it (see Github section)
- Check `mount-hdd.sh` to mount your disk in NAS
- Clone this repository
- Set static ip in the NAS (explained below)
- Configure your `.env` file with all variables required as described in `.env.example`
- Run ` docker compose up --build -d ` to start containers
- Run `sh install-hacs.sh` to install HACS in Home Assistant container
- Configure your router with the static ip assigned to NAS as DNS primary, necessary for pihole
- Configure all devices you need in Home Assistant
- Go to Cloudflare Tunnel Dashboard and expose all containers you want. You need a domain previously configured in  Cloudflare
- Enjoy!

## Services

### Available

- Home Assistant (HACS)
- SFTPGo (secure file transfer)
- Homebridge (integrate devices with HomeKit)
- Cloudflared (Cloudflare Tunnel)
- Portainer (Manage containers)
- WatchTower (Update containers)
- PiHole (DNS filtering / ad blocking / privacy)
- Tailscale (VPN)
- Mosquitto (MQTT Broker, internal)
- Frigate (NVR + cat detection on Tapo C220)
- door-watch (Telegram alerts: cat detected / door open)

### Coming soon

- WireGuard Easy (VPN) ...some day. CGNAT is too complicated.
- Addons for Home Assistant
- QBitTorrent

## Configuration

### Set static ip

```
sudo nmtui
```

Edit your connection with this values.

### Values

- address: 192.168.1.10/24 (static ip example)
- gateway: 192.168.1.1
- dns: 1.1.1.1
- dns: 1.0.0.1

## Github

### Generate ssh key in NAS with email

```
ssh-keygen -t rsa -b 4096 -C "your@email.com"
```

### Add ssh key in Github

Setting > SSH and GPG keys > New SSH key

Good job, you can now clone all repositories!

## Tailscale

### Create account and generate auth key

Go to [Tailscale](https://tailscale.com/) and create account.
Move to Setting > Personal Settings > Keys > Generate auth key

Complete form and enable _Reusable_ option. Remember auth key expire in 90 days (free mode). Add this key in your `.env` file.

After run docker containers go to Machines section, in *homelab-docker* machine > 3 dots > edit route settings > check if _subnet routes_ and _exit node_ is enabled.

Install tailscale app in your mobile, login with your account and enjoy!

## PiHole
Fix database, maybe you need in first time
```
docker exec -it pihole pihole -g
```

## Home Assistant in Cloudflare Tunnel.
Go to Home Assistant > File Editor > configuration.yaml > Edit
```
http:
  use_x_forwarded_for: true
  trusted_proxies:
    - 172.20.0.0/24
  ip_ban_enabled: true
  login_attempts_threshold: 5
```

## Tapo camera + AI (Frigate + door-watch)

Frigate detects cats with the CPU detector (Fedora's mainline kernel uses the `rocket` NPU driver, Frigate's `rknn` detector needs the Rockchip vendor kernel). `door-watch` sends Telegram alerts for cats and for the door being open.

### Camera

Tapo app > Camera > Advanced settings > Camera account: create user/password and add them to `.env` (`FRIGATE_TAPO_*`). Test from the NAS:

```
ffprobe -rtsp_transport tcp "rtsp://USER:PASS@192.168.0.194:554/stream2"
```

### Fedora

```
sudo firewall-cmd --permanent --add-port=8971/tcp
sudo firewall-cmd --reload
```

Frigate UI: `https://<nas-ip>:8971` (self-signed cert). The admin password is printed on first start: `docker logs frigate | grep -i password`.

### Telegram bot

- Talk to @BotFather > `/newbot` > copy the token to `TELEGRAM_BOT_TOKEN`
- Send `/start` to your bot
- Get your chat id: `curl -s "https://api.telegram.org/bot<TOKEN>/getUpdates"` > `"chat":{"id":...}` to `TELEGRAM_CHAT_ID`

### Door calibration

`DOOR_ROI` is `x,y,w,h` in the 640x360 detect frame. With the door **closed**:

```
docker compose exec door-watch python main.py debug                    # check debug_roi.png in ${DISK_PATH}/door-watch
docker compose exec door-watch python main.py capture-reference day
docker compose exec door-watch python main.py capture-reference night  # at night (IR mode)
```

Open the door and run `debug` again: set `DOOR_THRESHOLD` between the closed and open scores, then `docker compose up -d door-watch`.

## Docker commands

Up services

```
docker compose up --build -d
```

Check status

```
docker ps
```

Enter into container

```
docker exec -ti <container-name-or-id> /bin/bash
```

Stop services

```
docker compose down
```

See logs

```
docker compose logs -f <container-name-or-id>
```
