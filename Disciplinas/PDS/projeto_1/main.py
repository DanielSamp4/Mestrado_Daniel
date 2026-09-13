from pathlib import Path
import argparse

try:
    import cv2
    import numpy as np
except ImportError as exc:
    raise SystemExit("Instale o OpenCV com: pip install opencv-python") from exc


BASE = Path(__file__).parent
CORES = {
    "laranja": ((5, 80, 80), (25, 255, 255)),
    "azul": ((90, 70, 50), (130, 255, 255)),
    "verde": ((35, 60, 50), (85, 255, 255)),
    "amarelo": ((22, 70, 70), (38, 255, 255)),
    "vermelho": [((0, 70, 70), (4, 255, 255)), ((170, 70, 70), (179, 255, 255))],
    "roxo": ((130, 40, 50), (165, 255, 255)),
}
CORES_JOGADORES = ["azul", "verde", "amarelo", "vermelho", "roxo"]
COR_MEU_TIME = (255, 0, 0)
COR_ADVERSARIO = (0, 0, 255)


def mascara(hsv, cor):
    limites = CORES[cor]
    if isinstance(limites, list):
        img = np.zeros(hsv.shape[:2], np.uint8)
        for inferior, superior in limites:
            img = cv2.bitwise_or(img, cv2.inRange(hsv, np.array(inferior), np.array(superior)))
    else:
        img = cv2.inRange(hsv, np.array(limites[0]), np.array(limites[1]))

    kernel = np.ones((5, 5), np.uint8)
    img = cv2.morphologyEx(img, cv2.MORPH_OPEN, kernel)
    return cv2.morphologyEx(img, cv2.MORPH_CLOSE, kernel)


