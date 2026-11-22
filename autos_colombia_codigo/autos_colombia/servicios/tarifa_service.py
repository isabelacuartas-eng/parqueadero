"""Parametrización de tarifas (RF-09)."""
from datetime import datetime

from datos.db import TARIFAS_DEFECTO, col
from servicios.errores import ReglaNegocioError


class TarifaService:
    def obtener_todas(self) -> dict:
        """Devuelve {concepto: valor}. Si falta alguno usa el valor por defecto."""
        t = dict(TARIFAS_DEFECTO)
        for x in col("tarifas").find({}):
            t[x["concepto"]] = x["valor"]
        return t

    def actualizar(self, valores: dict, id_usuario: int):
        """RF-09: valores positivos (en pesos) para cada concepto; la tolerancia va de 0 a 60 minutos."""
        nuevos = {}
        for concepto in TARIFAS_DEFECTO:
            bruto = str(valores.get(concepto, "")).strip().replace(".", "").replace(",", "")
            if not bruto.isdigit():
                raise ReglaNegocioError(f"El valor de {concepto.replace('_', ' ').lower()} debe ser un número entero.")
            v = int(bruto)
            if concepto == "TOLERANCIA_MIN":
                if not 0 <= v <= 60:
                    raise ReglaNegocioError("La tolerancia debe estar entre 0 y 60 minutos.")
            elif not 1 <= v <= 10_000_000:
                raise ReglaNegocioError(f"El valor de {concepto.replace('_', ' ').lower()} debe ser mayor a 0.")
            nuevos[concepto] = v
        for concepto, v in nuevos.items():
            col("tarifas").update_one({"concepto": concepto},
                                      {"$set": {"valor": v, "actualizado": datetime.now(),
                                                "id_usuario": id_usuario}}, upsert=True)
