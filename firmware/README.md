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

With runtime-capable firmware, the dashboard Configuration dialog can change the
sensor ID, band/channel, sample factor and heartbeat interval over USB. Settings
are acknowledged after NVS persistence and survive reboots; they override
compiled defaults. See [configuration](../docs/CONFIGURATION.md) and
[USB commands](../docs/PROTOCOL.md). Native USB Serial/JTAG installs buffered
input for bounded commands; this path has been exercised on the C6.

Each `WIDS` line is one JSON object; firmware outputs ordinary ESP-IDF logs too.
Configure console output to USB-serial or UART at a readable rate (115200 is
supported for ordinary UART; actual native USB Serial/JTAG transport baud
settings may not affect physical throughput).
