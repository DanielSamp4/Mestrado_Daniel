"""OCR, uniao de trechos sobrepostos e extracao basica de uma nota fiscal."""

from dataclasses import asdict, dataclass
from difflib import SequenceMatcher
import csv
import re
from pathlib import Path

from text_reader import read_text


@dataclass
class ReceiptItem:
    description: str
    quantity: float | None
    unit: str | None
    unit_price: float | None
    total_price: float | None
    category: str
    confidence: str
    raw_line: str


@dataclass
class Receipt:
    merchant: str | None
    purchase_date: str | None
    total: float | None
    items: list[ReceiptItem]
    raw_text: str


def _clean(line: str) -> str:
    return " ".join(line.upper().split())


def _similar(left: str, right: str) -> bool:
    return _clean(left) == _clean(right) or SequenceMatcher(None, _clean(left), _clean(right)).ratio() >= 0.88


def merge_ocr_texts(texts: list[str]) -> list[str]:
    """Une textos na ordem capturada, removendo a sobreposicao entre quadros."""
    merged: list[str] = []
    for text in texts:
        incoming = [line.strip() for line in text.splitlines() if line.strip()]
        overlap = 0
        for size in range(min(len(merged), len(incoming)), 0, -1):
            if all(_similar(a, b) for a, b in zip(merged[-size:], incoming[:size])):
                overlap = size
                break
        merged.extend(incoming[overlap:])
    return merged


def _money(value: str) -> float:
    # OCR em ingles usa ponto; cupons brasileiros normalmente usam virgula.
    if "," in value:
        return float(value.replace(".", "").replace(",", "."))
    return float(value)


MONEY = re.compile(r"(?<![\d.,])(\d{1,4}(?:[.,]\d{2}))(?!\d)")
DATE = re.compile(r"\b(\d{2}[/-]\d{2}[/-]\d{2,4})\b")
NON_ITEMS = re.compile(r"\b(TOTAL|SUBTOTAL|TROCO|DINHEIRO|CARTAO|PIX|CNPJ|CPF|NFC|CUPOM|OPERADOR|QUANTIDADE|TRECHOS|DISTANCIA\s+BOA|DESCONTO)\b")
QUANTITY = re.compile(r"(?<!\d)(\d+(?:[.,]\d+)?)\s*(?:[JI1]?UN|KG|ML|LT|L|G)\b", re.IGNORECASE)
MAX_OCR_FRAMES = 8


def _parse_quantity(line: str) -> tuple[float | None, str | None]:
    matches = list(QUANTITY.finditer(line))
    if not matches:
        return None, None
    # Embalagens como "400G" fazem parte da descricao; prefira a unidade de
    # venda (UN/KG/L/ML), normalmente presente no fim da linha.
    preferred = [match for match in matches if not match.group(0).upper().endswith("G") or match.group(0).upper().endswith("KG")]
    match = preferred[-1] if preferred else matches[-1]
    suffix = re.search(r"[A-Za-z]+$", match.group(0)).group(0).upper()
    unit = "UN" if suffix.endswith("UN") else suffix
    return float(match.group(1).replace(",", ".")), unit


def _category(description: str) -> str:
    normalized = _clean(description)
    rules = (
        ("hortifruti", r"BATATA\s+DOCE"),
        ("doce", r"GELEIA|DOCE|CHOCOL|BOMBOM|BISCOIT|SUCRIL|ACUCAR"),
        ("proteina", r"FRANGO|PERU|PATINHO|BIFE|CHARQUE|SARDINHA|OVO|PEIXE|CARNE"),
        ("carboidrato", r"PAO|MACARR|FLOCAO|ARROZ|CEREAL|MACAXEIRA|BATATA|MILHO"),
        ("hortifruti", r"TOMATE|ALHO|CEBOLA|CEBOLINHA|COENTRO|PEPINO|ABACAXI|BANANA|LIMAO|PIMENT"),
        ("laticinio", r"QUEIJO|MUSSARELA|CHEDDAR|LEITE|MANTEIGA|CREME"),
        ("tempero/gordura", r"AZEITE|VINAGRE|KETCHUP|SAL"),
        ("nao alimenticio", r"PAP\s*TOALHA|HIGIENE|SABAO"),
    )
    return next((category for category, pattern in rules if re.search(pattern, normalized)), "outros")


def _description_similarity(left: str, right: str) -> float:
    """Compara descricoes ignorando codigo, pontuacao e pequenos erros de OCR."""
    def normalize(value: str) -> str:
        return re.sub(r"[^A-Z]", "", _clean(value))
    return SequenceMatcher(None, normalize(left), normalize(right)).ratio()


def _item_quality(item: ReceiptItem) -> int:
    letters = sum(character.isalpha() for character in item.description)
    words = len(item.description.split())
    return letters + 4 * words + (8 if item.quantity is not None else 0)


def _confidence(description: str, quantity: float | None, unit_price: float | None) -> str:
    words = len(re.findall(r"[A-Za-zÀ-ÿ]{2,}", description))
    if words >= 3 and quantity is not None and unit_price is not None:
        return "alta"
    if words >= 2 and (quantity is not None or unit_price is not None):
        return "media"
    return "revisar"


def _deduplicate_items(items: list[ReceiptItem]) -> list[ReceiptItem]:
    """Conserva a leitura mais clara de cada produto repetido em quadros sobrepostos."""
    unique: list[ReceiptItem] = []
    for item in items:
        duplicate_index = next(
            (
                index for index, existing in enumerate(unique)
                if existing.total_price == item.total_price
                and _description_similarity(existing.description, item.description) >= 0.74
            ),
            None,
        )
        if duplicate_index is None:
            unique.append(item)
        elif _item_quality(item) > _item_quality(unique[duplicate_index]):
            unique[duplicate_index] = item
    return unique


