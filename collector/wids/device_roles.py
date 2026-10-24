"""Conservative device-role evidence from management subtypes and address relationships."""
ROLE_LABELS = {'access_point': 'Access Point', 'client': 'Client / Host',
               'mixed': 'Mixed (AP + Client)', 'unknown': 'Unknown'}
EVIDENCE_LABELS = {
    'beacons': 'Beacon advertisements sent',
    'probe_responses': 'Probe response advertisements sent',
    'association_requests': 'Association requests sent',
    'reassociation_requests': 'Reassociation requests sent',
    'association_responses': 'Association responses addressed here',
    'reassociation_responses': 'Reassociation responses addressed here',
}

# UNION deduplicates an address appearing in multiple header fields of one frame.
# A BSSID field alone, auth or disconnection frames do not establish device roles.
ROLE_QUERY = """
WITH recent AS (
    SELECT * FROM frames WHERE timestamp >= ? AND (? IS NULL OR sa=? OR da=? OR bssid=?)
), addresses AS (
    SELECT id,bssid AS mac FROM recent UNION SELECT id,sa FROM recent UNION SELECT id,da FROM recent
), observations AS (
    SELECT r.*,a.mac FROM addresses a JOIN recent r ON a.id=r.id
    WHERE a.mac != '00:00:00:00:00:00' AND instr('02468ace',substr(a.mac,2,1)) > 0
), grouped AS (
    SELECT mac,MAX(mac=sa) AS is_source,MAX(mac=da) AS is_destination,MAX(mac=bssid) AS is_bssid,
        json_group_array(DISTINCT CASE WHEN mac=bssid AND sa=bssid
            AND subtype IN ('beacon','probe_resp') THEN ssid END) AS ssids,
        json_group_array(DISTINCT CASE WHEN bssid != '00:00:00:00:00:00'
            AND instr('02468ace',substr(bssid,2,1)) > 0 THEN bssid END) AS bssids,
        json_group_array(DISTINCT channel) AS channels,
        json_group_array(DISTINCT sensor_id) AS sensor_ids,
        MIN(timestamp) AS first_seen,MAX(timestamp) AS last_seen,COUNT(*) AS frame_count,MAX(id) AS last_id,
        SUM(CASE WHEN mac=sa AND sa=bssid AND subtype='beacon' THEN 1 ELSE 0 END) AS beacons,
        SUM(CASE WHEN mac=sa AND sa=bssid AND subtype='probe_resp' THEN 1 ELSE 0 END) AS probe_responses,
        SUM(CASE WHEN mac=sa AND sa!=bssid AND da=bssid AND bssid!='00:00:00:00:00:00'
            AND instr('02468ace',substr(bssid,2,1))>0 AND subtype='assoc_req' THEN 1 ELSE 0 END) AS association_requests,
        SUM(CASE WHEN mac=sa AND sa!=bssid AND da=bssid AND bssid!='00:00:00:00:00:00'
            AND instr('02468ace',substr(bssid,2,1))>0 AND subtype='reassoc_req' THEN 1 ELSE 0 END) AS reassociation_requests,
        SUM(CASE WHEN mac=da AND da!=bssid AND sa=bssid AND bssid!='00:00:00:00:00:00'
            AND instr('02468ace',substr(bssid,2,1))>0 AND subtype='assoc_resp' THEN 1 ELSE 0 END) AS association_responses,
        SUM(CASE WHEN mac=da AND da!=bssid AND sa=bssid AND bssid!='00:00:00:00:00:00'
            AND instr('02468ace',substr(bssid,2,1))>0 AND subtype='reassoc_resp' THEN 1 ELSE 0 END) AS reassociation_responses
    FROM observations GROUP BY mac
), classified AS (
    SELECT *,CASE
        WHEN beacons+probe_responses>0 AND association_requests+reassociation_requests+association_responses+reassociation_responses>0 THEN 'mixed'
        WHEN beacons+probe_responses>0 THEN 'access_point'
        WHEN association_requests+reassociation_requests+association_responses+reassociation_responses>0 THEN 'client'
        ELSE 'unknown' END AS role_code
    FROM grouped
)
SELECT * FROM classified WHERE (?='all' OR role_code=?) AND (? IS NULL OR mac=?)
ORDER BY last_seen DESC,last_id DESC,mac LIMIT ?
"""


def classification(row=None):
    counts = {name: (row or {}).get(name, 0) for name in EVIDENCE_LABELS}
    code = (row or {}).get('role_code', 'unknown')
    evidence = [f'{label}: {counts[name]}' for name, label in EVIDENCE_LABELS.items() if counts[name]]
    if not evidence:
        evidence = ['Insufficient subtype/address evidence in the last 24 hours']
    return {'role_code': code, 'role': ROLE_LABELS[code], 'evidence': evidence,
            'evidence_counts': counts, 'window_hours': 24}
