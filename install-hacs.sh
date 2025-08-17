#!/bin/bash

echo "waiting for home assistant boot..."
sleep 15  # 

echo "Install HACS..."
docker exec -it homeassistant bash -c "wget -O - https://get.hacs.xyz | bash -"

echo "reboot..."
docker restart homeassistant