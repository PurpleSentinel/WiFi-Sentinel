# Approximate BLE RSSI distance-decay plot

Implemented after Release 1.2 for issue #28, alongside the
[BLE advertiser explorer](BLE_EXPLORER.md). No new RF transmission or firmware
feature is required. This plot is an illustrative propagation model, **not
precise ranging, location tracking or authenticated device identification**.

## Select an advertiser

Open BLE and select an advertiser's label or the sensor/address/type selector.
The workspace plots a logarithmic RSSI decay curve, using distance in **metres**
on the horizontal axis and expected received signal strength in **dBm** vertically.
Only that sensor/address/type's latest 100 retained observations are loaded.
Different sensors and rotating addresses are never combined into one range trace.

The blue curve is the assumed model. An amber marker shows the latest raw RSSI
mapped through it; a green marker shows the median when smoothing is enabled.
Markers have tooltips. A textual equivalent below the chart includes RSSI,
approximate distances, sample time, sample count, assumptions and calibration.
An out-of-range estimate is shown numerically and labelled; its marker is omitted
rather than silently clamped to the plot edge.

## Model and controls

```text
RSSI(d) = A - 10 × n × log10(d / 1 metre)
approximate distance (metres) = 10 ^ ((A - RSSI) / (10 × n))
```

| Control | Initial assumption | Allowed |
|---|---|---|
| Reference RSSI A at 1 metre | -59 dBm | -127 to 20 dBm |
| Path-loss exponent n | 2 | 0.1–10 |
| Plot minimum distance | 0.1 m | 0.01–10000 m |
| Plot maximum distance | 30 m | Greater than minimum, up to 100000 m |
| Median window | 0 seconds (raw only) | Integer 0–3600 seconds |
| Measured-reference checkbox | Off | Operator assertion only |

These defaults are **uncalibrated illustrative values**, not validated for the
observed transmitter or room. Non-finite/missing values, invalid bounds and
non-positive exponents/distances are rejected, and invalid plots are cleared.
Changing controls updates the model; it does not reconfigure the sensor.

Settings stay in this browser session, separately per selected identity, with at
most 200 model configurations retained. They are not persisted in SQLite or
applied to other advertisers. Changing sensors/addresses gets independent
assumptions. A page reload discards them.

## Calibration

For a known transmitter, take representative received measurements with that
transmitter and receiver at a known **1-metre** separation, in the intended
placement/orientation. Enter the measured reference and an explicitly chosen
path-loss exponent. Record the conditions and assumptions, for example in your
protected operator notes. The checkbox only indicates that you supplied a
measurement; the application cannot verify the calibration or its accuracy.
An advertised Tx Power field is **never** substituted for a measured 1-metre RSSI.

Walls, reflections/multipath, antenna orientation, transmitter power changes,
receiver differences and shared-radio losses can dominate this estimate. Changing
the environment can invalidate the calibration. No confidence interval, verified
position or accuracy guarantee is produced.

## Smoothing, freshness and Pause

With window 0, the representative value is the latest raw report. A positive
window uses the median of fetched samples whose host receive timestamps fall
within that many seconds before the latest refresh. Both raw and median RSSI
and approximate distance are shown. If the window contains no samples, the
median estimate is unavailable; a stale raw report is still explicitly labelled.
The window can be incomplete because only 100 retained, filtered reports are
fetched and duplicate suppression may have removed many advertisements.

Samples older than **60 seconds** are labelled stale. This is freshness of stored
reports, not proof the transmitter is absent; capture, filtering and deduplication
can affect it. Missing samples produce an unavailable estimate. Future-timestamp
samples are excluded. Host UTC receive time is not authenticated RF capture time.

Pause freezes the sample set and its time reference. Model inputs can still
recompute from that frozen evidence without a new read. Selecting another
identity while paused clears old samples and requires Refresh/Resume, preventing
accidental reuse of the previous advertiser's RSSI.

## What has been tested

Mathematical fixtures with A=-59 and n=2 map -59 dBm to 1 metre and -79 dBm to
10 metres. Browser checks cover medians, missing/stale samples, invalid inputs,
out-of-range estimates, sensor separation, pause and mobile layout. These are
model/software tests; they do **not** validate physical distance accuracy.
No controlled RF calibration or independent ranging experiment is claimed.
