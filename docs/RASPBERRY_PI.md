# Raspberry Pi 5 collector deployment

Recommended OS: current Raspberry Pi OS **64-bit Lite** for a headless service, or desktop if you prefer to inspect locally. The same Python package runs on Fedora. Keep Pi OS patched and physically secure.

## 1. Install dependencies

```bash
sudo apt update
sudo apt install -y python3 python3-venv python3-pip git
```

Transfer the ZIP to the Pi or clone your GitHub repository:

```bash
unzip wifi-sentinel.zip
cd wifi-sentinel/collector
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e .
```

Do an offline demo first:

```bash
wifi-sentinel demo
wifi-sentinel serve
```

From another computer, leave the app bound to `127.0.0.1` and tunnel over SSH:

```bash
ssh -L 8080:127.0.0.1:8080 pi@<pi-hostname-or-ip>
```

Then browse `http://127.0.0.1:8080` on your workstation. Alternatively install an authenticated reverse proxy with TLS; **do not** set `WIDS_HOST=0.0.0.0` on an untrusted network because the dashboard currently has no login system.

## 2. Connect the sensor

Use a USB data cable, a stable Pi power supply and a powered hub if necessary:

```bash
dmesg | tail -40
ls -l /dev/serial/by-id/
ls -l /dev/ttyACM* /dev/ttyUSB* 2>/dev/null
id -nG
```

For serial permissions, add your user to the relevant device group (often `dialout`) and sign out/in. Do not run collector as root.

```bash
export WIDS_SERIAL_PORT=/dev/serial/by-id/<your-exact-device>
export WIDS_BAUD=115200
wifi-sentinel serve
```

If only boot text appears but no `WIDS` telemetry, inspect ESP-IDF console selection in the firmware configuration and try the ESP-IDF monitor first (stop it before opening the collector).

## 3. Configure thresholds and allowlists

```bash
cp ../../config/collector.env.example .env
$EDITOR .env
set -a
source .env
set +a
wifi-sentinel serve
```

For a permanent deployment create `collector/.env` and set an actual stable serial port. This is a shell-sourced file, **not automatically loaded by the application**. The `.gitignore` excludes it from commits.

## 4. Optional user systemd service

Edit the service's `EnvironmentFile`, `WorkingDirectory` and `ExecStart` for where you installed the repo and your Linux username. The provided service template assumes `~/wifi-sentinel/collector/`:

```bash
mkdir -p ~/.config/systemd/user
cp ../../systemd/wifi-sentinel.service ~/.config/systemd/user/
# Modify paths and environment file location before enabling:
$EDITOR ~/.config/systemd/user/wifi-sentinel.service
systemctl --user daemon-reload
systemctl --user enable --now wifi-sentinel.service
journalctl --user -u wifi-sentinel.service -f
```

To let a user service run after logout, if appropriate on your Pi:

```bash
sudo loginctl enable-linger "$USER"
```

Limit database permissions and keep the Pi on a trusted management LAN.

## 5. Capacity / operations

SQLite is suitable for a modest number of sensors, but a default every-Nth-beacon telemetry strategy is recommended to reduce wear and contention. Monitor `dropped` heartbeat counts and DB size, reduce beacon capture if necessary, and use an SSD for sustained collection. See `docs/OPERATIONS.md`.
