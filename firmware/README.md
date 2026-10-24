# ESP-IDF firmware (ESP32-C5 only)

Passive receive-only sensor. No GPIO attachments are required. The project has
not been compiled on an ESP-IDF toolchain or tested on the eBeetle 2 hardware in
this release; see [validation plan](../docs/VALIDATION.md).

Prerequisites: ESP-IDF **v5.5.2 or newer in the 5.5 branch** with ESP32-C5 target
support. Start with v5.5.4 for a known documented patch release. Prefer a newer
reviewed patch release if available.

```bash
source ~/esp/esp-idf/export.sh
cd firmware
idf.py set-target esp32c5
idf.py menuconfig
idf.py build
idf.py -p /dev/ttyACM0 flash monitor
```

Under `WiFi Sentinel sensor configuration`, configure fixed band/channel and
sensor ID. Select the console interface under ESP-IDF's `Component config > ESP
System Settings > Channel for console output` to match the *actual PCB's USB or
UART circuitry*. USB Serial/JTAG and external USB-UART are not interchangeable.
Do not assume the eBeetle 2 uses the same USB wiring as Espressif's DevKitC.

To check the receiver without the Pi, look for `WIDS { ... }` prefixed lines.
On quiet networks only heartbeat events may appear. Set beacon sample N=1 for
an initial functional test, then restore 20 to reduce traffic.

Each `WIDS` line is one JSON object; firmware outputs ordinary ESP-IDF logs too.
Configure console output to USB-serial or UART at a readable rate (115200 is
supported for ordinary UART; actual native USB Serial/JTAG transport baud
settings may not affect physical throughput).
