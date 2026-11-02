"""Leitura do QR Code e importacao da consulta NFC-e de Pernambuco."""
from datetime import datetime
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit, quote
from urllib.request import urlopen
import xml.etree.ElementTree as ET
import csv
import cv2
from receipt_processor import Receipt, ReceiptItem, _category, write_analysis_table

NS = {'n': 'http://www.portalfiscal.inf.br/nfe'}


def normalize_url(url: str) -> str:
    parts = urlsplit(url.strip())
    if parts.scheme not in ('http', 'https') or parts.hostname != 'nfce.sefaz.pe.gov.br' or parts.path != '/nfce-web/consultarNFCe':
        raise ValueError('QR Code nao corresponde a consulta NFC-e de Pernambuco suportada.')
    return urlunsplit(('https', 'nfce.sefaz.pe.gov.br:444', parts.path, quote(parts.query, safe='=%&'), ''))


def read_qr(camera_source: int | str) -> str | None:
    camera = cv2.VideoCapture(camera_source)
    window = 'QR Code da nota | q: sair'
    detector = cv2.QRCodeDetector()
    try:
        if not camera.isOpened():
            raise RuntimeError('Nao foi possivel abrir a camera.')
        while True:
            success, frame = camera.read()
            if not success:
                raise RuntimeError('Nao foi possivel ler a camera.')
            data, points, _ = detector.detectAndDecode(frame)
            if points is not None:
                cv2.polylines(frame, [points.astype('int32').reshape(-1, 2)], True, (0, 255, 0), 2)
            cv2.imshow(window, frame)
            if data:
                try:
                    return normalize_url(data)
                except ValueError:
                    print('[QR] Aponte para um QR Code de NFC-e de Pernambuco.')
            if cv2.waitKey(1) & 0xFF == ord('q') or cv2.getWindowProperty(window, cv2.WND_PROP_VISIBLE) < 1:
                return None
    finally:
        camera.release()
        cv2.destroyAllWindows()


def parse_nfce(data: bytes) -> Receipt:
    try:
        root = ET.fromstring(data)
    except ET.ParseError as error:
        raise ValueError('Resposta sem XML da nota: consulta indisponivel ou requer acesso pelo navegador.') from error
    info = root.find('.//n:infNFe', NS)
    if info is None:
        raise ValueError('A consulta nao retornou os dados da NFC-e.')
    def value(node, path):
        result = node.findtext(path, namespaces=NS)
        if result is None:
            raise ValueError(f'Campo obrigatorio ausente: {path}')
        return result
    items = []
    for detail in info.findall('n:det', NS):
        prod = detail.find('n:prod', NS)
        if prod is None:
            raise ValueError('Item sem produto na resposta.')
        name = value(prod, 'n:xProd')
        items.append(ReceiptItem(name, float(value(prod, 'n:qCom')), value(prod, 'n:uCom'),
                                 float(value(prod, 'n:vUnCom')), float(value(prod, 'n:vProd')),
                                 _category(name), 'digital', f"Item {detail.get('nItem')}: {name}"))
    if not items:
        raise ValueError('Nota sem itens.')
    return Receipt(value(info, 'n:emit/n:xNome'), value(info, 'n:ide/n:dhEmi'),
                   float(value(info, 'n:total/n:ICMSTot/n:vNF')), items,
                   data.decode('utf-8'), len(items))


def export_nfce(data: bytes, directory: Path) -> Path:
    receipt = parse_nfce(data)
    directory.mkdir(parents=True, exist_ok=True)
    (directory / 'nota.xml').write_bytes(data)
    csv_path, _ = write_analysis_table(receipt, directory)
    # Exportacao adicional preserva codigo, numero do item e descontos monetarios.
    root = ET.fromstring(data)
    with (directory / 'itens_digitais.csv').open('w', newline='', encoding='utf-8-sig') as file:
        writer = csv.writer(file, delimiter=';')
        writer.writerow(['numero', 'codigo', 'produto', 'quantidade', 'unidade', 'preco_unitario', 'valor_bruto', 'desconto'])
        for detail in root.findall('.//n:infNFe/n:det', NS):
            prod = detail.find('n:prod', NS)
            writer.writerow([detail.get('nItem')] + [prod.findtext('n:' + key, default='0' if key == 'vDesc' else '', namespaces=NS)
                             for key in ('cProd', 'xProd', 'qCom', 'uCom', 'vUnCom', 'vProd', 'vDesc')])
    print(f'[QR] {len(receipt.items)} itens. Total da nota: R$ {receipt.total:.2f}')
    return csv_path


def import_nfce(url: str) -> Path:
    url = normalize_url(url)
    with urlopen(url, timeout=30) as response:
        data = response.read()
    directory = Path('captures') / datetime.now().strftime('qrcode_%Y%m%d_%H%M%S_%f')
    csv_path = export_nfce(data, directory)
    (directory / 'origem.txt').write_text(url, encoding='utf-8')
    return csv_path