def _description(line: str) -> str:
    without_code = re.sub(r"^\s*\d{7,}\s*", "", line)
    without_numbers = MONEY.sub("", without_code)
    # Remove a quantidade de venda, mas preserva o tamanho da embalagem (400G).
    matches = list(QUANTITY.finditer(without_numbers))
    preferred = [
        match for match in matches
        if not match.group(0).upper().endswith("G") or match.group(0).upper().endswith("KG")
    ]
    if preferred:
        match = preferred[-1]
        without_numbers = without_numbers[:match.start()] + without_numbers[match.end():]
    return " ".join(without_numbers.strip(" -.:;").split())


def parse_receipt(lines: list[str]) -> Receipt:
    raw_text = "\n".join(lines)
    purchase_date = next((match.group(1) for line in lines if (match := DATE.search(line))), None)
    total = None
    for line in lines:
        if re.search(r"\b(TOTAL|VALOR\s+(?:A\s+)?PAGAR)\b", _clean(line)):
            values = MONEY.findall(line)
            if values:
                total = _money(values[-1])
    merchant = next((line.strip() for line in lines[:8] if sum(char.isalpha() for char in line) >= 5 and not MONEY.search(line)), None)
    items: list[ReceiptItem] = []
    for line in lines:
        values = MONEY.findall(line)
        description = _description(line)
        if not values or len(description) < 3 or NON_ITEMS.search(_clean(line)):
            continue
        words = re.findall(r"[A-Za-zÀ-ÿ]{2,}", description)
        if sum(char.isalpha() for char in description) < 6 or len(words) < 2:
            continue
        parsed_values = [_money(value) for value in values]
        item_total = parsed_values[-1]
        if total is not None and item_total == total:
            continue
        quantity, unit = _parse_quantity(line)
        unit_price = parsed_values[-2] if len(parsed_values) >= 2 else None
        if unit_price and item_total:
            inferred_quantity = item_total / unit_price
            if unit == "KG" and 0.005 <= inferred_quantity <= 20:
                quantity = round(inferred_quantity, 3)
            elif unit == "UN" and 0.9 <= inferred_quantity <= 100:
                rounded_quantity = round(inferred_quantity)
                if abs(inferred_quantity - rounded_quantity) <= 0.08:
                    quantity = float(rounded_quantity)
        items.append(ReceiptItem(
            description=description,
            quantity=quantity,
            unit=unit,
            unit_price=unit_price,
            total_price=item_total,
            category=_category(description),
            confidence=_confidence(description, quantity, unit_price),
            raw_line=line,
        ))
    return Receipt(
        merchant=merchant,
        purchase_date=purchase_date,
        total=total,
        items=_deduplicate_items(items),
        raw_text=raw_text,
    )


def _representative_frames(frames: list[Path]) -> list[Path]:
    """Reduz sequencias densas, mantendo cobertura uniforme da nota inteira."""
    if len(frames) <= MAX_OCR_FRAMES:
        return frames
    indices = {
        round(index * (len(frames) - 1) / (MAX_OCR_FRAMES - 1))
        for index in range(MAX_OCR_FRAMES)
    }
    return [frame for index, frame in enumerate(frames) if index in indices]


def process_session(session: Path, language: str = "por") -> Receipt:
    frames = sorted(session.glob("frame_*.png"))
    if not frames:
        raise FileNotFoundError(f"Nenhum frame encontrado em {session}")
    frames = _representative_frames(frames)
    lines = merge_ocr_texts([read_text(frame, language) for frame in frames])
    return parse_receipt(lines)


def receipt_as_dict(receipt: Receipt) -> dict:
    return asdict(receipt)


def write_analysis_table(receipt: Receipt, output_directory: Path) -> tuple[Path, Path]:
    """Gera formatos para conferencia humana no Excel ou em um editor Markdown."""
    csv_path = output_directory / "analise_itens.csv"
    markdown_path = output_directory / "analise_itens.md"
    headers = ["item", "quantidade", "unidade", "preco_unitario", "valor_total", "categoria", "confianca", "linha_ocr"]
    rows = [
        [
            item.description,
            "" if item.quantity is None else f"{item.quantity:.3f}",
            item.unit or "",
            "" if item.unit_price is None else f"{item.unit_price:.2f}",
            "" if item.total_price is None else f"{item.total_price:.2f}",
            item.category,
            item.confidence,
            item.raw_line,
        ]
        for item in receipt.items
    ]
    with csv_path.open("w", newline="", encoding="utf-8-sig") as file:
        writer = csv.writer(file, delimiter=";")
        writer.writerow(headers)
        writer.writerows(rows)
    markdown_rows = [
        "| Item | Qtd. | Unid. | Unitário | Total | Categoria | Confiança |",
        "| --- | ---: | --- | ---: | ---: | --- | --- |",
    ]
    for item in receipt.items:
        quantity = "" if item.quantity is None else f"{item.quantity:.3f}"
        unit_price = "" if item.unit_price is None else f"R$ {item.unit_price:.2f}"
        total_price = "" if item.total_price is None else f"R$ {item.total_price:.2f}"
        markdown_rows.append(f"| {item.description} | {quantity} | {item.unit or ''} | {unit_price} | {total_price} | {item.category} | {item.confidence} |")
    markdown_path.write_text("\n".join(markdown_rows) + "\n", encoding="utf-8")
    return csv_path, markdown_path
