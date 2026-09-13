import argparse
from dataclasses import dataclass
from pathlib import Path

try:
    import cv2
    import numpy as np
except ImportError as exc:
    raise SystemExit(
        "OpenCV nao esta instalado. Instale com: pip install opencv-python"
    ) from exc


@dataclass
class ConfiguracaoDeteccao:
    area_minima_bola: int = 20
    area_minima_marcador: int = 20
    distancia_maxima_marcadores: float = 90.0


def criar_mascara(hsv: np.ndarray, limite_inferior: tuple, limite_superior: tuple) -> np.ndarray:
    mascara = cv2.inRange(
        hsv,
        np.array(limite_inferior, dtype=np.uint8),
        np.array(limite_superior, dtype=np.uint8),
    )
    kernel = np.ones((5, 5), np.uint8)
    mascara = cv2.morphologyEx(mascara, cv2.MORPH_OPEN, kernel)
    mascara = cv2.morphologyEx(mascara, cv2.MORPH_CLOSE, kernel)
    return mascara


def encontrar_centroides(mascara: np.ndarray, area_minima: int) -> list[tuple[int, int, float]]:
    contornos, _ = cv2.findContours(mascara, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    centroides = []

    for contorno in contornos:
        area = cv2.contourArea(contorno)

        if area < area_minima:
            continue

        momentos = cv2.moments(contorno)

        if momentos["m00"] == 0:
            continue

        x = int(momentos["m10"] / momentos["m00"])
        y = int(momentos["m01"] / momentos["m00"])
        centroides.append((x, y, area))

    return centroides


def detectar_bola(hsv: np.ndarray, config: ConfiguracaoDeteccao) -> tuple[int, int] | None:
    mascara_laranja = criar_mascara(hsv, (5, 80, 80), (25, 255, 255))
    centroides = encontrar_centroides(mascara_laranja, config.area_minima_bola)

    if not centroides:
        return None

    x, y, _ = max(centroides, key=lambda centroide: centroide[2])
    return x, y


def detectar_meu_jogador(
    hsv: np.ndarray,
    config: ConfiguracaoDeteccao,
) -> tuple[int, int] | None:
    mascara_azul = criar_mascara(hsv, (90, 70, 50), (130, 255, 255))
    mascara_verde = criar_mascara(hsv, (35, 60, 50), (85, 255, 255))

    centroides_azuis = encontrar_centroides(mascara_azul, config.area_minima_marcador)
    centroides_verdes = encontrar_centroides(mascara_verde, config.area_minima_marcador)

    melhor_par = None
    menor_distancia = float("inf")

    for azul in centroides_azuis:
        for verde in centroides_verdes:
            distancia = ((azul[0] - verde[0]) ** 2 + (azul[1] - verde[1]) ** 2) ** 0.5

            if distancia < menor_distancia and distancia <= config.distancia_maxima_marcadores:
                melhor_par = (azul, verde)
                menor_distancia = distancia

    if melhor_par is None:
        return None

    azul, verde = melhor_par
    x = int((azul[0] + verde[0]) / 2)
    y = int((azul[1] + verde[1]) / 2)
    return x, y


def desenhar_trajetoria(
    frame_saida: np.ndarray,
    pontos: list[tuple[int, int]],
    cor: tuple[int, int, int],
    raio_atual: int,
) -> None:
    if len(pontos) > 1:
        for ponto_anterior, ponto_atual in zip(pontos, pontos[1:]):
            cv2.line(frame_saida, ponto_anterior, ponto_atual, cor, 2)

    if pontos:
        cv2.circle(frame_saida, pontos[-1], raio_atual, cor, -1)


def criar_frame_saida(
    largura: int,
    altura: int,
    trajetoria_jogador: list[tuple[int, int]],
    trajetoria_bola: list[tuple[int, int]],
    frame_atual: int,
) -> np.ndarray:
    frame_saida = np.full((altura, largura, 3), 245, dtype=np.uint8)

    cv2.rectangle(frame_saida, (0, 0), (largura - 1, altura - 1), (40, 40, 40), 2)
    cv2.putText(
        frame_saida,
        f"Frame {frame_atual}",
        (20, 35),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.8,
        (40, 40, 40),
        2,
        cv2.LINE_AA,
    )

    desenhar_trajetoria(frame_saida, trajetoria_jogador, (255, 0, 0), 8)
    desenhar_trajetoria(frame_saida, trajetoria_bola, (0, 140, 255), 6)

    cv2.putText(
        frame_saida,
        "Jogador",
        (20, altura - 55),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.65,
        (255, 0, 0),
        2,
        cv2.LINE_AA,
    )
    cv2.putText(
        frame_saida,
        "Bola",
        (20, altura - 25),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.65,
        (0, 140, 255),
        2,
        cv2.LINE_AA,
    )

    return frame_saida


def processar_video(
    caminho_entrada: Path,
    caminho_saida: Path,
    config: ConfiguracaoDeteccao,
) -> None:
    video = cv2.VideoCapture(str(caminho_entrada))

    if not video.isOpened():
        raise SystemExit(f"Nao foi possivel abrir o video: {caminho_entrada}")

    fps = video.get(cv2.CAP_PROP_FPS)
    largura = int(video.get(cv2.CAP_PROP_FRAME_WIDTH))
    altura = int(video.get(cv2.CAP_PROP_FRAME_HEIGHT))
    fps_saida = fps if fps > 0 else 30

    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    saida = cv2.VideoWriter(str(caminho_saida), fourcc, fps_saida, (largura, altura))

    if not saida.isOpened():
        video.release()
        raise SystemExit(f"Nao foi possivel criar o video de saida: {caminho_saida}")

    trajetoria_jogador = []
    trajetoria_bola = []
    numero_frame = 0

    while True:
        sucesso, frame = video.read()

        if not sucesso:
            break

        numero_frame += 1
        hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)

        posicao_jogador = detectar_meu_jogador(hsv, config)
        posicao_bola = detectar_bola(hsv, config)

        if posicao_jogador is not None:
            trajetoria_jogador.append(posicao_jogador)

        if posicao_bola is not None:
            trajetoria_bola.append(posicao_bola)

        frame_saida = criar_frame_saida(
            largura,
            altura,
            trajetoria_jogador,
            trajetoria_bola,
            numero_frame,
        )
        saida.write(frame_saida)

    video.release()
    saida.release()

    print(f"Video gerado: {caminho_saida}")
    print(f"Pontos do jogador detectados: {len(trajetoria_jogador)}")
    print(f"Pontos da bola detectados: {len(trajetoria_bola)}")


