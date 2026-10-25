#ifndef WIDS_BEACON_SAMPLER_H
#define WIDS_BEACON_SAMPLER_H

#include <stdbool.h>
#include <stdint.h>
#include <string.h>

#define WIDS_SAMPLER_CAPACITY 64

typedef struct {
    uint8_t bssid[6];
    uint8_t channel;
    bool used;
    uint16_t factor;
    uint16_t remaining[2];  /* Beacon and probe-response counters are independent. */
} wids_sample_entry_t;

typedef struct {
    wids_sample_entry_t entries[WIDS_SAMPLER_CAPACITY];
    uint8_t replacement;
} wids_sampler_t;

/* Owned only by the Wi-Fi RX task: fixed memory, bounded scan, no I/O or allocation.
 * First sighting is reported, then every Nth observation for that BSSID/channel/type.
 * FIFO eviction increases reports under churn; it never suppresses a new identity.
 */
static inline bool wids_sample_frame(wids_sampler_t *sampler, const uint8_t bssid[6],
                                     uint8_t channel, uint8_t subtype, uint16_t factor)
{
    if (subtype != 8 && subtype != 5) return true;
    if (!factor) factor = 1;
    wids_sample_entry_t *entry = NULL;
    unsigned free_slot = WIDS_SAMPLER_CAPACITY;
    for (unsigned i = 0; i < WIDS_SAMPLER_CAPACITY; i++) {
        wids_sample_entry_t *candidate = &sampler->entries[i];
        if (candidate->used) {
            if (candidate->channel == channel && !memcmp(candidate->bssid, bssid, 6)) {
                entry = candidate;
                break;
            }
        } else if (free_slot == WIDS_SAMPLER_CAPACITY) {
            free_slot = i;
        }
    }
    if (!entry) {
        unsigned slot = free_slot;
        if (slot == WIDS_SAMPLER_CAPACITY) {
            slot = sampler->replacement;
            sampler->replacement = (sampler->replacement + 1) % WIDS_SAMPLER_CAPACITY;
        }
        entry = &sampler->entries[slot];
        *entry = (wids_sample_entry_t){.channel = channel, .used = true, .factor = factor};
        memcpy(entry->bssid, bssid, 6);
    }
    if (entry->factor != factor) {
        entry->factor = factor;
        entry->remaining[0] = entry->remaining[1] = 0;
    }
    unsigned kind = subtype == 8 ? 0 : 1;
    if (entry->remaining[kind]) {
        entry->remaining[kind]--;
        return false;
    }
    entry->remaining[kind] = factor - 1;
    return true;
}

#endif
