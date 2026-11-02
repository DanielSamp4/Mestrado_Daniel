"""Processa uma sessao de captura e opcionalmente salva a compra no SQLite."""

import argparse
import json
from pathlib import Path

from receipt_database import save_receipt
from receipt_processor import process_session, receipt_as_dict, write_analysis_table


def main() -> None:
    parser = argparse.ArgumentParser(description="Faz OCR e extrai dados de uma nota capturada.")
    parser.add_argument("session", type=Path, help="Pasta nota_... criada pelo main.py")
    parser.add_argument("--lang", default="por", help="Idioma do Tesseract (padrao: por)")
    parser.add_argument("--save", action="store_true", help="Salva o resultado em purchases.sqlite3")
    parser.add_argument("--json", action="store_true", help="Tambem mostra o resultado tecnico em JSON")
    args = parser.parse_args()
    receipt = process_session(args.session, args.lang)
    csv_path, markdown_path = write_analysis_table(receipt, args.session)
    print(f"Tabela CSV: {csv_path}")
    print(f"Tabela Markdown: {markdown_path}")
    print(f"Itens identificados: {len(receipt.items)}")
    if args.json:
        print(json.dumps(receipt_as_dict(receipt), ensure_ascii=False, indent=2))
    if args.save:
        purchase_id = save_receipt(receipt, args.session)
        print(f"\nCompra salva no banco com id {purchase_id}.")


if __name__ == "__main__":
    main()
