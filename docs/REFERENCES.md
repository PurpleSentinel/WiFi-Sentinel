# Hardware and technical references

## Tested ESP32-C6 / Raspberry Pi 4 path

- [ESP32-C6 datasheet](https://www.espressif.com/sites/default/files/documentation/esp32-c6_datasheet_en.pdf): C6 Wi-Fi is 2.4 GHz. Chipset features do not establish the commercial PCB model, antenna wiring or flash capacity of the attached board.
- [ESP-IDF v5.5.4 C6 getting started](https://docs.espressif.com/projects/esp-idf/en/v5.5.4/esp32c6/get-started/index.html).
- [ESP-IDF v5.5.4 C6 Wi-Fi API](https://docs.espressif.com/projects/esp-idf/en/v5.5.4/esp32c6/api-reference/network/esp_wifi.html).
- [ESP-IDF repository](https://github.com/espressif/esp-idf).
- [Raspberry Pi 4 Model B specifications](https://www.raspberrypi.com/products/raspberry-pi-4-model-b/specifications/).
- [Raspberry Pi computer documentation](https://www.raspberrypi.com/documentation/computers/).

Installation evidence is recorded in [Hardware](HARDWARE.md): the host's device
tree reports Raspberry Pi 4 Model B Rev 1.2; the USB sensor was identified by
esptool as ESP32-C6 revision v0.0 and exercised with ESP-IDF v5.5.4. The hostname
`pi5` does not override the device-tree model. No authoritative board-level
product/schematic has been established for the attached C6.

## Optional C5 path — separate and unvalidated

- [C5 getting started](https://docs.espressif.com/projects/esp-idf/en/release-v5.5/esp32c5/get-started/index.html).
- [C5 Wi-Fi driver guide](https://docs.espressif.com/projects/esp-idf/en/release-v5.5/esp32c5/api-guides/wifi.html).
- [ESP-IDF chip/revision compatibility](https://github.com/espressif/esp-idf/blob/master/COMPATIBILITY.md).

Earlier eBeetle 2 / C5 references described an unverified candidate, not the
connected device. Qualify an actual C5 board, supported revision, USB console,
antenna, power and regulatory channels independently before deploying it. C5
capability must not be attributed to the C6.

## Vendor registry data

- [IEEE Registration Authority](https://standards.ieee.org/products-programs/regauth/) publishes MAC assignment registries.
- [MACLookup JSON database and field definitions](https://maclookup.app/downloads/json-database) supplies the bundled public prefix snapshot.
- [MACLookup API documentation](https://maclookup.app/api-v2/documentation) describes the additional prefix-only lookup fields and service limits.
- [MACLookup terms](https://maclookup.app/terms-and-conditions) describe data use and attribution.

The bundled MACLookup data is attributed to that provider, not represented as a
direct IEEE download. IEEE downloads were unavailable to this build host. Public
registry facts remain subject to the provider's terms rather than the project's
MIT source-code license. No observed full MAC is sent to the enrichment service.

## BLE monitoring and shared-radio coexistence

- [ESP-IDF v5.5.4 C6 RF coexistence](https://docs.espressif.com/projects/esp-idf/en/v5.5.4/esp32c6/api-guides/coexist.html): Wi-Fi sniffer RX and BLE scanning are classified as supported with unstable performance on the shared RF path.
- The tested toolchain's `examples/bluetooth/nimble/blecent/main/main.c` demonstrates NimBLE initialization and passive discovery parameters. This project's observer omits the example's connection/GATT behavior.

Project behavior, supported legacy advertisements, raw-data interpretation and
numeric company identifiers are documented in [BLE monitoring](BLE.md). The
local MAC prefix registry is not a Bluetooth company-identifier dataset.

## Readable BLE identifiers

- [Bluetooth SIG Assigned Numbers](https://www.bluetooth.com/specifications/assigned-numbers/) links the official registry sources and notices.
- [Official company identifier YAML](https://bitbucket.org/bluetooth-SIG/public/raw/HEAD/assigned_numbers/company_identifiers/company_identifiers.yaml).
- [Official standard service UUID YAML](https://bitbucket.org/bluetooth-SIG/public/raw/HEAD/assigned_numbers/uuids/service_uuids.yaml).

The explorer's offline snapshot records retrieval time and source digests.
Registry facts are separate from MAC registration and device/owner identity.
The RSSI distance curve is the documented mathematical model in [ranging](BLE_RANGING.md),
not a physical accuracy claim derived from those identifier registries.