def encontrar_videos(padrao: str, pasta_base: Path) -> list[Path]:
    caminho = Path(padrao)

    if caminho.is_file():
        return [caminho]

    if not caminho.is_absolute():
        caminho = pasta_base / caminho

    videos = sorted(caminho.parent.glob(caminho.name))

    if not videos:
        raise SystemExit(f"Nenhum video encontrado com o padrao: {caminho}")

    return videos


def criar_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Gera um video 2D com a trajetoria do meu jogador e da bola."
    )
    parser.add_argument(
        "entrada",
        nargs="?",
        default="teste*.mp4",
        help="Arquivo ou padrao dos videos de entrada. Padrao: teste*.mp4",
    )
    parser.add_argument(
        "--saida",
        default=None,
        help="Arquivo de saida. Use somente quando a entrada for um unico video.",
    )
    parser.add_argument(
        "--distancia-marcadores",
        type=float,
        default=90.0,
        help="Distancia maxima entre os circulos azul e verde do seu jogador.",
    )
    return parser


def main() -> None:
    pasta_base = Path(__file__).parent
    args = criar_parser().parse_args()
    videos = encontrar_videos(args.entrada, pasta_base)

    if args.saida is not None and len(videos) > 1:
        raise SystemExit("Use --saida somente quando a entrada for um unico video.")

    config = ConfiguracaoDeteccao(
        distancia_maxima_marcadores=args.distancia_marcadores,
    )

    for video in videos:
        caminho_saida = Path(args.saida) if args.saida else video.with_name(f"{video.stem}_trajetoria.mp4")

        if not caminho_saida.is_absolute():
            caminho_saida = pasta_base / caminho_saida

        processar_video(video, caminho_saida, config)


if __name__ == "__main__":
    main()
