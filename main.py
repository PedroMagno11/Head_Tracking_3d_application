import serial
import numpy as np
import pygame
from pygame.locals import *
from OpenGL.GL import *
from OpenGL.GLU import *

# ==============================
# ⚙️ CONFIGURAÇÕES
# ==============================
PORTA_SERIAL = "COM3"    # altere conforme necessário
BAUD_RATE = 9600
ESCALA = 1 / 70.0
TIMEOUT = 1

# ==============================
# 🔌 CONEXÃO SERIAL
# ==============================
ser = serial.Serial(PORTA_SERIAL, BAUD_RATE, timeout=TIMEOUT)
print(f"✅ Conectado à {PORTA_SERIAL}")

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
# 🎥 LOOP PRINCIPAL OPENGL
# ==============================
pygame.init()
display = (800, 600)
pygame.display.set_mode(display, DOUBLEBUF | OPENGL)
pygame.display.set_caption("GY-50 3D Viewer (Pygame + OpenGL)")

gluPerspective(45, (display[0]/display[1]), 0.1, 50.0)
glTranslatef(0.0, 0.0, -7)

angle_x = angle_y = angle_z = 0

clock = pygame.time.Clock()

# ==============================

# 🔁 LOOP
# ==============================
while True:
    for event in pygame.event.get():
        if event.type == pygame.QUIT:
            ser.close()
            pygame.quit()
            quit()

    # Lê a linha do sensor
    linha = ser.readline().decode('utf-8', errors='ignore').strip()
    if linha.startswith("$HT"):
        try:
            partes = linha.split(",")
            gx = float(partes[1])
            gy = float(partes[2])
            gz = float(partes[3])

            angle_x += gx * ESCALA
            angle_y += gy * ESCALA
            angle_z += gz * ESCALA
        except:
            pass

    # Limpa e aplica rotação
    glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT)
    glPushMatrix()

    glRotatef(angle_x, 1, 0, 0)
    glRotatef(angle_y, 0, 1, 0)
    glRotatef(angle_z, 0, 0, 1)

    desenhar_cubo()
    glPopMatrix()

    pygame.display.flip()
    clock.tick(60)
