"""AeroCargo local practice API. Run: python server.py (Python 3.9+)."""
import argparse
import json
import math
import mimetypes
import os
import re
import threading
import uuid
from datetime import date, datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit
from shipment_importer import parse_shipment

ROOT = Path(__file__).resolve().parent
CARRIERS = [dict(name='Qatar Airways', code='QR', via='DOH', stops='1 Stop', days='3-4 Days', plane='Freighter', freight=1.34), dict(name='Air India', code='AI', via='SFO → DEL', stops='2 Stops', days='4-6 Days', plane='RFS', freight=1.54)]
FIELDS = {**dict.fromkeys(('pickup', 'origin', 'destination', 'dropoff', 'cargoType', 'commodity', 'unit', 'weightUnit', 'weightMode'), str), **dict.fromkeys(('known', 'stackable', 'pickupService'), bool), 'rows': list}
OPTIONAL = dict(aes=False, hawb=False, note='', reference='', flight='Wide body')


class APIError(Exception):
    def __init__(self, status, message, details=None):
        super().__init__(message)
        self.status, self.details = status, details or []


def validate(data):
    if not isinstance(data, dict):
        raise APIError(422, 'Shipment must be a JSON object')
    errors, result = [], {}

    def error(field, message):
        errors.append(dict(field=field, message=message))

    for key, kind in FIELDS.items():
        value = data.get(key)
        if type(value) is not kind:
            error(key, 'Required ' + kind.__name__)
            continue
        if kind is str:
            value = value.strip()
            if not 1 <= len(value) <= 500:
                error(key, 'Must contain 1–500 characters')
        result[key] = value
    for key, default in OPTIONAL.items():
        value = data.get(key, default)
        if type(value) is not type(default) or (isinstance(value, str) and len(value) > 5000):
            error(key, 'Invalid value')
        result[key] = value
    for key, values in dict(unit=['cm', 'in'], weightUnit=['kg', 'lb'], weightMode=['piece', 'gross'], cargoType=['General Cargo', 'Dangerous Goods', 'Perishable', 'Temperature Controlled', 'Live Animals']).items():
        if result.get(key) not in values:
            error(key, 'Use ' + ' or '.join(values))
    for key in ('origin', 'destination'):
        if key in result:
            result[key] = result[key].upper()
            if not re.fullmatch('[A-Z]{3}', result[key]):
                error(key, 'Use a 3-letter airport code')
    if 'dropoff' in result:
        try:
            if not re.fullmatch(r'\d{4}-\d{2}-\d{2}', result['dropoff']):
                raise ValueError()
            date.fromisoformat(result['dropoff'])
        except ValueError:
            error('dropoff', 'Use a valid YYYY-MM-DD date')
    if 'rows' in result:
        if not 1 <= len(result['rows']) <= 100:
            error('rows', 'Provide 1–100 cargo rows')
        clean = []
        for i, row in enumerate(result['rows']):
            item = {}
            for key in ('pieces', 'l', 'w', 'h', 'weight'):
                n = row.get(key) if isinstance(row, dict) else None
                if type(n) not in (int, float) or not 0 < n <= 1000000 or not math.isfinite(n) or (key == 'pieces' and int(n) != n):
                    error(f'rows.{i}.{key}', 'Use a positive number up to 1000000; pieces must be an integer')
                item[key] = n
            clean.append(item)
        result['rows'] = clean
    if errors:
        raise APIError(422, 'Shipment validation failed', errors)
    return result


def totals(s):
    pieces = gross = volume = 0
    for row in s['rows']:
        pieces += row['pieces']
        gross += row['weight'] * (2.20462262 if s['weightUnit'] == 'kg' else 1) * (row['pieces'] if s['weightMode'] == 'piece' else 1)
        f = 1 / 2.54 if s['unit'] == 'cm' else 1
        volume += row['l'] * row['w'] * row['h'] * f ** 3 * row['pieces'] / 366
    charge = max(gross, volume)
    return dict(pieces=pieces, gross=gross, volume=volume, charge=charge, kg=charge / 2.20462262)


def quotes(s):
    kg, result = totals(s)['kg'], []
    for carrier in CARRIERS:
        q = dict(carrier, screen=.18, edi=2.5, booking=17, pickup=190, awb=25, label=15)
        freight, screen = kg * q['freight'], kg * q['screen']
        air = freight + screen + q['edi'] + q['booking']
        inland = q['pickup'] + q['awb'] + q['label'] if s['pickupService'] else 0
        total = air + inland
        result.append(dict(q, pricing=dict(kg=kg, freight=freight, screen=screen, air=air, inland=inland, total=total, rate=total / kg), currency='USD', demo=True))
    return result


class Store:
    def __init__(self, directory):
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)
        self.file = self.directory / 'shipments.json'
        self.records = json.loads(self.file.read_text(encoding='utf-8')) if self.file.exists() else {}
        self.lock = threading.RLock()

    def save(self, shipment, shipment_id=None):
        with self.lock:
            if shipment_id and shipment_id not in self.records:
                raise APIError(404, 'Shipment not found')
            now = datetime.now(timezone.utc).isoformat()
            key = shipment_id or str(uuid.uuid4())
            record = dict(shipment, id=key, createdAt=self.records[key]['createdAt'] if shipment_id else now, updatedAt=now, totals=totals(shipment))
            next_records = dict(self.records, **{key: record})
            temp = self.file.with_suffix('.tmp')
            temp.write_text(json.dumps(next_records, indent=2, allow_nan=False), encoding='utf-8')
            os.replace(temp, self.file)
            self.records = next_records
            return record