def centroides(img, area_min=20):
    contornos, _ = cv2.findContours(img, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    pontos = []

    contornos = sorted(contornos, key=cv2.contourArea, reverse=True)
    for contorno in contornos:
        area = cv2.contourArea(contorno)
        if area < area_min:
            continue

        m = cv2.moments(contorno)
        if m["m00"]:
            pontos.append((int(m["m10"] / m["m00"]), int(m["m01"] / m["m00"])))

    return pontos


def marcadores(hsv):
    encontrados = []
    for cor in CORES_JOGADORES:
        for ponto in centroides(mascara(hsv, cor)):
            encontrados.append({"cor": cor, "ponto": ponto})
    return encontrados


def distancia(p1, p2):
    return ((p1[0] - p2[0]) ** 2 + (p1[1] - p2[1]) ** 2) ** 0.5


def pares_jogadores(hsv, distancia_max=55):
    candidatos = []
    pontos = marcadores(hsv)

    for i, marcador_a in enumerate(pontos):
        for j in range(i + 1, len(pontos)):
            marcador_b = pontos[j]
            if marcador_a["cor"] == marcador_b["cor"]:
                continue

            dist = distancia(marcador_a["ponto"], marcador_b["ponto"])
            if dist <= distancia_max:
                candidatos.append((dist, i, j))

    candidatos.sort()
    usados = set()
    pares = []

    for _, i, j in candidatos:
        if i in usados or j in usados:
            continue

        usados.update((i, j))
        pares.append((pontos[i], pontos[j]))

    return pares


def maior_centro(hsv, cor):
    pontos = centroides(mascara(hsv, cor))
    return pontos[0] if pontos else None


def centro_proximo(hsv, cor, anterior, deslocamento_max=60):
    pontos = centroides(mascara(hsv, cor))
    if not pontos:
        return None

    if anterior is None:
        return pontos[0]

    def distancia(ponto):
        return ((ponto[0] - anterior[0]) ** 2 + (ponto[1] - anterior[1]) ** 2) ** 0.5

    ponto = min(pontos, key=distancia)
    return ponto if distancia(ponto) <= deslocamento_max else None


def meu_jogador(hsv, distancia_max=90):
    azuis = centroides(mascara(hsv, "azul"))
    verdes = centroides(mascara(hsv, "verde"))
    pares = [
        (azul, verde, ((azul[0] - verde[0]) ** 2 + (azul[1] - verde[1]) ** 2) ** 0.5)
        for azul in azuis
        for verde in verdes
    ]
    pares = [par for par in pares if par[2] <= distancia_max]

    if not pares:
        return None

    azul, verde, _ = min(pares, key=lambda par: par[2])
    return int((azul[0] + verde[0]) / 2), int((azul[1] + verde[1]) / 2)


def mascara_campo(frame):
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    linhas = cv2.inRange(hsv, np.array((0, 0, 150)), np.array((179, 70, 255)))
    kernel = np.ones((3, 3), np.uint8)
    linhas = cv2.morphologyEx(linhas, cv2.MORPH_OPEN, kernel)
    limpa = np.zeros_like(linhas)
    total, rotulos, estatisticas, _ = cv2.connectedComponentsWithStats(linhas)

    for i in range(1, total):
        if estatisticas[i, cv2.CC_STAT_AREA] >= 100:
            limpa[rotulos == i] = 255

    return cv2.erode(limpa, kernel, iterations=1)


def desenhar_campo(tela, frame_original):
    linhas = mascara_campo(frame_original)
    tela[linhas > 0] = (0, 0, 0)


def quadrado_do_jogador(par, margem=12):
    (x1, y1), (x2, y2) = par[0]["ponto"], par[1]["ponto"]
    esquerda = min(x1, x2) - margem
    direita = max(x1, x2) + margem
    topo = min(y1, y2) - margem
    baixo = max(y1, y2) + margem

    lado = max(direita - esquerda, baixo - topo)
    cx = (esquerda + direita) // 2
    cy = (topo + baixo) // 2
    metade = lado // 2
    return (cx - metade, cy - metade), (cx + metade, cy + metade)


def circulo_do_jogador(par):
    p1, p2 = quadrado_do_jogador(par)
    centro = ((p1[0] + p2[0]) // 2, (p1[1] + p2[1]) // 2)
    raio = max(p2[0] - p1[0], p2[1] - p1[1]) // 2
    return centro, raio


def desenhar_jogadores(tela, pares):
    for par in pares:
        cores = {par[0]["cor"], par[1]["cor"]}
        cor = COR_MEU_TIME if "azul" in cores else COR_ADVERSARIO
        centro, raio = circulo_do_jogador(par)
        cv2.circle(tela, centro, raio, cor, 1)


def desenhar(frame, pontos, cor, raio, texto=None):
    for p1, p2 in zip(pontos, pontos[1:]):
        cv2.line(frame, p1, p2, cor, 3)

    if pontos:
        cv2.circle(frame, pontos[-1], raio, cor, -1)
        if texto:
            x, y = pontos[-1]
            cv2.putText(frame, texto, (x + 10, y - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.55, cor, 2)


def processar(video_path):
    video = cv2.VideoCapture(str(video_path))
    if not video.isOpened():
        print(f"Nao foi possivel abrir: {video_path}")
        return

    fps = video.get(cv2.CAP_PROP_FPS) or 30
    w = int(video.get(cv2.CAP_PROP_FRAME_WIDTH))
    h = int(video.get(cv2.CAP_PROP_FRAME_HEIGHT))
    saida_path = video_path.with_name(f"{video_path.stem}_trajetoria.mp4")
    saida = cv2.VideoWriter(str(saida_path), cv2.VideoWriter_fourcc(*"mp4v"), fps, (w, h))

    traj_jogador, traj_bola, frame_n = [], [], 0

    while True:
        ok, frame = video.read()
        if not ok:
            break

        frame_n += 1
        # No teste1, depois do frame 114 o video volta ao inicio; por isso esses frames sao ignorados.
        if video_path.name == "teste1.mp4" and frame_n > 114:
            break

        hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
        jogador = meu_jogador(hsv)
        bola = centro_proximo(hsv, "laranja", traj_bola[-1] if traj_bola else None)
        jogadores = pares_jogadores(hsv)

        if jogador:
            traj_jogador.append(jogador)
        if bola:
            traj_bola.append(bola)

        tela = np.full((h, w, 3), 245, np.uint8)
        desenhar_campo(tela, frame)
        desenhar_jogadores(tela, jogadores)
        cv2.putText(tela, f"Frame {frame_n}", (20, 35), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (40, 40, 40), 2)
        desenhar(tela, traj_bola, (0, 140, 255), 6, "bola")
        desenhar(tela, traj_jogador, (255, 0, 0), 8, "jogador")
        saida.write(tela)

    video.release()
    saida.release()
    print(f"Gerado: {saida_path}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("entrada", nargs="?", default="teste[0-9].mp4")
    args = parser.parse_args()

    caminho = Path(args.entrada)
    videos = [caminho] if caminho.is_file() else sorted(BASE.glob(args.entrada))
    videos = [video for video in videos if "_trajetoria" not in video.stem]

    if not videos:
        raise SystemExit(f"Nenhum video encontrado: {args.entrada}")

    for video in videos:
        processar(video if video.is_absolute() else BASE / video)


if __name__ == "__main__":
    main()
