"""Paquete datos: conexión y creación de la base de datos SQLite."""
import os
import sqlite3

BASE = os.path.dirname(os.path.abspath(__file__))
RUTA_DB = os.path.join(BASE, "..", "parqueadero.db")


def conectar():
    con = sqlite3.connect(RUTA_DB)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON")
    return con


def inicializar():
    con = conectar()
    with open(os.path.join(BASE, "schema.sql"), encoding="utf-8") as f:
        con.executescript(f.read())
    if con.execute("SELECT COUNT(*) FROM celda").fetchone()[0] == 0:
        for i in range(1, 11):
            con.execute("INSERT INTO celda(codigo,id_tipo) VALUES (?,1)", (f"C-{i:02d}",))
        for i in range(1, 6):
            con.execute("INSERT INTO celda(codigo,id_tipo) VALUES (?,2)", (f"M-{i:02d}",))
        con.execute("INSERT INTO usuario(documento,nombre,telefono) VALUES ('1001','Ana Gómez','3001112233')")
        con.execute("INSERT INTO vehiculo(placa,marca,color,id_tipo,id_usuario) VALUES ('ABC123','Mazda','Rojo',1,1)")
    con.commit()
    con.close()
