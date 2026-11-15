"""Gestión de entrada y salida de vehículos (iteración 1) con reglas de la iteración 2."""
import re
from datetime import datetime

from datos.db import DuplicateKeyError, ReturnDocument, col, siguiente_id
from modelo.entidades import TIPOS_VEHICULO, Celda, Contrato, Usuario, Vehiculo
from servicios.errores import ReglaNegocioError


class MovimientoService:
    def registrar_vehiculo(self, placa, marca, color, tipo, documento):
        placa = (placa or "").strip().upper()
        if not re.fullmatch(r"[A-Z0-9]{5,7}", placa):
            raise ReglaNegocioError("La placa no es válida (5 a 7 letras o números).")
        if tipo not in TIPOS_VEHICULO:
            raise ReglaNegocioError("Tipo de vehículo no válido.")
        u = col("usuarios").find_one({"documento": (documento or "").strip()})
        if not u:
            raise ReglaNegocioError("No existe un usuario con ese documento.")
        if col("vehiculos").find_one({"placa": placa}):
            raise ReglaNegocioError("Ya existe un vehículo con esa placa.")
        try:
            col("vehiculos").insert_one({"id_vehiculo": siguiente_id("vehiculos"), "placa": placa,
                                         "marca": (marca or "").strip(), "color": (color or "").strip(),
                                         "tipo": tipo, "id_usuario": u["id_usuario"]})
        except DuplicateKeyError:
            raise ReglaNegocioError("Ya existe un vehículo con esa placa.")

    def registrar_entrada(self, placa: str, observacion: str = "", id_operador=None) -> str:
        placa = (placa or "").strip().upper()
        veh = Vehiculo.desde_doc(col("vehiculos").find_one({"placa": placa}))
        if not veh:
            raise ReglaNegocioError("Placa no registrada. Registre primero el vehículo.")
        usr = Usuario.desde_doc(col("usuarios").find_one({"id_usuario": veh.id_usuario}))
        if not usr or not usr.esta_activo():
            raise ReglaNegocioError("El propietario del vehículo está inactivo.")
        if col("movimientos").find_one({"id_vehiculo": veh.id_vehiculo, "abierto": True}):
            raise ReglaNegocioError("El vehículo ya se encuentra dentro del parqueadero.")

        celda, propia = None, False
        contrato = Contrato.desde_doc(col("contratos").find_one(
            {"id_usuario": veh.id_usuario, "estado": "ACTIVO", "fecha_fin": {"$gte": datetime.now()}}))
        if contrato:  # mensualidad: usa su celda reservada si es del tipo de su vehículo
            c = Celda.desde_doc(col("celdas").find_one({"id_celda": contrato.id_celda}))
            if c and c.tipo == veh.tipo and c.estado == "RESERVADA":
                celda, propia = c, True
        if not celda:
            # asignación atómica: la celda DISPONIBLE pasa a OCUPADA en una sola operación (RNF-03).
            # Las celdas ocupadas, en mantenimiento o reservadas nunca se asignan (RF-06, RF-08).
            celda = Celda.desde_doc(col("celdas").find_one_and_update(
                {"tipo": veh.tipo, "estado": "DISPONIBLE"}, {"$set": {"estado": "OCUPADA"}},
                sort=[("codigo", 1)], return_document=ReturnDocument.AFTER))
            if not celda:
                raise ReglaNegocioError("No hay celdas disponibles para este tipo de vehículo.")
        try:
            col("movimientos").insert_one({
                "id_movimiento": siguiente_id("movimientos"), "id_vehiculo": veh.id_vehiculo,
                "id_celda": celda.id_celda, "fecha_entrada": datetime.now(), "fecha_salida": None,
                "observacion": (observacion or "").strip(), "abierto": True, "id_operador": id_operador})
        except DuplicateKeyError:
            if not propia:
                col("celdas").update_one({"id_celda": celda.id_celda}, {"$set": {"estado": "DISPONIBLE"}})
            raise ReglaNegocioError("El vehículo o la celda ya tienen un movimiento abierto.")
        return celda.codigo

    def registrar_salida(self, id_movimiento: int) -> None:
        mov = col("movimientos").find_one_and_update(
            {"id_movimiento": id_movimiento, "abierto": True},
            {"$set": {"abierto": False, "fecha_salida": datetime.now()}}, return_document=True)
        if not mov:
            raise ReglaNegocioError("El movimiento no existe o ya fue cerrado.")
        # solo se libera la celda si estaba OCUPADA; una reservada sigue reservada
        col("celdas").update_one({"id_celda": mov["id_celda"], "estado": "OCUPADA"},
                                 {"$set": {"estado": "DISPONIBLE"}})

    def _unir(self, movimientos):
        filas = []
        for m in movimientos:
            v = col("vehiculos").find_one({"id_vehiculo": m["id_vehiculo"]}) or {}
            c = col("celdas").find_one({"id_celda": m["id_celda"]}) or {}
            filas.append({"id_movimiento": m["id_movimiento"], "placa": v.get("placa", ""),
                          "marca": v.get("marca", ""), "codigo": c.get("codigo", ""),
                          "fecha_entrada": m["fecha_entrada"], "fecha_salida": m.get("fecha_salida")})
        return filas

    def listar_vehiculos_dentro(self):
        dentro = self._unir(col("movimientos").find({"abierto": True}).sort("fecha_entrada", -1))
        libres = col("celdas").count_documents({"estado": "DISPONIBLE"})
        return dentro, libres

    def listar_historial(self):
        return self._unir(col("movimientos").find({}).sort("fecha_entrada", -1))
