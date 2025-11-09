import serial
import time
import math
import pygame
from pygame.locals import *
from OpenGL.GL import *
from OpenGL.GLU import *

# ==============================
# ⚙️ CONFIGURAÇÕES
# ==============================
PORTA_SERIAL = "COM5"     # altere conforme necessário (ex.: "/dev/ttyUSB0")
BAUD_RATE    = 230400     # combine com o firmware do head_tracker
TIMEOUT_S    = 0.05       # leitura não bloqueante
FPS_TARGET   = 60

# Prioridade de fonte: True => usa $HT (ângulos) primeiro; False => usa $HTGR (giros) primeiro
PRIORIZA_HT  = True

# Suavização leve nos ângulos renderizados (0..1). 0 = sem filtro; 0.1-0.2 = suave
SUAVIZACAO_ANGULO = 0.12

# ==============================
# 🔌 CONEXÃO SERIAL
# ==============================
try:
    ser = serial.Serial(PORTA_SERIAL, BAUD_RATE, timeout=TIMEOUT_S)
    print(f"✅ Conectado à {PORTA_SERIAL} @ {BAUD_RATE} bps")
except Exception as e:
    print(f"❌ Não foi possível abrir {PORTA_SERIAL}: {e}")
    raise

# ==============================
# 📡 PARSER NMEA
# ==============================
def nmea_checksum_ok(sentence: str) -> bool:
    """
    Verifica checksum NMEA.
    Aceita strings como: $TAG,foo,bar*b6\r\n
    """
    try:
        if not sentence.startswith("$"):
            return False
        # remove CR/LF
        s = sentence.strip()
        if "*" not in s:
            return False
        body, cs_hex = s[1:].split("*", 1)  # remove '$' e separa checksum
        cs_calc = 0
        for ch in body:
            cs_calc ^= ord(ch)
        cs_recv = int(cs_hex[:2], 16)
        return cs_calc == cs_recv
    except Exception:
        return False

def parse_nmea(sentence: str):
    """
    Retorna (tag, [campos como float]) se OK, senão (None, None).
    Ignora erro de conversão.
    """
    if not nmea_checksum_ok(sentence):
        return None, None
    s = sentence.strip()[1:]             # remove '$'
    bloco, _ = s.split("*", 1)           # "TAG,payload"
    parts = bloco.split(",")
    tag = parts[0].upper()
    vals = []
    for p in parts[1:]:
        try:
            vals.append(float(p))
        except:
            vals.append(float("nan"))
    return tag, vals

# ==============================
# 🎨 DEFINIÇÃO DO CUBO
# ==============================
vertices = [
    [1, 1, -1],
    [1, -1, -1],
    [-1, -1, -1],
    [-1, 1, -1],
    [1, 1, 1],
    [1, -1, 1],
    [-1, -1, 1],
    [-1, 1, 1]
]

arestas = (
    (0,1), (1,2), (2,3), (3,0),
    (4,5), (5,6), (6,7), (7,4),
    (0,4), (1,5), (2,6), (3,7)
)

faces = (
    (0,1,2,3),
    (4,5,6,7),
    (0,1,5,4),
    (2,3,7,6),
    (1,2,6,5),
    (0,3,7,4)
)

colors = [
    (1,0,0),
    (0,1,0),
    (0,0,1),
    (1,1,0),
    (1,0,1),
    (0,1,1)
]

def desenhar_cubo():
    glBegin(GL_QUADS)
    for i, face in enumerate(faces):
        glColor3fv(colors[i % len(colors)])
        for vert in face:
            glVertex3fv(vertices[vert])
    glEnd()

    glColor3fv((0,0,0))
    glBegin(GL_LINES)
    for edge in arestas:
        for vert in edge:
            glVertex3fv(vertices[vert])
    glEnd()

# ==============================
# 🎥 OPENGL / PYGAME
# ==============================
pygame.init()
display = (900, 700)
pygame.display.set_mode(display, DOUBLEBUF | OPENGL)
pygame.display.set_caption("Head Tracker 3D Viewer (NMEA $HT/$HTGR)")
glEnable(GL_DEPTH_TEST)
glClearColor(0.95, 0.95, 0.95, 1.0)

gluPerspective(45, (display[0]/display[1]), 0.1, 50.0)
glTranslatef(0.0, 0.0, -7)

clock = pygame.time.Clock()

# Ângulos (graus)
pitch = roll = yaw = 0.0          # estimados a partir do dispositivo
pitch_vis = roll_vis = yaw_vis = 0.0  # suavizados para render

# Integração quando usar $HTGR
last_time = time.perf_counter()

# Zero/centro
center_pitch = center_roll = center_yaw = 0.0

# Últimas medidas recebidas (para debug/diagnóstico)
ultimo_HT   = None
ultimo_HTGR = None
ultimo_HTAC = None
ultimo_HTMG = None

