# Upstream technical references (verified October 2026)

These are background references, not bundled SDK source.

1. **ESP-IDF C5 getting started (release/v5.5)**: https://docs.espressif.com/projects/esp-idf/en/release-v5.5/esp32c5/get-started/index.html
2. **ESP32-C5 Wi-Fi promiscuous APIs**: https://docs.espressif.com/projects/esp-idf/en/v5.5/esp32c5/api-reference/network/esp_wifi.html
3. **ESP32-C5 Wi-Fi driver guide, band mode and channel limits**: https://docs.espressif.com/projects/esp-idf/en/release-v5.5/esp32c5/api-guides/wifi.html
4. **Official ESP-IDF compatibility**, C5 revision v1.0/v1.2 >= v5.5.2: https://github.com/espressif/esp-idf/blob/master/COMPATIBILITY.md
5. **ESP32-C5 SoC support status**: https://developer.espressif.com/hardware/esp32c5/
6. **ESP-IDF repository / install**: https://github.com/espressif/esp-idf
7. **IEEE 802.11 protected management frames background**: https://www.wi-fi.org/discover-wi-fi/security

**Board qualification warning:** the exact product-name phrase "eBeetle 2 ESP32-C5 IoT Development Board" was not matched to an authoritative PCB reference/schematic during preparation. The firmware is deliberately designed around the verified ESP32-C5 SoC API and makes *no unverified board pinout claims*.

Consult the board vendor before committing to a production BOM, particularly for USB console, PCB antenna and power.
