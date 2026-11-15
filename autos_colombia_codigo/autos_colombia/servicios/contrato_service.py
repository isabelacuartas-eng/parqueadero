"""Contratos de mensualidad: asignación de celdas reservadas (RF-08)."""
from datetime import datetime, timedelta

from datos.db import DuplicateKeyError, col, siguiente_id
from modelo.entidades import Celda, Contrato, Usuario
from servicios.errores import ReglaNegocioError


class ContratoService:
    def asignar(self, documento: str, id_celda: int, dias: int) -> int:
        cliente = Usuario.desde_doc(col("usuarios").find_one({"documento": (documento or "").strip()}))
        if not cliente:
            raise ReglaNegocioError("No existe un usuario con ese documento.")
        if not cliente.esta_activo():
            raise ReglaNegocioError("El cliente está inactivo.")
        if cliente.rol != "CLIENTE":
            raise ReglaNegocioError("Solo se pueden asignar mensualidades a usuarios con rol Cliente.")
        try:
            dias = int(dias)
        except (TypeError, ValueError):
            raise ReglaNegocioError("La vigencia debe ser un número de días.")
        if not 1 <= dias <= 365:
            raise ReglaNegocioError("La vigencia debe estar entre 1 y 365 días.")
        if col("contratos").find_one({"id_usuario": cliente.id_usuario, "estado": "ACTIVO"}):
            raise ReglaNegocioError("El cliente ya tiene una mensualidad activa.")
        # reserva atómica: solo una celda DISPONIBLE pasa a RESERVADA (RNF-03)
        reservada = Celda.desde_doc(col("celdas").find_one_and_update(
            {"id_celda": id_celda, "estado": "DISPONIBLE"}, {"$set": {"estado": "RESERVADA"}},
            return_document=True))
        if not reservada:
            raise ReglaNegocioError("La celda no está disponible para reservar.")
        ahora = datetime.now()
        id_contrato = siguiente_id("contratos")
        try:
            col("contratos").insert_one({"id_contrato": id_contrato, "id_usuario": cliente.id_usuario,
                                         "id_celda": id_celda, "fecha_inicio": ahora,
                                         "fecha_fin": ahora + timedelta(days=dias), "estado": "ACTIVO"})
        except DuplicateKeyError:
            col("celdas").update_one({"id_celda": id_celda}, {"$set": {"estado": "DISPONIBLE"}})
            raise ReglaNegocioError("El cliente o la celda ya tienen un contrato activo.")
        return id_contrato

    def finalizar(self, id_contrato: int):
        r = col("contratos").find_one_and_update({"id_contrato": id_contrato, "estado": "ACTIVO"},
                                                 {"$set": {"estado": "FINALIZADO"}}, return_document=True)
        if not r:
            raise ReglaNegocioError("El contrato no existe o ya fue finalizado.")
        # si el titular todavía está dentro, la celda queda OCUPADA hasta que salga
        dentro = col("movimientos").find_one({"id_celda": r["id_celda"], "abierto": True})
        col("celdas").update_one({"id_celda": r["id_celda"], "estado": "RESERVADA"},
                                 {"$set": {"estado": "OCUPADA" if dentro else "DISPONIBLE"}})

    def vencer_vencidos(self):
        """Finaliza los contratos cuya vigencia terminó."""
        for c in list(col("contratos").find({"estado": "ACTIVO", "fecha_fin": {"$lt": datetime.now()}})):
            self.finalizar(c["id_contrato"])

    def listar_activos(self):
        filas = []
        for c in col("contratos").find({"estado": "ACTIVO"}).sort("fecha_fin", 1):
            ct = Contrato.desde_doc(c)
            u = col("usuarios").find_one({"id_usuario": ct.id_usuario}) or {}
            ce = col("celdas").find_one({"id_celda": ct.id_celda}) or {}
            filas.append({"contrato": ct, "cliente": f"{u.get('nombres', '')} {u.get('apellidos', '')}".strip(),
                          "documento": u.get("documento", ""), "celda": ce.get("codigo", "")})
        return filas
