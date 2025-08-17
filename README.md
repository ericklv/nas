# Home Automation
Automatization using docker compose

## First steps
- Install docker
- Install docker compose
- Configure Github user if you need it (see Github section)
- Check `mount-hdd.sh` to mount your disk in NAS
- Clone this repository
- Set static ip (see commands section)
- Run docker compose up --build -d
- Run install-hacs.sh

## Services
### Available
- Home Assistant (HACS)
- SFTPGo (secure file transfer)
- Homebridge (integrate devices with HomeKit)
- Cloudflared (Cloudflare Tunnel)
- Portainer (Monitoring containers)
- Watchower (Update containers)

### Coming soon
- PiHole (DNS filtering / ad blocking / privacy)
- WireGuard Easy (VPN)

## Commands
### Set static ip
```
sudo nmtui
```
### Values
- address: 192.168.1.10/24
- gateway: 192.168.1.1
- dns: 1.1.1.1
- dns: 1.0.0.1

## Github
### Generate ssh key in nas
```
ssh-keygen -t rsa -b 4096 -C "elazon01@gmail.com"
```

### Add ssh key in Github
Setting > SSH and GPG keys > New SSH key

## Docker
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
