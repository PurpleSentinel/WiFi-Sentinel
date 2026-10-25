#ifndef WIDS_SSID_CODEC_H
#define WIDS_SSID_CODEC_H

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>

#define WIDS_SSID_MAX_LEN 32

/* Beacons/probe responses: 24-byte management header + 12 fixed bytes. */
static inline bool wids_extract_ssid(const uint8_t *data, size_t length,
                                     uint8_t out[WIDS_SSID_MAX_LEN], uint8_t *out_length)
{
    *out_length = 0;
    size_t position = 36;
    while (position + 2 <= length) {
        uint8_t id = data[position++];
        uint8_t size = data[position++];
        if (size > length - position) return false;
        if (id == 0) {
            if (size > WIDS_SSID_MAX_LEN) return false;
            memcpy(out, data + position, size);
            *out_length = size;
            return true;
        }
        position += size;
    }
    return false;
}

/* Hex preserves arbitrary bytes, including NUL, without JSON/UTF-8 ambiguity. */
static inline void wids_write_ssid_hex(FILE *stream, const uint8_t *ssid,
                                      size_t length, bool present)
{
    if (!present || length > WIDS_SSID_MAX_LEN) {
        fputs("null", stream);
        return;
    }
    fputc('"', stream);
    for (size_t i = 0; i < length; i++) fprintf(stream, "%02x", (unsigned)ssid[i]);
    fputc('"', stream);
}

#endif
