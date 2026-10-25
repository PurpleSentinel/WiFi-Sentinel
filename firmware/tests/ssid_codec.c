/* Host-side integration harness using the firmware's actual SSID codec. */
#include <stdlib.h>
#include "ssid_codec.h"

int main(int argc, char **argv)
{
    if (argc != 2) return 2;
    size_t digits = strlen(argv[1]);
    if (digits % 2 || digits > 2048) return 2;
    uint8_t frame[1024];
    for (size_t i = 0; i < digits / 2; i++) {
        unsigned value;
        if (sscanf(argv[1] + i * 2, "%2x", &value) != 1) return 2;
        frame[i] = value;
    }
    uint8_t ssid[WIDS_SSID_MAX_LEN];
    uint8_t length;
    bool present = wids_extract_ssid(frame, digits / 2, ssid, &length);
    printf("WIDS {\"v\":1,\"kind\":\"frame\",\"sensor_id\":\"codec-test\","
           "\"channel\":6,\"subtype\":\"beacon\",\"sa\":\"00:11:22:33:44:55\","
           "\"da\":\"ff:ff:ff:ff:ff:ff\",\"bssid\":\"00:11:22:33:44:55\","
           "\"rssi\":-40,\"protected\":false,\"ssid\":null,\"ssid_hex\":");
    wids_write_ssid_hex(stdout, ssid, length, present);
    puts("}");
    return 0;
}
