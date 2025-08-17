# Home Automation

Automatization using docker compose

## First steps

- Install docker
- Install docker compose
- Configure Github user if you need it (see Github section)
- Check `mount-hdd.sh` to mount your disk in NAS
- Clone this repository
- Set static ip (see commands section)
- Configure your `.env` file with all variables required as described in `.env.example`
- Run `docker compose up --build -d` to start containers
- Run `install-hacs.sh` to install HACS in Home Assistant container

## Services

### Available

- Home Assistant (HACS)
- SFTPGo (secure file transfer)
- Homebridge (integrate devices with HomeKit)
- Cloudflared (Cloudflare Tunnel)
- Portainer (Monitoring containers)
- Watchower (Update containers)
- PiHole (DNS filtering / ad blocking / privacy)
- Tailscale (VPN)

### Coming soon

- WireGuard Easy (VPN) ...some day. CGNAT is too complicated.

## Commands

### Set static ip

```
sudo nmtui
```

Edit your connection with this values.

### Values

- address: 192.168.1.10/24
- gateway: 192.168.1.1
- dns: 1.1.1.1
- dns: 1.0.0.1

## Github

### Generate ssh key in nas with email

```
ssh-keygen -t rsa -b 4096 -C "your@email.com"
```

### Add ssh key in Github

Setting > SSH and GPG keys > New SSH key

## Tailscale

### Create account and generate auth key

Go to [Tailscale](https://tailscale.com/) and create account.
Move to Setting > Personal Settings > Keys > Generate auth key

Complete form and enable _Reusable_ option. Remember auth key expire in 90 days (free mode).

Add this key in your `.env` file.

After run containers go to Machines section,in *homelab-docker* machine > 3 dots > edit route settings check _subnet routes_ and _exit node_ is enabled.

Install tailscale app in your mobile, login with your account and enjoy!

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
