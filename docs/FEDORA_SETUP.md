# Fedora development workflow (GNOME / VS Code / terminal)

## 1. Host dependencies

```bash
sudo dnf install -y git curl wget flex bison gperf cmake ninja-build ccache \
  dfu-util libusbx python3 python3-pip python3-virtualenv python3-devel \
  openssl-devel
```

Versions of Fedora differ in package names. If the above reports a missing package, use the [official ESP-IDF Linux setup](REFERENCES.md) for the exact set supported by your Fedora release. Use a non-root user for development.

## 2. Install ESP-IDF (separate from this repo)

The deployed ESP32-C6 was built/flashed with v5.5.4. C6 supports 2.4 GHz only; its target defaults use native USB Serial/JTAG. Optional C5/5 GHz support remains unvalidated.

Example known documented version: v5.5.4. Upgrading within a security-reviewed patch series is sensible. **Do not use early ESP32-C5 preview releases below v5.5.2 for production-revision C5 devices.**

```bash
mkdir -p ~/esp
cd ~/esp
git clone --recursive --branch v5.5.4 https://github.com/espressif/esp-idf.git
cd esp-idf
./install.sh esp32c6
. ./export.sh
idf.py --version
```

If you already have ESP-IDF installed, simply source its `export.sh` in each new terminal.

## 3. Clone/import the local ZIP as a repository

```bash
unzip wifi-sentinel.zip
cd wifi-sentinel
git init
git add .
git commit -m "Initial WiFi Sentinel passive IDS prototype"
```

To publish later, create an empty repository using the GitHub website and follow the new repository's `git remote add origin ...` instructions. This archive does not make changes to your GitHub account.

## 4. Build firmware

```bash
cd firmware
idf.py set-target esp32c6
idf.py menuconfig
idf.py build
```

Select: `WiFi Sentinel sensor configuration` for band/channel/sensor ID. For serial reporting, ensure the **console output channel** matches the actual PCB (native USB Serial/JTAG vs board UART bridge). The firmware relies on `printf` through the ESP-IDF console; it has no separate hardcoded pinout.

## 5. Identify and flash the board

```bash
ls -l /dev/serial/by-id/ 2>/dev/null || true
ls -l /dev/ttyACM* /dev/ttyUSB* 2>/dev/null || true
# Set SENSOR_PORT to the verified /dev/serial/by-id/... path first
idf.py -p "$SENSOR_PORT" flash monitor
```

You may need permissions to use the serial device:

```bash
id -nG
sudo usermod -aG dialout "$USER"
# Log out and in for group membership to take effect.
```

Do not grant world-writable serial permissions or use `chmod 777`.

## 6. Run collector/dashboard on Fedora

```bash
cd ../collector
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[dev]'
python -m pytest -q tests
wifi-sentinel demo
wifi-sentinel serve
```

The dashboard is `http://127.0.0.1:8181`. For a plugged-in board, stop the monitor terminal so it releases the serial port, then:

```bash
export WIDS_SERIAL_PORT="$SENSOR_PORT"   # verified by-ID path
wifi-sentinel serve
```

Only one process can open the serial port at a time. Native USB Serial/JTAG may enumerate differently when flashed or reset. Prefer `/dev/serial/by-id/...` if available.

## 7. VS Code

Install the official **Espressif IDF** and Python extensions. Open `wifi-sentinel/` as workspace. Point ESP-IDF extension to `~/esp/esp-idf` and the compiler environment. The firmware folder is an IDF project, while the Python package lives in `collector/`. Configure a Python interpreter at `collector/.venv/bin/python`.

## Developer checks

```bash
cd collector
python -m pytest -q tests
python -m compileall -q wids
# Optional after installing ruff:
ruff check wids tests
```

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
