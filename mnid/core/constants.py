"""Shared MNID constants and mutable live metadata caches."""

OK_C    = '#16A34A'
WARN_C  = '#FFC107'
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

# Live metadata is filled from the MAHIS dataframe during MNID rendering.
FACILITY_DISTRICT = {}
ALL_FACILITIES = []
ALL_DISTRICTS = []
FACILITY_COORDS = {}
FACILITY_NAMES = {}
