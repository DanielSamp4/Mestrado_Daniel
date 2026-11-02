"""Leitura OCR de uma imagem ou do ultimo frame salvo."""

import argparse
import os
from pathlib import Path
import shutil

import cv2

CAPTURES_DIRECTORY = Path("captures")


def _configure_tesseract(pytesseract) -> None:
    """Usa PATH, variavel de ambiente ou o local padrao do instalador Windows."""
    configured = os.environ.get("TESSERACT_CMD")
    candidates = [
        configured,
        shutil.which("tesseract"),
        r"C:\Program Files\Tesseract-OCR\tesseract.exe",
        r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
    ]
    for candidate in candidates:
        if candidate and Path(candidate).is_file():
            pytesseract.pytesseract.tesseract_cmd = str(candidate)
            return


def _crop_receipt(image):
    """Remove o fundo da camera, mantendo o maior bloco claro (o cupom)."""
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    _, binary = cv2.threshold(gray, 140, 255, cv2.THRESH_BINARY)
    count, _, stats, _ = cv2.connectedComponentsWithStats(binary, connectivity=8)
    image_height, image_width = gray.shape
    candidates = [
        stat for stat in stats[1:count]
        if stat[4] >= image_height * image_width * 0.08
    ]
    if not candidates:
        return gray
    x, y, width, height, _ = max(candidates, key=lambda stat: stat[4])
    padding = 8
    left, top = max(0, x - padding), max(0, y - padding)
    right, bottom = min(image_width, x + width + padding), min(image_height, y + height + padding)
    return gray[top:bottom, left:right]


def latest_capture() -> Path:
    captures = sorted(CAPTURES_DIRECTORY.rglob("frame_*.png"))
    if not captures:
        raise FileNotFoundError("Nenhum frame salvo. Faca uma sessao no live feed.")
    return captures[-1]


def read_text(image_path: Path, language: str = "por") -> str:
    """Extrai texto de uma imagem preparada para recibos usando Tesseract."""
    try:
        import pytesseract
    except ImportError as error:
        raise RuntimeError("Biblioteca ausente. Instale com: pip install pytesseract") from error
    _configure_tesseract(pytesseract)
    image = cv2.imread(str(image_path))
    if image is None:
        raise FileNotFoundError(f"Nao foi possivel abrir a imagem: {image_path}")
    gray = _crop_receipt(image)
    # A escala de cinza preserva melhor caracteres térmicos finos que uma
    # binarização agressiva, e a ampliação ajuda o modelo de OCR.
    prepared = cv2.resize(gray, None, fx=3, fy=3, interpolation=cv2.INTER_CUBIC)
    try:
        return pytesseract.image_to_string(prepared, lang=language, config="--oem 3 --psm 6").strip()
    except pytesseract.TesseractNotFoundError as error:
        raise RuntimeError("Tesseract nao encontrado. Instale-o e adicione-o ao PATH.") from error
    except pytesseract.TesseractError as error:
        raise RuntimeError(f"OCR nao pode usar o idioma '{language}'. Instale seus dados.") from error


def main() -> None:
    parser = argparse.ArgumentParser(description="Le o texto de uma imagem capturada.")
    parser.add_argument("image", nargs="?", type=Path)
    parser.add_argument("--lang", default="por")
    args = parser.parse_args()
    image_path = args.image or latest_capture()
    print(f"Imagem analisada: {image_path}\n\nTexto identificado:\n{read_text(image_path, args.lang)}")


if __name__ == "__main__":
    main()