def aplica_centro(p, r, y):
    return (p - center_pitch, r - center_roll, y - center_yaw)

def ema(prev, novo, alpha):
    if alpha <= 0.0:  return novo
    if alpha >= 1.0:  return prev
    return prev + alpha * (novo - prev)

# ==============================
# 🔁 LOOP PRINCIPAL
# ==============================
rodando = True
while rodando:
    for event in pygame.event.get():
        if event.type == pygame.QUIT:
            rodando = False
        elif event.type == pygame.KEYDOWN:
            if event.key == pygame.K_ESCAPE:
                rodando = False
            elif event.key == pygame.K_c:
                # centraliza (zera pose atual)
                center_pitch, center_roll, center_yaw = pitch, roll, yaw
                print("↘️  CENTER aplicado.")
            elif event.key == pygame.K_r:
                # reseta
                pitch = roll = yaw = 0.0
                pitch_vis = roll_vis = yaw_vis = 0.0
                center_pitch = center_roll = center_yaw = 0.0
                print("🔄 Reset de ângulos e centro.")
            elif event.key == pygame.K_s:
                PRIORIZA_HT = not PRIORIZA_HT
                print("🔀 Prioridade:", "HT → HTGR" if PRIORIZA_HT else "HTGR → HT")

    # tempo para integração ($HTGR)
    now = time.perf_counter()
    dt = now - last_time
    last_time = now
    if dt <= 0.0 or dt > 0.05:
        dt = 1.0 / 250.0  # protege contra stalls

    # leitura serial (pode chegar várias linhas por frame)
    try:
        linha = ser.readline().decode('utf-8', errors='ignore').strip()
        # drena buffer rápido para diminuir latência, mantendo só a última leitura útil
        # (pega até ~10 linhas por frame para não travar render)
        for _ in range(10):
            if ser.in_waiting <= 0:
                break
            extra = ser.readline().decode('utf-8', errors='ignore').strip()
            if extra:
                linha = extra  # mantém a mais recente
    except Exception:
        linha = ""

    # atualiza estimativa conforme prioridade e mensagens disponíveis
    if linha.startswith("$"):
        tag, vals = parse_nmea(linha)
        if tag is not None:
            if tag == "HT" and len(vals) >= 3:
                ultimo_HT = vals
                if PRIORIZA_HT:
                    p, r, y = vals[0], vals[1], vals[2]
                    pitch, roll, yaw = aplica_centro(p, r, y)
            elif tag == "HTGR" and len(vals) >= 3:
                ultimo_HTGR = vals
                if not PRIORIZA_HT:
                    gx, gy, gz = vals[0], vals[1], vals[2]  # °/s
                    pitch += gx * dt
                    roll  += gy * dt
                    yaw   += gz * dt
                    pitch, roll, yaw = aplica_centro(pitch, roll, yaw)
            elif tag == "HTAC" and len(vals) >= 3:
                ultimo_HTAC = vals
            elif tag == "HTMG" and len(vals) >= 3:
                ultimo_HTMG = vals

            # fallback: se prioriza HT mas só veio HTGR (ou vice-versa), atualiza mesmo assim
            if PRIORIZA_HT and tag == "HTGR" and ultimo_HT is None:
                gx, gy, gz = vals[0], vals[1], vals[2]
                pitch += gx * dt
                roll  += gy * dt
                yaw   += gz * dt
                pitch, roll, yaw = aplica_centro(pitch, roll, yaw)
            if not PRIORIZA_HT and tag == "HT" and ultimo_HTGR is None:
                p, r, y = vals[0], vals[1], vals[2]
                pitch, roll, yaw = aplica_centro(p, r, y)

    # suavização leve só para render (evita jitter visual)
    pitch_vis = ema(pitch_vis, pitch, SUAVIZACAO_ANGULO)
    roll_vis  = ema(roll_vis,  roll,  SUAVIZACAO_ANGULO)
    yaw_vis   = ema(yaw_vis,   yaw,   SUAVIZACAO_ANGULO)

    # ============ RENDER ============
    glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT)
    glPushMatrix()

    # Aplica rotações (mesma convenção do firmware: Pitch=X, Roll=Y, Yaw=Z)
    glRotatef(pitch_vis, 1, 0, 0)  # X
    glRotatef(roll_vis,  0, 1, 0)  # Y
    glRotatef(yaw_vis,   0, 0, 1)  # Z

    desenhar_cubo()
    glPopMatrix()
    pygame.display.set_caption(
        f"Head Tracker 3D Viewer — Fonte: {'HT' if PRIORIZA_HT else 'HTGR'} | "
        f"P:{pitch_vis:6.2f} R:{roll_vis:6.2f} Y:{yaw_vis:6.2f}"
    )
    pygame.display.flip()
    clock.tick(FPS_TARGET)

# Encerramento
ser.close()
pygame.quit()
