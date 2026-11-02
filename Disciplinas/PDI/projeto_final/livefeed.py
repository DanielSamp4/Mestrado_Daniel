"""Captura guiada de varios trechos de uma nota fiscal pela camera."""

from collections import defaultdict
from datetime import datetime
import json
from pathlib import Path
from time import perf_counter

import cv2
import numpy as np

from text_algorithms import draw_text_distance_feedback, estimate_text_distance

LOG_INTERVAL_FRAMES = 30
STABLE_CAPTURE_SECONDS = 1.0
MAX_STABLE_FRAME_DIFFERENCE = 3.0
MIN_NEW_FRAME_DIFFERENCE = 6.0
# Evita uma sequencia de salvamentos enquanto a nota e movimentada, sem exigir
# que o detector permaneça estavel por um segundo para o primeiro salvamento.
AUTO_CAPTURE_COOLDOWN_SECONDS = 1.0
CAPTURES_DIRECTORY = Path("captures")


def _print_performance_log(totals: dict[str, float], frame_count: int) -> None:
    average_total_ms = totals["frame_total"] / frame_count
    fps = 1000 / average_total_ms if average_total_ms else 0.0
    stages = " | ".join(f"{stage}: {total / frame_count:.1f} ms" for stage, total in totals.items() if stage != "frame_total")
    print(f"[perfil: {frame_count} frames] total: {average_total_ms:.1f} ms ({fps:.1f} FPS) | {stages}", flush=True)


def _new_session() -> Path:
    """Cria uma pasta que preserva a ordem de todos os trechos da nota."""
    session = CAPTURES_DIRECTORY / datetime.now().strftime("nota_%Y%m%d_%H%M%S")
    session.mkdir(parents=True, exist_ok=False)
    return session


def _thumbnail(frame: np.ndarray) -> np.ndarray:
    return cv2.resize(cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY), (160, 90))


def _save_captured_frame(session: Path, frame: np.ndarray, index: int) -> Path:
    capture_path = session / f"frame_{index:03d}.png"
    if not cv2.imwrite(str(capture_path), frame):
        raise RuntimeError(f"Nao foi possivel salvar o frame em {capture_path}.")
    return capture_path


def _save_if_new(
    session: Path,
    frame: np.ndarray,
    saved_frames: list[Path],
    last_saved_thumbnail: np.ndarray | None,
    *,
    force: bool = False,
) -> tuple[bool, np.ndarray | None]:
    """Salva um trecho novo; ``force`` permite ao usuario substituir o limiar."""
    thumbnail = _thumbnail(frame)
    is_new = (
        last_saved_thumbnail is None
        or np.mean(cv2.absdiff(thumbnail, last_saved_thumbnail)) >= MIN_NEW_FRAME_DIFFERENCE
    )
    if not (is_new or force):
        return False, last_saved_thumbnail
    capture_path = _save_captured_frame(session, frame, len(saved_frames) + 1)
    saved_frames.append(capture_path)
    print(f"[captura] Frame salvo em: {capture_path}", flush=True)
    return True, thumbnail


def _show_capture_preview(window_name: str, frame: np.ndarray) -> None:
    """Mostra o trecho bruto salvo, reduzido apenas para caber confortavelmente."""
    height, width = frame.shape[:2]
    maximum_width = 900
    if width > maximum_width:
        scale = maximum_width / width
        frame = cv2.resize(frame, (maximum_width, int(height * scale)))
    cv2.imshow(window_name, frame)


