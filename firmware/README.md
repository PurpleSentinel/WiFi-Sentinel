# ESP-IDF firmware (ESP32-C5 / ESP32-C6)

Passive receive-only sensor. No GPIO attachments are required. The project has
been built/flashed on the connected ESP32-C6, while the C5 path remains unvalidated; see
[validation plan](../docs/VALIDATION.md).

For the tested ESP32-C6 native USB Serial/JTAG interface, first set `SENSOR_PORT` to its verified `/dev/serial/by-id/...` path (see [Hardware](../docs/HARDWARE.md)). Stop the collector before opening/flashing its port, then use:

```bash
source ~/esp/esp-idf/export.sh
cd firmware
idf.py set-target esp32c6
idf.py build
idf.py -p "$SENSOR_PORT" flash
```

The C6 target defaults select the USB Serial/JTAG console, sensor ID
`c6-sensor-01`, and channel 6. C6 supports 2.4 GHz only; the 5 GHz option is
available only on capable targets such as C5. Verify the port belongs to the
intended board before flashing. Channel selection remains configurable through
`idf.py menuconfig`.

Prerequisites: ESP-IDF **v5.5.2 or newer in the 5.5 branch** with the selected target
support. Start with v5.5.4 for a known documented patch release. Prefer a newer
reviewed patch release if available.

The legacy Makefile `build-firmware` target selects C5; for this C6 installation use the explicit commands above.

The optional C5 build uses `idf.py set-target esp32c5`; qualify that separate
board and select the proper console before building. It is not the attached C6.


Under `WiFi Sentinel sensor configuration`, configure fixed band/channel and
sensor ID. Select the console interface under ESP-IDF's `Component config > ESP
System Settings > Channel for console output` to match the *actual PCB's USB or
UART circuitry*. USB Serial/JTAG and external USB-UART are not interchangeable.
The connected board's commercial model and antenna arrangement remain unknown; no eBeetle 2 identification or board pinout is assumed.

To check the receiver without the Pi, look for `WIDS { ... }` prefixed lines.
On quiet networks only heartbeat events may appear. Set beacon sample N=1 for
an initial functional test, then restore 20 to reduce traffic.

Sampling uses fixed state for 64 BSSID/channel entries and independent beacon /
probe-response counters. First observations are reported immediately, followed
by one after every N further observations. Other management subtypes remain
unsampled. FIFO eviction reports returning identities as new; it can increase
exports under address churn but does not grow memory or hide new entries.
The callback's sampler performs no allocation or I/O and scans at most 64 entries.
Host C tests exercise the same sampler header, including the four-AP periodic
regression, mixed subtype traffic, runtime factors and eviction stress.

With runtime-capable firmware, the dashboard Configuration dialog can change the
sensor ID, band/channel, sample factor, heartbeat interval and BLE
enable/scan interval/window over USB. Settings
are acknowledged after NVS persistence and survive reboots; they override
compiled defaults. See [configuration](../docs/CONFIGURATION.md) and
[USB commands](../docs/PROTOCOL.md). Native USB Serial/JTAG installs buffered
input for bounded commands; this path has been exercised on the C6.

SSID information elements are copied as up to 32 exact bytes with an explicit
length and presence flag. Firmware exports them as ASCII `ssid_hex`, not a C
string or underscore-sanitized text. Upgrade the collector before flashing this
version so UTF-8 names and arbitrary-byte SSIDs are decoded correctly. The host
compiler integration tests use the same extraction/serialization header as the
firmware; a host C compiler is needed to run those tests (otherwise they skip).

Each `WIDS` line is one JSON object; firmware outputs ordinary ESP-IDF logs too.
Configure console output to USB-serial or UART at a readable rate (115200 is
supported for ordinary UART; actual native USB Serial/JTAG transport baud
settings may not affect physical throughput).

## Bluetooth Low Energy monitoring

Build defaults enable NimBLE observer-only support and software RF coexistence;
central, peripheral and broadcaster roles are disabled. `ble_monitor.c` uses
passive legacy LE 1M scanning, a separate 64-report queue and a 20-report/second
export ceiling. It never advertises, connects, pairs or requests scan responses.
Extended advertisements and Bluetooth Classic are not collected.

Upgrade the collector first. The enlarged application uses the single-app large
partition layout: flash the complete generated image set with `idf.py flash` or
`write_flash @flash_args` from the build directory. Flashing only the application
onto an old partition layout can fail its size check. NVS remains at 0x9000; do
not erase it. This is not an OTA layout.

BLE defaults disabled when no saved BLE configuration exists. Enable it through
Configuration; scan interval/window default to 100/20 ms, with 10–10240 ms allowed
and window no greater than interval. Settings survive reboot separately from the
Wi-Fi configuration. Status exposes scan state, report/drop counts, free heap
and stack/controller errors. Open the **BLE** tab after Devices for observations.

Wi-Fi sniffer RX and BLE scanning share one radio and can miss traffic during
concurrent monitoring. Separate sensors are needed for dependable simultaneous
coverage. See [BLE configuration, limits and interpretation](../docs/BLE.md) and
[measured validation](../docs/VALIDATION.md).

## Collector-side BLE explorer additions

Release 1.3 identification/layout and RSSI-curve enhancements require the 1.3
collector/dashboard, not a new sensor image or host Bluetooth stack. The C6 firmware source remains version 1.2.0. Preserve
the current USB device, Wi-Fi channel and Pi network configuration. Review
[BLE explorer](../docs/BLE_EXPLORER.md) and [approximate ranging](../docs/BLE_RANGING.md).
No physical calibration accuracy or new RF capability is implied.
