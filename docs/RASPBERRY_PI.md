# Raspberry Pi 4 collector deployment

The tested host reports **Raspberry Pi 4 Model B Rev 1.2** in `/proc/device-tree/model`; its hostname `pi5` is not its model. The attached monitoring sensor is an ESP32-C6 using USB Serial/JTAG and 2.4 GHz only. See [installation identifiers](HARDWARE.md).

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
ssh -L 8181:127.0.0.1:8181 pi@<pi-hostname-or-ip>
```

Then browse `http://127.0.0.1:8181` on your workstation. Alternatively install an authenticated reverse proxy with TLS; **do not** set `WIDS_HOST=0.0.0.0` on an untrusted network because the dashboard currently has no login system.

## 2. Connect the C6 sensor

Use a USB data cable, a stable Pi power supply and a powered hub if necessary:

```bash
dmesg | tail -40
ls -l /dev/serial/by-id/
ls -l /dev/ttyACM* /dev/ttyUSB* 2>/dev/null
id -nG
```

Match the sensor USB serial, not just `/dev/ttyACM1`: that enumeration can change. A separate ESP device currently uses `/dev/ttyACM0`; leave it to its existing application. Do not alter Pi Wi-Fi settings to receive USB telemetry.

For serial permissions, add your user to the relevant device group (often `dialout`) and sign out/in. Do not run collector as root.

```bash
export WIDS_SERIAL_PORT=/dev/serial/by-id/<your-exact-device>
export WIDS_BAUD=115200
wifi-sentinel serve
```

If only boot text appears but no `WIDS` telemetry, inspect ESP-IDF console selection in the firmware configuration and try the ESP-IDF monitor first (stop it before opening the collector).

## 3. Configure thresholds and allowlists

```bash
cp ../config/collector.env.example .env
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
cp ../systemd/wifi-sentinel.service ~/.config/systemd/user/
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

SQLite is suitable for a modest number of sensors. Per-BSSID/channel/subtype
sampling reduces steady-state beacon/probe telemetry while immediately reporting
new entries. New identities and table eviction can temporarily raise the rate.
Monitor `dropped` heartbeat counts and DB size, increase the sample factor if
needed, and use an SSD for sustained collection. See `docs/OPERATIONS.md`.

## Enable BLE and use its dashboard tab

BLE scanning runs on the USB ESP32-C6, not the host Bluetooth adapter. It needs
no BlueZ service, Pi wireless reconfiguration or additional serial device. Leave
unrelated ESP hardware and the host's Ethernet/Wi-Fi settings unchanged.

1. Upgrade the collector before flashing BLE-capable sensor firmware.
2. Stop the collector, build with the supplied NimBLE/coexistence defaults and
   flash the complete generated image set, including the enlarged app partition
   table. Preserve NVS and use only the verified C6 by-ID port.
3. Restart the collector. Open Configuration, enter its existing key, enable BLE
   and apply sensor settings. New sensors start with BLE disabled; saved settings
   override the defaults. Interval/window default to 100/20 ms.
4. Check Status for passive scanning, report/drop counts and error 0. Open **BLE**
   immediately after Devices for advertiser summaries and recent advertisements.
5. Set BLE observation filters, optional alert rules and independent retention/
   record limits in Configuration. The software-only `demo` generates Wi-Fi data;
   use the [BLE replay example](BLE.md#software-only-example) for BLE UI testing.

The C6 shares its radio between Wi-Fi sniffing and BLE scanning; captures are
best effort. The existing collector supports one live USB input. For reliable
simultaneous coverage, use separate sensors/collectors. See [BLE monitoring](BLE.md)
and [operations](OPERATIONS.md) for privacy, limits and troubleshooting.

## Collector-side BLE explorer additions

Post-v1.2 identification/layout and RSSI-curve enhancements require an updated
collector/dashboard, not a new sensor image or host Bluetooth stack. Preserve
the current USB device, Wi-Fi channel and Pi network configuration. Review
[BLE explorer](BLE_EXPLORER.md) and [approximate ranging](BLE_RANGING.md).
No physical calibration accuracy or new RF capability is implied.