def _write_manifest(session: Path, frames: list[Path]) -> None:
    manifest = {"created_at": datetime.now().isoformat(timespec="seconds"), "frames": [frame.name for frame in frames]}
    (session / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")


def livefeed(camera_index: int | str = 0, mirror: bool = True) -> Path | None:
    """Captura trechos legiveis ate ``f`` (finalizar) ou ``q`` (cancelar).

    Comece no topo; apos cada salvamento, mova a nota para cima e mantenha uma
    pequena sobreposicao com o trecho anterior.
    """
    camera = cv2.VideoCapture(camera_index)
    if not camera.isOpened():
        raise RuntimeError(f"Nao foi possivel abrir a fonte de video: {camera_index}.")
    if isinstance(camera_index, int):
        camera.set(cv2.CAP_PROP_AUTOFOCUS, 1)

    session = _new_session()
    saved_frames: list[Path] = []
    window_name = "Escaneamento de nota - s: salvar | f: finalizar | q: sair"
    preview_window_name = "Ultimo trecho capturado (automatico)"
    timing_totals: dict[str, float] = defaultdict(float)
    frames_profiled = 0
    last_saved_thumbnail: np.ndarray | None = None
    last_auto_capture_at = 0.0
    finished = False
    last_reported_status: str | None = None
    print(f"[sessao] Nota iniciada em: {session}", flush=True)
    print("[sessao] Comece pelo topo; apos cada captura, mova a nota para cima.", flush=True)

    try:
        while True:
            frame_started_at = perf_counter()
            stage_started_at = perf_counter()
            success, frame = camera.read()
            frame_timings = {"captura": (perf_counter() - stage_started_at) * 1000}
            if not success:
                raise RuntimeError("Nao foi possivel ler um quadro da webcam.")
            if mirror:
                frame = cv2.flip(frame, 1)
            # Mantem uma copia sem os textos da interface para qualquer captura,
            # inclusive quando o usuario aperta "s" apos a janela ser desenhada.
            capture_frame = frame.copy()
            frame_timings["espelhamento"] = (perf_counter() - stage_started_at) * 1000
            text_result = estimate_text_distance(frame, frame_timings)
            if text_result.status != last_reported_status:
                height = f" (altura de letra: {text_result.character_height:.0f}px)" if text_result.text_detected else ""
                print(f"[guia] {text_result.message}{height}", flush=True)
                last_reported_status = text_result.status

            stage_started_at = perf_counter()
            if text_result.status == "ok":
                now = perf_counter()
                if now - last_auto_capture_at >= AUTO_CAPTURE_COOLDOWN_SECONDS:
                    saved, last_saved_thumbnail = _save_if_new(
                        session, capture_frame, saved_frames, last_saved_thumbnail
                    )
                    if saved:
                        last_auto_capture_at = now
                        _show_capture_preview(preview_window_name, capture_frame)
                        text_result.message = f"Trecho {len(saved_frames)} salvo. Mova a nota para cima."
                    else:
                        text_result.message = "Mesmo trecho; mova a nota para cima."
            frame_timings["estabilidade"] = (perf_counter() - stage_started_at) * 1000

            frame = draw_text_distance_feedback(frame, text_result)
            cv2.putText(frame, f"Trechos: {len(saved_frames)} | s: salvar | f: finalizar", (20, 82), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2, cv2.LINE_AA)
            cv2.imshow(window_name, frame)
            key = cv2.waitKey(1) & 0xFF
            if key == ord("s"):
                if text_result.text_detected:
                    saved, last_saved_thumbnail = _save_if_new(
                        session, capture_frame, saved_frames, last_saved_thumbnail, force=True
                    )
                    if saved:
                        print("[captura] Salvamento manual; confira a nitidez no OCR.", flush=True)
                else:
                    print("[captura] Nenhum texto foi detectado; quadro nao salvo.", flush=True)
            if key == ord("f"):
                finished = True
                break
            if cv2.getWindowProperty(window_name, cv2.WND_PROP_VISIBLE) < 1:
                break
            if key == ord("q"):
                break
            frame_timings["frame_total"] = (perf_counter() - frame_started_at) * 1000
            for stage, duration in frame_timings.items():
                timing_totals[stage] += duration
            frames_profiled += 1
            if frames_profiled == LOG_INTERVAL_FRAMES:
                _print_performance_log(timing_totals, frames_profiled)
                timing_totals.clear()
                frames_profiled = 0
    finally:
        camera.release()
        cv2.destroyAllWindows()

    if saved_frames:
        _write_manifest(session, saved_frames)
        print(f"[sessao] Finalizada com {len(saved_frames)} trechos: {session}", flush=True)
        return session
    if not saved_frames:
        session.rmdir()
        print("[sessao] Cancelada sem trechos salvos.", flush=True)
    else:
        print(f"[sessao] Cancelada; os {len(saved_frames)} trechos parciais foram mantidos em: {session}", flush=True)
    return None
