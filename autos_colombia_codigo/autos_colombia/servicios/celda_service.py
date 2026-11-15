"""Gestión de celdas (RF-05, RF-06, RF-07)."""
from datos.db import DuplicateKeyError, col, siguiente_id
from modelo.entidades import TIPOS_VEHICULO, Celda
from servicios.errores import ReglaNegocioError

# Cambios manuales permitidos. OCUPADA solo la gestiona la entrada/salida de vehículos
# y RESERVADA solo la gestionan los contratos de mensualidad.
TRANSICIONES_MANUALES = {("DISPONIBLE", "MANTENIMIENTO"), ("MANTENIMIENTO", "DISPONIBLE")}


class CeldaService:
    def crear(self, codigo: str, zona: str, tipo: str) -> int:
        """RF-05: crea una celda con código único; estado inicial DISPONIBLE."""
        codigo, zona = (codigo or "").strip().upper(), (zona or "").strip()
        if not codigo or not zona:
            raise ReglaNegocioError("El código y la zona son obligatorios.")
        if tipo not in TIPOS_VEHICULO:
            raise ReglaNegocioError("Tipo de vehículo no válido.")
        if col("celdas").find_one({"codigo": codigo}):
            raise ReglaNegocioError("Ya existe una celda con ese código.")
        id_celda = siguiente_id("celdas")
        try:
            col("celdas").insert_one({"id_celda": id_celda, "codigo": codigo, "zona": zona, "tipo": tipo,
                                      "estado": "DISPONIBLE"})
        except DuplicateKeyError:
            raise ReglaNegocioError("Ya existe una celda con ese código.")
        return id_celda

    def obtener(self, id_celda: int) -> Celda:
        c = Celda.desde_doc(col("celdas").find_one({"id_celda": id_celda}))
        if not c:
            raise ReglaNegocioError("Celda no encontrada.")
        return c

    def listar(self, tipo: str = "", zona: str = ""):
        filtro = {}
        if tipo:
            filtro["tipo"] = tipo
        if zona:
            filtro["zona"] = zona
        return [Celda.desde_doc(x) for x in col("celdas").find(filtro).sort("codigo", 1)]

    def zonas(self):
        return sorted({c["zona"] for c in col("celdas").find({})})

    def en_uso(self):
        """Ids de celdas con un vehículo adentro en este momento."""
        return {m["id_celda"] for m in col("movimientos").find({"abierto": True})}

    def resumen(self, celdas):
        r = {"total": len(celdas), "DISPONIBLE": 0, "OCUPADA": 0, "MANTENIMIENTO": 0, "RESERVADA": 0}
        for c in celdas:
            r[c.estado] += 1
        return r

    def cambiar_estado(self, id_celda: int, nuevo: str):
        """RF-06: cambio manual de estado con transiciones controladas."""
        celda = self.obtener(id_celda)
        if (celda.estado, nuevo) not in TRANSICIONES_MANUALES:
            raise ReglaNegocioError(
                f"No se puede pasar la celda {celda.codigo} de {celda.estado} a {nuevo}. "
                "Una celda ocupada o reservada no se modifica manualmente.")
        # la condición sobre el estado actual hace el cambio atómico (RNF-03)
        r = col("celdas").update_one({"id_celda": id_celda, "estado": celda.estado}, {"$set": {"estado": nuevo}})
        if r.matched_count == 0:
            raise ReglaNegocioError("La celda cambió de estado mientras se procesaba la solicitud.")
