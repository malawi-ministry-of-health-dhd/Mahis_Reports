"""Shared MNID constants and metadata."""

OK_C    = '#16A34A'
WARN_C  = '#CA8A04'
DANGER_C = '#DC2626'
INFO_C  = '#475569'
MUTED   = '#94A3B8'
GRID_C  = '#F1F5F9'
BG      = '#fff'
BORDER  = '#E2E8F0'
TEXT    = '#0F172A'
DIM     = '#64748B'
FONT    = '-apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif'

CAT_PALETTES = {
    'ANC':     ['#15803D', '#22C55E', '#4ADE80', '#86EFAC', '#BBF7D0', '#14532D'],
    'Labour':  ['#BA7517', '#D4881A', '#E8A830', '#F5C658', '#FAD97A', '#7C4D0A', '#A35F10'],
    'Newborn': ['#0D9488', '#14B8A6', '#2DD4BF', '#5EEAD4', '#99F6E4', '#0F766E', '#0E7490'],
    'PNC':     ['#7C3AED', '#9D5CF0', '#B683F4', '#CFAAF8'],
}

HEATMAP_CS = [
    [0.00, DANGER_C],
    [0.6499, DANGER_C],
    [0.65, WARN_C],
    [0.7999, WARN_C],
    [0.80, OK_C],
    [1.00, OK_C],
]

FACILITY_DISTRICT = {
    'LL040033': 'Lilongwe',
    'MZ120004': 'Mzuzu',
    'BL050022': 'Blantyre',
    'BT020011': 'Lilongwe',
    'KS010001': 'Kasungu',
    'SL020001': 'Salima',
    'ZO030001': 'Zomba',
    'NT080001': 'Ntcheu',
    'KR060001': 'Karonga',
    'RP070001': 'Rumphi',
    'LL040099': 'Lilongwe',
    'BL050099': 'Blantyre',
}

ALL_FACILITIES = [
    'LL040033', 'LL040099', 'BT020011',
    'MZ120004', 'KR060001', 'RP070001',
    'BL050022', 'BL050099', 'ZO030001',
    'KS010001', 'SL020001', 'NT080001',
]

ALL_DISTRICTS = [
    'Karonga', 'Rumphi', 'Mzuzu',
    'Kasungu', 'Lilongwe', 'Salima',
    'Ntcheu', 'Zomba', 'Blantyre',
]

FACILITY_COORDS = {
    'LL040033': (-13.9626, 33.7741, 'Lilongwe Central Hospital', 'Lilongwe'),
    'LL040099': (-13.9500, 33.7800, 'Kamuzu Central Hospital', 'Lilongwe'),
    'BT020011': (-13.9780, 33.7853, 'Bwaila District Hospital', 'Lilongwe'),
    'MZ120004': (-11.4534, 34.0192, 'Mzuzu Urban Health Centre', 'Mzuzu'),
    'BL050022': (-15.7861, 35.0058, 'Blantyre South Health Centre', 'Blantyre'),
    'BL050099': (-15.7800, 35.0200, 'Queen Elizabeth CH', 'Blantyre'),
    'KS010001': (-13.0147, 33.4800, 'Kasungu District Hospital', 'Kasungu'),
    'SL020001': (-13.7833, 34.4500, 'Salima District Hospital', 'Salima'),
    'ZO030001': (-15.3833, 35.3167, 'Zomba Central Hospital', 'Zomba'),
    'NT080001': (-14.9833, 34.6333, 'Ntcheu District Hospital', 'Ntcheu'),
    'KR060001': (-9.9333, 33.9667, 'Karonga District Hospital', 'Karonga'),
    'RP070001': (-10.7833, 34.0333, 'Rumphi District Hospital', 'Rumphi'),
}

FACILITY_NAMES = {k: v[2] for k, v in FACILITY_COORDS.items()}

