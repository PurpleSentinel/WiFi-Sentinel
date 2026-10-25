/* Deterministic host tests use the same bounded sampler as the Wi-Fi callback. */
#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
#include "beacon_sampler.h"

static void address(unsigned id, uint8_t mac[6])
{
    const uint8_t prefix[3] = {0x02, 0, 0};
    memcpy(mac, prefix, 3);
    mac[3] = (id >> 16) & 255;
    mac[4] = (id >> 8) & 255;
    mac[5] = id & 255;
}

int main(int argc, char **argv)
{
    if (argc < 2) return 2;
    wids_sampler_t sampler = {0};
    uint8_t mac[6];
    address(1, mac);
    if (!strcmp(argv[1], "periodic")) {
        if (argc != 5) return 2;
        unsigned aps = (unsigned)atoi(argv[2]);
        unsigned rounds = (unsigned)atoi(argv[3]);
        unsigned factor = (unsigned)atoi(argv[4]);
        if (!aps || aps > WIDS_SAMPLER_CAPACITY || !rounds || !factor || factor > 1000) return 2;
        unsigned counts[WIDS_SAMPLER_CAPACITY] = {0};
        for (unsigned i = 0; i < aps * rounds; i++) {
            unsigned ap = i % aps;
            address(ap + 1, mac);
            if (wids_sample_frame(&sampler, mac, 6, 8, factor)) counts[ap]++;
        }
        putchar('[');
        for (unsigned i = 0; i < aps; i++) printf("%s%u", i ? "," : "", counts[i]);
        puts("]");
    } else if (!strcmp(argv[1], "subtypes")) {
        unsigned seen[2] = {0}, selected[2] = {0};
        for (unsigned i = 0; i < 4000; i++) {
            unsigned kind = i % 21 == 0 ? 0 : 1;
            seen[kind]++;
            if (wids_sample_frame(&sampler, mac, 6, kind ? 5 : 8, 20)) selected[kind]++;
        }
        for (unsigned i = 0; i < 2; i++) assert(selected[i] == (seen[i] + 19) / 20);
        puts("true");
    } else if (!strcmp(argv[1], "settings")) {
        assert(wids_sample_frame(&sampler, mac, 6, 8, 20));
        assert(!wids_sample_frame(&sampler, mac, 6, 8, 20));
        assert(wids_sample_frame(&sampler, mac, 11, 8, 20));
        assert(!wids_sample_frame(&sampler, mac, 6, 8, 20));
        assert(wids_sample_frame(&sampler, mac, 6, 5, 20));
        assert(wids_sample_frame(&sampler, mac, 6, 8, 3));
        assert(!wids_sample_frame(&sampler, mac, 6, 8, 3));
        assert(!wids_sample_frame(&sampler, mac, 6, 8, 3));
        assert(wids_sample_frame(&sampler, mac, 6, 8, 3));
        assert(wids_sample_frame(&sampler, mac, 6, 8, 1));
        assert(wids_sample_frame(&sampler, mac, 6, 8, 1));
        assert(wids_sample_frame(&sampler, mac, 6, 8, 20));
        assert(wids_sample_frame(&sampler, mac, 6, 8, 0)); /* Defensive fail-open. */
        puts("true");
    } else if (!strcmp(argv[1], "eviction")) {
        for (unsigned i = 0; i < 100000; i++) {
            address(i, mac);
            assert(wids_sample_frame(&sampler, mac, 6, 8, 1000));
        }
        address(0, mac); /* An evicted AP reports immediately on returning. */
        assert(wids_sample_frame(&sampler, mac, 6, 8, 1000));
        assert(!wids_sample_frame(&sampler, mac, 6, 8, 1000));
        printf("{\"capacity\":%u,\"bytes\":%zu}\n", WIDS_SAMPLER_CAPACITY, sizeof(sampler));
    } else if (!strcmp(argv[1], "unsampled")) {
        const uint8_t subtypes[] = {0, 1, 2, 3, 10, 11, 12};
        for (unsigned i = 0; i < 1000; i++) {
            for (unsigned j = 0; j < sizeof(subtypes); j++)
                assert(wids_sample_frame(&sampler, mac, 6, subtypes[j], 1000));
        }
        for (unsigned i = 0; i < WIDS_SAMPLER_CAPACITY; i++) assert(!sampler.entries[i].used);
        puts("true");
    } else {
        return 2;
    }
    return 0;
}
