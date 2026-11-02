"""Painel local: python dashboard.py (http://127.0.0.1:8765)."""
import csv
import json
from pathlib import Path
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

ROOT = Path(__file__).resolve().parent


def load_receipts():
    receipts = []
    for folder in sorted((ROOT / 'captures').glob('*'), reverse=True):
        digital = folder / 'itens_digitais.csv'
        source = digital if digital.exists() else folder / 'analise_itens.csv'
        if not source.exists():
            continue
        with source.open(encoding='utf-8-sig', newline='') as file:
            rows = list(csv.DictReader(file, delimiter=';'))
        items = []
        def number(value):
            try:
                return float(value.replace(',', '.')) if value else None
            except ValueError:
                return None
        for i, row in enumerate(rows):
            gross = number(row.get('valor_bruto', row.get('valor_total', '')))
            discount = number(row.get('desconto', '0')) or 0
            items.append(dict(id=i, name=row.get('produto', row.get('item', '')), quantity=number(row.get('quantidade')), unit=row.get('unidade', ''), cost=None if gross is None else gross-discount))
        receipts.append(dict(id=folder.name, source='QR Code' if digital.exists() else 'Scanning / OCR', items=items))
    return receipts


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(ROOT / 'dashboard'), **kwargs)

    def do_GET(self):
        if self.path == '/api/receipts':
            body = json.dumps(load_receipts(), ensure_ascii=False).encode()
            self.send_response(200)
            self.send_header('Content-Type', 'application/json; charset=utf-8')
            self.send_header('Cache-Control', 'no-store')
            self.end_headers()
            self.wfile.write(body)
        else:
            super().do_GET()


if __name__ == '__main__':
    print('Painel da compra: http://127.0.0.1:8765 | Ctrl+C para encerrar', flush=True)
    ThreadingHTTPServer(('127.0.0.1', 8765), Handler).serve_forever()
