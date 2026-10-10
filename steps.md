# door-watch: recalibrate references

Always with the door **closed**.

1. Rebuild the container:
   ```bash
   docker compose up -d --build door-watch
   ```
2. At night (camera in IR, lights off), replace the night reference:
   ```bash
   docker compose exec door-watch python main.py capture-reference night
   ```
3. Optional, to start fresh during the day:
   ```bash
   docker compose exec door-watch python main.py capture-reference day
   ```
4. Add more references in different lighting (morning, noon, sunset, stair light on):
   ```bash
   docker compose exec door-watch python main.py add-reference day
   ```
5. Open the door and run `debug` to see the open score. Set `DOOR_THRESHOLD` and `DOOR_THRESHOLD_NIGHT` in `.env` between the closed and open scores, then `docker compose up -d door-watch`:
   ```bash
   docker compose exec door-watch python main.py debug
   ```