class Handler(BaseHTTPRequestHandler):
    def json_response(self, status, payload, headers=None):
        raw = json.dumps(payload, ensure_ascii=False, allow_nan=False).encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(raw)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        for key, value in (headers or {}).items():
            self.send_header(key, value)
        self.end_headers()
        self.wfile.write(raw)

    def read_json(self):
        if self.headers.get_content_type() != 'application/json':
            raise APIError(415, 'Content-Type must be application/json')
        if self.headers.get('Transfer-Encoding'):
            raise APIError(400, 'Use Content-Length, not Transfer-Encoding')
        try:
            size = int(self.headers.get('Content-Length', '0'))
        except ValueError:
            raise APIError(400, 'Invalid Content-Length')
        if size > 65536:
            raise APIError(413, 'Request body exceeds 64 KB')
        if size <= 0:
            raise APIError(400, 'JSON body is required')
        try:
            return json.loads(self.rfile.read(size).decode('utf-8'), parse_constant=lambda _: (_ for _ in ()).throw(ValueError()))
        except (ValueError, UnicodeError):
            raise APIError(400, 'Invalid JSON body')

    def dispatch(self):
        try:
            origin = self.headers.get('Origin')
            port = self.server.server_port
            if origin and origin not in (f'http://127.0.0.1:{port}', f'http://localhost:{port}'):
                raise APIError(403, 'Cross-origin requests are not allowed')
            p, method, store = urlsplit(self.path).path, self.command, self.server.store
            if p == '/api/health' and method == 'GET':
                return self.json_response(200, dict(status='ok', demo=True))
            if p == '/api/shipments/import' and method == 'POST':
                data = self.read_json()
                text = data.get('text') if isinstance(data, dict) else None
                if not isinstance(text, str) or not text.strip() or len(text) > 20000:
                    raise APIError(422, 'text must contain 1–20000 characters')
                return self.json_response(200, parse_shipment(text))
            if p == '/api/shipments':
                if method == 'GET':
                    with store.lock:
                        records = list(store.records.values())
                    return self.json_response(200, dict(shipments=records))
                if method == 'POST':
                    record = store.save(validate(self.read_json()))
                    return self.json_response(201, record, {'Location': '/api/shipments/' + record['id']})
            match = re.fullmatch(r'/api/shipments/([^/]+)(/quotes)?', p)
            if match:
                key = match[1]
                with store.lock:
                    record = store.records.get(key)
                if record is None:
                    raise APIError(404, 'Shipment not found')
                if method == 'GET':
                    return self.json_response(200, dict(shipmentId=key, quotes=quotes(record)) if match[2] else record)
                if method == 'PUT' and not match[2]:
                    return self.json_response(200, store.save(validate(self.read_json()), key))
                raise APIError(405, 'Method not allowed')
            if p.startswith('/api/'):
                raise APIError(405 if p in ('/api/health', '/api/shipments', '/api/shipments/import') else 404, 'Endpoint or method not supported')
            files = {'/': 'index.html', '/index.html': 'index.html', '/app.js': 'app.js', '/importer.js': 'importer.js', '/api-client.js': 'api-client.js', '/style.css': 'style.css', '/assets/cargo-plane.jpg': 'assets/cargo-plane.jpg', '/docs': 'docs.html', '/openapi.json': 'openapi.json'}
            if method != 'GET' or p not in files:
                raise APIError(404, 'Not found')
            name = files[p]
            raw = (ROOT / name).read_bytes()
            mime = 'text/javascript' if name.endswith('.js') else mimetypes.guess_type(name)[0] or 'application/octet-stream'
            self.send_response(200)
            self.send_header('Content-Type', mime)
            self.send_header('Content-Length', str(len(raw)))
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.end_headers()
            self.wfile.write(raw)
        except APIError as exc:
            self.json_response(exc.status, dict(error=dict(message=str(exc), details=exc.details)))
        except (BrokenPipeError, ConnectionResetError):
            pass
        except Exception:
            self.json_response(500, dict(error=dict(message='Internal server error', details=[])))

    do_GET = do_POST = do_PUT = do_DELETE = do_PATCH = do_OPTIONS = dispatch

    def log_message(self, fmt, *args):
        # Avoid logging pasted text, query strings or other request data.
        pass


def create_server(port=8000, data_dir=None):
    store = Store(data_dir or ROOT / 'data')
    server = ThreadingHTTPServer(('127.0.0.1', port), Handler)
    server.store = store
    return server


def main():
    parser = argparse.ArgumentParser(description='Start the local AeroCargo portal and API')
    parser.add_argument('--port', type=int, default=8000)
    args = parser.parse_args()
    try:
        server = create_server(args.port)
    except OSError as exc:
        parser.exit(1, f'Could not start server: {exc}\nTry: python server.py --port 8001\n')
    print(f'AeroCargo: http://127.0.0.1:{args.port}\nAPI docs: http://127.0.0.1:{args.port}/docs\nKeep this terminal open. Press Ctrl+C to stop.', flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print('\nServer stopped.')
    finally:
        server.server_close()


if __name__ == '__main__':
    main()
