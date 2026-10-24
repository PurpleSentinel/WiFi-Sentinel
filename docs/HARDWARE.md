# Hardware / bill of materials

## Core bill of materials

| Item | Quantity | Required | Comments |
|---|---:|---|---|
| eBeetle 2 ESP32-C5 IoT Development Board | 1 per channel | Yes | Board identity/console pinout/antenna **must be confirmed against vendor PCB** |
| USB data-capable cable matching the PCB | 1 | Yes | Not charge-only |
| Fedora development computer | 1 | For builds | ESP-IDF toolchain + flash/programming access |
| Raspberry Pi 5 or other Linux host | 1 | Optional | Store, correlate, dashboard; can run on Fedora instead |
| Pi 5 adequate power supply + microSD/SSD | 1 | If Pi used | Use official/quality power and a reliable disk |
| Powered USB hub | Optional | For >1 sensor | Prevent low-power disconnects |
| RF-appropriate enclosure | Optional | For permanent use | Avoid metal shielding/antenna detuning |
| Known-good 5 GHz-capable antenna | Verify | PCB dependent | Never assume 2.4-only antenna adequate for 5 GHz |

No wireless packet transmission from the application, level shifters or external circuits are necessary. The specific eBeetle 2 USB connector, module antenna, boot/reset buttons, flash size and schematic **could not be independently established** from authoritative product documentation when preparing this repository. Consequently the project **does not invent pin assignments**.

## Important physical questions to answer on receipt

1. Is the installed chip an ESP32-C5 production revision supported by IDF v5.5.2+?
2. Does it expose native USB Serial/JTAG or an external USB-to-UART interface? Which VID/PID and Linux `/dev/serial/by-id/` path?
3. Does flashing require a BOOT/RESET button combination?
4. Is the onboard antenna approved/performs adequately at **both** 2.4 and 5 GHz? If a connector is present, confirm antenna type and RF path before attachment.
5. Are there unusual boot straps/USB bridges/watchdogs that constrain continuous operation?
6. Which 5 GHz channels are permitted by country/region and actually supported by this SKU?

## 2.4 vs 5 GHz

ESP32-C5 uses a single dual-band Wi-Fi radio. `WIFI_BAND_MODE_AUTO` does **not** create two concurrent sniffers. The default config is channel 6 on 2.4 GHz. For 5 GHz select the 5G Kconfig option and change the channel to an authorized locally supported channel (e.g. 36 where legal). Some channels require DFS and other rules; do not assume every channel in the Kconfig numeric range is available.

## Monitoring placement

Passive reception quality depends on distance, orientation, walls, competing transmitters, and antenna efficiency. Put the receiver where it can hear the legitimate AP and nearby client devices. A capture rate near zero may reflect placement or antenna issues, not an absence of attacks.

## Better continuous coverage

With two channels in use, use **two sensors**, each fixed to one channel. More sensors can support different channels and physical locations, but live multi-port aggregation is not yet wired into a single collector process (see architecture and roadmap).
