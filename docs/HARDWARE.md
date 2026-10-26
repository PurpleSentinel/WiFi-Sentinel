# Hardware and bill of materials

## Tested installation (Wi-Fi 2026-10-24; BLE 2026-10-25)

| Component | Evidence / state |
|---|---|
| Collector | **Raspberry Pi 4 Model B Rev 1.2**, read from `/proc/device-tree/model` |
| Hostname | `pi5`; a hostname is not a hardware model |
| Monitoring chip | **ESP32-C6 (QFN40), revision v0.0**, identified by esptool during bring-up |
| Sensor Wi-Fi | **2.4 GHz only**, one receive channel at a time; deployed on channel 6 |
| Sensor BLE | Passive legacy LE 1M advertisement reception tested; optional, shares the C6 radio with Wi-Fi |
| USB transport | Native Espressif USB Serial/JTAG, VID:PID `303a:1001` |
| Tested toolchain | ESP-IDF **v5.5.4**, target `esp32c6` |
| Tested functions | Build/flash, sampled beacons and heartbeat, passive BLE reports, USB ingestion, runtime controls, channel switching and NVS persistence |
| Board product/PCB revision | Unknown; the USB/chip identifiers do not establish a commercial board model |
| Antenna/connector/pinout/flash capacity | Not independently established; do not infer PCB features from chipset capabilities or the build's flash-size setting |

This sensor has not been identified as an eBeetle 2 or an ESP32-C5 board.
The C6 cannot monitor 5 GHz or 6 GHz. The Pi's own Wi-Fi is separate from the
USB sensor and is not reconfigured by the collector.

### Installation-specific USB identifiers

The monitoring sensor currently enumerates as `/dev/ttyACM1`, with USB serial
`40:4C:CA:4D:6F:E4`. Its stable path is:

```text
/dev/serial/by-id/usb-Espressif_USB_JTAG_serial_debug_unit_40:4C:CA:4D:6F:E4-if00
```

A different ESP device currently occupies `/dev/ttyACM0`. Never open or flash it
for this project. Enumeration numbers can change after reboot/reconnection;
match the USB serial and prefer the by-ID path. These identifiers describe this
installation, not values to copy onto another host without checking its devices.

## Core bill of materials

| Item | Quantity | Notes |
|---|---:|---|
| ESP32-C6 development board exposing native USB Serial/JTAG | One per monitored channel | Tested chip family; establish exact board product and antenna before buying replacements |
| USB data cable matching the actual board connector | One per sensor | Charge-only cables do not carry telemetry |
| Raspberry Pi 4 or compatible Linux collector host | One | Fedora can also run the collector; the Pi 4 hosts this tested installation |
| Appropriate Pi supply and reliable microSD/SSD | One | Pi 4 official specification lists 5 V / 3 A via USB-C; check the actual supply and combined USB load |
| Powered USB hub | Optional | Useful when peripheral power demand exceeds the host's available USB power |
| RF-appropriate enclosure | Optional | Avoid shielding or detuning the antenna |

No extra GPIO circuits or level shifters are required by this application.
Consult the exact board's vendor documentation before making antenna, GPIO,
boot-button, or power assumptions. See [official references](REFERENCES.md).

## Optional ESP32-C5 path — unvalidated hardware

The source retains an `esp32c5` target and band selection for the C5's single
2.4/5 GHz radio. This is a separate, unvalidated path: it does not add 5 GHz to
this installation's C6. Earlier references to an eBeetle 2 C5 board were an
unverified candidate, not an identification of the deployed board.

Qualify the exact C5 board, supported chip revision/toolchain, USB console,
antenna for both bands, power, and permitted channels before using that path.
The runtime UI offers a conservative non-DFS 5 GHz subset on capable targets;
the driver still enforces its regulatory constraints. No 6 GHz support is claimed.

## Monitoring placement and coverage

Reception depends on distance, orientation, walls, traffic and antenna quality.
Low frame counts do not prove that no activity occurred. One fixed-channel
sensor cannot hear every channel; two sensors fixed to different channels give
more continuous coverage. Live multi-port fan-in within one collector process
remains a roadmap item. See [validation limits](VALIDATION.md).

## Bluetooth Low Energy monitoring

The current C6 provides BLE monitoring without another USB peripheral or the
Pi Bluetooth adapter. Existing unrelated ESP hardware remains outside this
application. Wi-Fi sniffing and BLE scanning share the C6 RF path; Espressif
classifies simultaneous performance as unstable. Separate RF sensors and
collectors are appropriate when coverage continuity matters; single-process
multi-port collection is still not implemented.

Live BLE reports, enable/disable and reboot persistence were exercised on this
C6, but controlled-device identity verification and long RF soak tests remain
outstanding. Do not infer support for extended advertisements, Bluetooth Classic
or untested C5 BLE hardware. See [BLE limits](BLE.md) and [validation](VALIDATION.md).

## Collector-side BLE explorer additions

Release 1.3 identification/layout and RSSI-curve enhancements require the 1.3
collector/dashboard, not a new sensor image or host Bluetooth stack. Preserve
the current USB device, Wi-Fi channel and Pi network configuration. Review
[BLE explorer](BLE_EXPLORER.md) and [approximate ranging](BLE_RANGING.md).
No physical calibration accuracy or new RF capability is implied.
