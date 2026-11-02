"""Algoritmos de visão para localizar texto e estimar sua distância na imagem."""

from collections import defaultdict
from dataclasses import dataclass
from time import perf_counter

import cv2
import numpy as np


@dataclass
class TextDistanceResult:
    """Resultado da análise de texto de um quadro da câmera."""

    text_detected: bool
    status: str
    message: str
    character_height: float = 0.0
    text_bounds: tuple[int, int, int, int] | None = None


# Faixa em pixels adequada para caracteres legíveis em uma webcam comum.
# A faixa original (12--20 px) era estreita demais para streams de celular e
# quase nunca liberava a captura. OCR continua legivel com letras maiores.
MIN_READABLE_HEIGHT = 10
MAX_READABLE_HEIGHT = 48
MIN_CHARACTERS_IN_LINE = 5
MIN_TEXT_SHARPNESS = 45.0


def _record_timing(
    timings: dict[str, float] | None, stage: str, started_at: float
) -> None:
    """Registra a duração de uma etapa em milissegundos quando o perfil está ativo."""
    if timings is not None:
        timings[stage] = (perf_counter() - started_at) * 1000


def _largest_text_line(
    candidates: list[tuple[int, int, int, int]],
) -> list[tuple[int, int, int, int]]:
    """Retorna o maior grupo de caracteres alinhados horizontalmente.

    Textos formam sequências de componentes de tamanho parecido e com centros na
    mesma linha. Essa validação evita que ruído e detalhes isolados da cena sejam
    considerados letras.
    """
    # A versão anterior comparava todos os candidatos entre si (O(n²)). Cada
    # componente agora é colocado em três faixas próximas do seu centro vertical;
    # isso preserva linhas de texto que cruzam a borda de uma faixa e reduz o
    # agrupamento para ordenações locais O(n log n).
    bucket_size = 8
    buckets: dict[int, list[tuple[int, int, int, int]]] = defaultdict(list)
    for candidate in candidates:
        _, y, _, height = candidate
        center_bucket = int((y + height / 2) // bucket_size)
        for bucket in range(center_bucket - 1, center_bucket + 2):
            buckets[bucket].append(candidate)

    largest_line: list[tuple[int, int, int, int]] = []
    for same_line in buckets.values():
        same_line.sort(key=lambda item: item[0])
        current_line: list[tuple[int, int, int, int]] = []

        for candidate in same_line:
            if not current_line:
                current_line.append(candidate)
                continue

            previous_x, previous_y, previous_width, previous_height = current_line[-1]
            x, y, _, height = candidate
            gap = x - (previous_x + previous_width)
            height_ratio = height / previous_height
            center_distance = abs(
                (y + height / 2) - (previous_y + previous_height / 2)
            )
            allowed_gap = 5 * max(previous_height, height)
            aligned = center_distance <= max(4, 0.6 * max(previous_height, height))

            if 0.5 <= height_ratio <= 2.0 and aligned and gap <= allowed_gap:
                current_line.append(candidate)
            else:
                if len(current_line) > len(largest_line):
                    largest_line = current_line
                current_line = [candidate]

        if len(current_line) > len(largest_line):
            largest_line = current_line

    return largest_line


def estimate_text_distance(
    frame: np.ndarray, timings: dict[str, float] | None = None
) -> TextDistanceResult:
    """Detecta regiões semelhantes a texto e classifica a distância estimada.

    A classificação usa a altura mediana dos componentes que parecem caracteres:
    letras pequenas indicam que o objeto está longe; letras grandes, que está perto.
    """
    started_at = perf_counter()
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    _record_timing(timings, "analise/cinza", started_at)

    started_at = perf_counter()
    threshold_input = cv2.GaussianBlur(gray, (3, 3), 0)
    binary = cv2.adaptiveThreshold(
        threshold_input,
        255,
        cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY_INV,
        31,
        9,
    )
    _record_timing(timings, "analise/limiar", started_at)

    started_at = perf_counter()
    count, _, stats, _ = cv2.connectedComponentsWithStats(binary, connectivity=8)
    _record_timing(timings, "analise/componentes", started_at)

    started_at = perf_counter()
    frame_height, frame_width = gray.shape
    candidates: list[tuple[int, int, int, int]] = []

    for x, y, width, height, area in stats[1:count]:
        aspect_ratio = width / height
        if (
            6 <= height <= frame_height * 0.25
            and 2 <= width <= frame_width * 0.2
            and 0.08 <= aspect_ratio <= 3.0
            and area >= height * 0.12
            and area <= width * height * 0.9
        ):
            candidates.append((x, y, width, height))
    _record_timing(timings, "analise/filtragem", started_at)

    started_at = perf_counter()
    text_line = _largest_text_line(candidates)
    _record_timing(timings, "analise/agrupamento", started_at)
    if len(text_line) < MIN_CHARACTERS_IN_LINE:
        return TextDistanceResult(
            False,
            "none",
            "Aponte a camera para o texto.",
        )

    started_at = perf_counter()
    character_height = float(np.median([height for _, _, _, height in text_line]))
    left = max(0, min(x for x, _, _, _ in text_line) - int(character_height))
    top = max(0, min(y for _, y, _, _ in text_line) - int(character_height))
    right = min(
        frame_width,
        max(x + width for x, _, width, _ in text_line) + int(character_height),
    )
    bottom = min(
        frame_height,
        max(y + height for _, y, _, height in text_line) + int(character_height),
    )
    text_region = gray[top:bottom, left:right]
    # Variância do Laplaciano na região do texto: quanto menor, mais desfocada.
    sharpness = float(cv2.Laplacian(text_region, cv2.CV_64F).var())
    _record_timing(timings, "analise/nitidez", started_at)
    # Esta regra tem prioridade sobre a distância: texto borrado não é legível.
    if sharpness < MIN_TEXT_SHARPNESS:
        return TextDistanceResult(
            True,
            "too_close",
            "Afaste a camera: imagem desfocada.",
            character_height,
            (left, top, right, bottom),
        )
    if character_height < MIN_READABLE_HEIGHT:
        return TextDistanceResult(
            True,
            "too_far",
            "Aproxime o texto.",
            character_height,
            (left, top, right, bottom),
        )
    if character_height > MAX_READABLE_HEIGHT:
        return TextDistanceResult(
            True,
            "too_close",
            "Afaste o texto.",
            character_height,
            (left, top, right, bottom),
        )
    return TextDistanceResult(True, "ok", "Distancia boa: texto legivel.", character_height,
                              (left, top, right, bottom))


def draw_text_distance_feedback(frame: np.ndarray, result: TextDistanceResult) -> np.ndarray:
    """Desenha no quadro a orientação retornada pela análise."""
    colors = {
        "ok": (0, 180, 0),
        "too_far": (0, 180, 255),
        "too_close": (0, 80, 255),
        "none": (180, 180, 180),
    }
    color = colors[result.status]
    if result.text_detected and result.text_bounds is not None:
        left, top, right, bottom = result.text_bounds
        cv2.rectangle(frame, (left, top), (right - 1, bottom - 1), color, 2)
    cv2.rectangle(frame, (10, 10), (frame.shape[1] - 10, 58), (0, 0, 0), -1)
    cv2.putText(
        frame,
        result.message,
        (20, 42),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.65,
        color,
        2,
        cv2.LINE_AA,
    )
    return frame
