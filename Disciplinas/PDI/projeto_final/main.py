from livefeed import livefeed
from receipt_processor import process_session, write_analysis_table

DROIDCAM_URL = "http://192.168.1.102:4747/video"


def scanning() -> None:
    session = livefeed(DROIDCAM_URL, mirror=False)
    if session is None:
        return
    print(f"[OCR] Processando as fotos de {session}...", flush=True)
    try:
        receipt = process_session(session)
        csv_path, _ = write_analysis_table(receipt, session)
    except (RuntimeError, OSError) as error:
        print(f"[OCR] Falha: {error}. Fotos preservadas em {session}.", flush=True)
        return
    print(f"[OCR] {len(receipt.items)} itens identificados. CSV: {csv_path.resolve()}", flush=True)
    if not receipt.items:
        print("[OCR] Nenhum item identificado; confira as fotos e o texto extraido.", flush=True)


def main() -> None:
    while True:
        method = input("Metodo de obtencao: 1 - scanning | 2 - QR Code | q - sair: ").strip().lower()
        if method in ("1", "scanning"):
            scanning()
            return
        if method in ("2", "qr", "qrcode", "qr code"):
            from nfce_reader import read_qr, import_nfce
            try:
                url = read_qr(DROIDCAM_URL)
                if url:
                    print("[QR] Consultando a SEFAZ...", flush=True)
                    csv_path = import_nfce(url)
                    print(f"[QR] CSV: {csv_path.resolve()}")
            except (RuntimeError, ValueError, OSError) as error:
                print(f"[QR] Falha na importacao: {error}", flush=True)
            return
        if method == "q":
            return
        print("Escolha scanning ou QR Code.")


if __name__ == "__main__":
    main()
