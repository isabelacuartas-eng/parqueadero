"""Paquete servicios: alta de usuarios y vehículos."""
import sqlite3

from datos.db import conectar
from servicios.movimiento_service import ReglaNegocioError


class RegistroService:
    def registrar_usuario(self, documento, nombre, telefono=""):
        con = conectar()
        try:
            con.execute("INSERT INTO usuario(documento,nombre,telefono) VALUES (?,?,?)",
                        (documento.strip(), nombre.strip(), telefono.strip()))
            con.commit()
        except sqlite3.IntegrityError:
            raise ReglaNegocioError("Ya existe un usuario con ese documento.")
        finally:
            con.close()

    def registrar_vehiculo(self, placa, marca, color, id_tipo, documento):
        con = conectar()
        try:
            u = con.execute("SELECT id_usuario FROM usuario WHERE documento=?", (documento.strip(),)).fetchone()
            if not u:
                raise ReglaNegocioError("No existe un usuario con ese documento.")
            con.execute("INSERT INTO vehiculo(placa,marca,color,id_tipo,id_usuario) VALUES (?,?,?,?,?)",
                        (placa.strip().upper(), marca.strip(), color.strip(), int(id_tipo), u["id_usuario"]))
            con.commit()
        except sqlite3.IntegrityError:
            raise ReglaNegocioError("Ya existe un vehículo con esa placa.")
        finally:
            con.close()
