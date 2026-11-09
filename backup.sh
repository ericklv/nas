#!/bin/bash
# Backup of all service state (${DISK_PATH}) + .env, to restore the NAS after a reinstall.
# Usage: ./backup.sh [dest_dir]   (default: ~/backups, keeps the last $KEEP archives)
# Restore: git clone the repo, then: sudo tar --numeric-owner -xzpf <archive> -C / && docker compose up -d
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
DEST="${1:-$HOME/backups}"
KEEP="${KEEP:-5}"

cd "$SCRIPT_DIR"
[ -f .env ] || { echo "missing .env in $SCRIPT_DIR" >&2; exit 1; }
# read only DISK_PATH (.env isn't valid bash: e.g. PIHOLE_DNS contains ';')
DISK_PATH="$(sed -n 's/^DISK_PATH=//p' .env | sed 's/[[:space:]]*#.*//;s/^["'\'']//;s/["'\'']$//' | tail -1)"
[ -n "${DISK_PATH:-}" ] && [ -d "$DISK_PATH" ] || { echo "DISK_PATH not set or not found" >&2; exit 1; }
DISK_PATH="$(realpath "$DISK_PATH")"

mkdir -p "$DEST"
DEST="$(realpath "$DEST")"
case "$DEST/" in "$DISK_PATH/"*) echo "dest must be outside DISK_PATH" >&2; exit 1;; esac
ARCHIVE="$DEST/nas-backup-$(date +%F_%H%M).tar.gz"

# stop containers so databases (HA, Jellyfin, Navidrome, Frigate, SFTPGo) are consistent; always restart them
docker compose stop
trap 'docker compose start' EXIT

# regenerable / large data is excluded: Jellyfin cache, Frigate recordings
sudo tar --numeric-owner -czpf "$ARCHIVE" \
  --exclude="${DISK_PATH#/}/jellyfin/cache" \
  --exclude="${DISK_PATH#/}/frigate/media" \
  -C / "${DISK_PATH#/}" "${SCRIPT_DIR#/}/.env"
sudo chown "$(id -u):$(id -g)" "$ARCHIVE"

echo "backup created: $ARCHIVE ($(du -h "$ARCHIVE" | cut -f1))"

# rotation: keep the newest $KEEP archives
ls -1t "$DEST"/nas-backup-*.tar.gz | tail -n +$((KEEP + 1)) | xargs -r rm --
