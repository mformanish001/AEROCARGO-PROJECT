"""Rule-based shipment text import; returns partial fields for user review."""
import re
from datetime import date


def parse_shipment(text):
    patch, found, warnings = {}, [], []

    def put(key, value, label=None):
        patch[key] = value
        found.append(label or key)

    def line(labels):
        match = re.search(r'(?:^|\n)\s*(?:' + labels + r')\s*:\s*([^\n]+)', text, re.I)
        return match[1].strip() if match else None

    route = re.search(r'(?:air\s*freight\s+)?from\s+([^\n]+?)\s+to\s+([^\n]+)', text, re.I)
    pickup = line(r'pickup(?: address)?') or (route[1].strip() if route else None)
    destination = line(r'destination(?: airport)?') or (route[2].strip() if route else None)
    origin = line(r'origin(?: airport)?')
    if pickup:
        put('pickup', pickup)
    if destination:
        put('destination', destination.upper())
    if origin:
        put('origin', origin.upper())
    elif pickup and re.fullmatch('[A-Za-z]{3}', pickup):
        put('origin', pickup.upper())
    for key, label in [('commodity', 'commodity'), ('cargoType', 'cargo type')]:
        value = line(label)
        if value:
            put(key, value)
    value = line(r'expected drop[ -]?off(?: date)?|drop[ -]?off(?: date)?')
    if value:
        match = re.fullmatch(r'(\d{2})[-/](\d{2})[-/](\d{4})', value)
        if match:
            value = f'{match[3]}-{match[2]}-{match[1]}'
        try:
            if not re.fullmatch(r'\d{4}-\d{2}-\d{2}', value):
                raise ValueError()
            date.fromisoformat(value)
            put('dropoff', value)
        except ValueError:
            warnings.append('Enter a valid drop-off date (DD-MM-YYYY or YYYY-MM-DD).')
    for key, negative, positive in [
        ('known', r'\b(?:unknown|not known) shipper\b|known shipper\s*:\s*no\b', r'\bknown shipper\b'),
        ('stackable', r'\bnon[ -]?stackable\b|\bnot stackable\b|stackable\s*:\s*no\b', r'\bstackable\b'),
    ]:
        if re.search(negative, text, re.I):
            put(key, False)
        elif re.search(positive, text, re.I):
            put(key, True)
    handling = line(r'handling\s*/\s*packing|handling|packing')
    if handling and handling.lower() in ('yes', 'no'):
        put('stackable', handling.lower() == 'yes')
    declared = line('units') or ''
    du = line('dimension units?|length units?')
    wu = line('weight units?')
    if not du:
        match = re.search(r'\b(cm|inches|inch|in)\b', declared, re.I)
        du = match[1] if match else None
    if not wu:
        match = re.search(r'\b(kg|kgs|lb|lbs)\b', declared, re.I)
        wu = match[1] if match else None
    if du:
        if du.lower() in ('cm', 'in', 'inch', 'inches'):
            put('unit', 'cm' if du.lower() == 'cm' else 'in')
        else:
            warnings.append('Unrecognized dimension unit; select cm or in.')
            du = None
    if wu:
        if wu.lower() in ('kg', 'kgs', 'lb', 'lbs'):
            put('weightUnit', 'kg' if wu.lower().startswith('k') else 'lb')
        else:
            warnings.append('Unrecognized weight unit; select kg or lb.')
            wu = None
    mode = line('weight mode')
    if mode and mode.lower() in ('piece', 'gross'):
        put('weightMode', mode.lower())
    pieces = re.search(r'(?:number of pieces|total pieces|pieces|pcs)\s*:\s*([\d,]+)', text, re.I)
    weight = re.search(r'(?:^|\n)\s*(gross weight|total weight|weight per piece|weight)\s*:\s*([\d,.]+)\s*(kg|kgs|kilograms?|lb|lbs|pounds?)\b', text, re.I)
    if not weight and wu:
        weight = re.search(r'(?:^|\n)\s*(gross weight|total weight|weight per piece|weight)\s*:\s*([\d,.]+)\s*(?=\n|$)', text, re.I)
    dims = [list(m.groups()) for m in re.finditer(r'(?:(\d+)\s*(?:pcs?|pieces?|pallets?)?\s*[@:]\s*)?(\d+(?:\.\d+)?)\s*[x×*]\s*(\d+(?:\.\d+)?)\s*[x×*]\s*(\d+(?:\.\d+)?)\s*(cm|inches|inch|in)?\b', text, re.I)]
    if not dims:
        values = [line(k) for k in ('length', 'width', 'height')]
        parsed = [re.fullmatch(r'(\d+(?:\.\d+)?)(?:\s*(cm|in|inches))?', v, re.I) if v else None for v in values]
        if all(parsed):
            units = {'cm' if m[2].lower() == 'cm' else 'in' for m in parsed if m[2]}
            if len(units) > 1:
                warnings.append('Mixed length, width and height units; enter dimensions manually.')
            else:
                dims = [[None, *[m[1] for m in parsed], next(iter(units), du)]]
    if pieces or weight or dims:
        units = {'cm' if d[4].lower() == 'cm' else 'in' for d in dims if d[4]}
        unit = next(iter(units)) if len(units) == 1 else patch.get('unit')
        count = int(pieces[1].replace(',', '')) if pieces else None
        if count is not None and count < 1:
            warnings.append('Piece count must be positive; enter a valid count.')
        rows = [dict(pieces=int(d[0]) if d[0] else (count or 1) if len(dims) == 1 else 1, l=float(d[1]), w=float(d[2]), h=float(d[3]), weight='') for d in dims] if dims else [dict(pieces=count or 1, l='', w='', h='', weight='')]
        if len(units) > 1:
            warnings.append('Mixed dimension units; enter dimensions manually.')
            for row in rows:
                row.update(l='', w='', h='')
        if not unit and dims:
            warnings.append('Dimension units missing; check the selected unit.')
        if unit:
            put('unit', unit)
        if weight:
            weight_unit = weight[3] if weight.lastindex == 3 else wu
            put('weightUnit', 'kg' if weight_unit.lower().startswith('k') else 'lb')
            try:
                amount = float(weight[2].replace(',', ''))
            except ValueError:
                amount = None
            if amount is None or amount <= 0:
                warnings.append('Enter a valid positive weight.')
            elif len(rows) == 1:
                per_piece = weight[1].lower() == 'weight per piece'
                mode = patch.get('weightMode', 'piece' if per_piece else 'gross')
                count = rows[0]['pieces']
                rows[0]['weight'] = (amount * count if per_piece else amount) if mode == 'gross' else (amount if per_piece else amount / count)
                put('weightMode', mode)
            else:
                warnings.append('Enter weight per piece for each cargo row; total weight cannot identify row weights.')
        if not dims:
            warnings.append('Dimensions missing; enter length, width and height.')
        if not weight:
            warnings.append('Gross weight missing; enter weight and unit.')
        if not pieces and not any(d[0] for d in dims):
            warnings.append('Piece count missing; check the default of 1 per row.')
        put('rows', rows, 'cargo details')
    return dict(patch=patch, found=found, warnings=warnings)
