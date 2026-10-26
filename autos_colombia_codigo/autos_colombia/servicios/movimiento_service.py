"""Paquete servicios: reglas de negocio de entrada y salida."""
from datetime import datetime

from datos.db import conectar
from modelo.entidades import Celda, Movimiento, Usuario, Vehiculo


class ReglaNegocioError(Exception):
    """Se lanza cuando una operación incumple una regla de negocio."""


class MovimientoService:
    def _ahora(self):
        return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    def registrar_entrada(self, placa: str, observacion: str = "") -> str:
        placa = placa.strip().upper()
        con = conectar()
        try:
            fila = con.execute("SELECT * FROM vehiculo WHERE placa=?", (placa,)).fetchone()
            if not fila:
                raise ReglaNegocioError("Placa no registrada. Registre primero el vehículo.")
            veh = Vehiculo(**dict(fila))
            usr = Usuario(**dict(con.execute("SELECT * FROM usuario WHERE id_usuario=?",
                                             (veh.id_usuario,)).fetchone()))
            if not usr.esta_activo():
                raise ReglaNegocioError("El usuario no tiene mensualidad activa.")
            if con.execute("SELECT 1 FROM movimiento WHERE id_vehiculo=? AND fecha_salida IS NULL",
                           (veh.id_vehiculo,)).fetchone():
                raise ReglaNegocioError("El vehículo ya se encuentra dentro del parqueadero.")
            fc = con.execute("SELECT * FROM celda WHERE estado='DISPONIBLE' AND id_tipo=? "
                             "ORDER BY codigo LIMIT 1", (veh.id_tipo,)).fetchone()
            if not fc:
                raise ReglaNegocioError("No hay celdas disponibles para este tipo de vehículo.")
            celda = Celda(**dict(fc))
            celda.ocupar()
            con.execute("INSERT INTO movimiento(id_vehiculo,id_celda,fecha_entrada,observacion) "
                        "VALUES (?,?,?,?)", (veh.id_vehiculo, celda.id_celda, self._ahora(), observacion))
            con.execute("UPDATE celda SET estado=? WHERE id_celda=?", (celda.estado, celda.id_celda))
            con.commit()
            return celda.codigo
        finally:
            con.close()

    def registrar_salida(self, id_movimiento: int) -> None:
        con = conectar()
        try:
            fila = con.execute("SELECT * FROM movimiento WHERE id_movimiento=?", (id_movimiento,)).fetchone()
            if not fila:
                raise ReglaNegocioError("Movimiento no encontrado.")
            mov = Movimiento(**dict(fila))
            if not mov.esta_abierto():
                raise ReglaNegocioError("El movimiento ya fue cerrado.")
            con.execute("UPDATE movimiento SET fecha_salida=? WHERE id_movimiento=?",
                        (self._ahora(), id_movimiento))
            celda = Celda(**dict(con.execute("SELECT * FROM celda WHERE id_celda=?",
                                             (mov.id_celda,)).fetchone()))
            celda.liberar()
            con.execute("UPDATE celda SET estado=? WHERE id_celda=?", (celda.estado, celda.id_celda))
            con.commit()
        finally:
            con.close()

    def listar_vehiculos_dentro(self):
        con = conectar()
        filas = con.execute(
            """SELECT m.id_movimiento, v.placa, v.marca, c.codigo, m.fecha_entrada
               FROM movimiento m JOIN vehiculo v USING(id_vehiculo) JOIN celda c USING(id_celda)
               WHERE m.fecha_salida IS NULL ORDER BY m.fecha_entrada DESC""").fetchall()
        libres = con.execute("SELECT COUNT(*) FROM celda WHERE estado='DISPONIBLE'").fetchone()[0]
        con.close()
        return filas, libres

    def listar_historial(self):
        con = conectar()
        filas = con.execute(
            """SELECT v.placa, c.codigo, m.fecha_entrada, m.fecha_salida
               FROM movimiento m JOIN vehiculo v USING(id_vehiculo) JOIN celda c USING(id_celda)
               ORDER BY m.fecha_entrada DESC""").fetchall()
        con.close()
        return filas
