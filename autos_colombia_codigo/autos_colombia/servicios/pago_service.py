"""Gestión de pagos (iteración 3): cobro de salida, mensualidad, comprobante, anulación y reporte."""
import math
from datetime import date, datetime, time, timedelta

from datos.db import DuplicateKeyError, col, siguiente_id
from modelo.entidades import Contrato, Movimiento, Usuario, Vehiculo
from servicios.errores import ReglaNegocioError
from servicios.movimiento_service import MovimientoService
from servicios.tarifa_service import TarifaService

METODOS = ("EFECTIVO", "TRANSFERENCIA", "TARJETA")
DIAS_MENSUALIDAD = 30


def calcular_cobro(entrada: datetime, salida: datetime, valor_hora: int, tolerancia_min: int):
    """RF-11: devuelve (minutos, horas_cobradas, valor).
    Dentro de la tolerancia no se cobra; después se cobra por hora o fracción (mínimo una hora)."""
    minutos = math.ceil(max(0, (salida - entrada).total_seconds()) / 60)
    if minutos <= tolerancia_min:
        return minutos, 0, 0
    horas = max(1, math.ceil(minutos / 60))
    return minutos, horas, horas * valor_hora


class PagoService:
    def __init__(self):
        self._tarifas = TarifaService()
        self._mov = MovimientoService()

    # ---------- utilidades ----------
    def _validar_metodo(self, metodo, referencia):
        metodo = (metodo or "").strip().upper()
        if metodo not in METODOS:
            raise ReglaNegocioError("Seleccione un método de pago válido.")
        referencia = (referencia or "").strip()
        if metodo != "EFECTIVO" and not referencia:
            raise ReglaNegocioError("La referencia es obligatoria para pagos por transferencia o tarjeta.")
        return metodo, referencia

    def _insertar(self, **campos) -> dict:
        id_pago = siguiente_id("pagos")
        doc = {"id_pago": id_pago, "consecutivo": f"PG-{id_pago:06d}", "fecha": datetime.now(),
               "estado": "VALIDO", **campos}
        try:
            col("pagos").insert_one(doc)
        except DuplicateKeyError:
            raise ReglaNegocioError("Este movimiento ya tiene un cobro registrado.")
        return doc

    def _es_titular_en_su_celda(self, veh: Vehiculo, mov: Movimiento) -> bool:
        c = col("contratos").find_one({"id_usuario": veh.id_usuario, "estado": "ACTIVO",
                                       "id_celda": mov.id_celda})
        return c is not None

    # ---------- cobro a la salida (RF-11) ----------
    def vista_previa_salida(self, id_movimiento: int) -> dict:
        mov = Movimiento.desde_doc(col("movimientos").find_one({"id_movimiento": id_movimiento, "abierto": True}))
        if not mov:
            raise ReglaNegocioError("El movimiento no existe o ya fue cerrado.")
        veh = Vehiculo.desde_doc(col("vehiculos").find_one({"id_vehiculo": mov.id_vehiculo}))
        usr = Usuario.desde_doc(col("usuarios").find_one({"id_usuario": veh.id_usuario}))
        celda = col("celdas").find_one({"id_celda": mov.id_celda})
        t = self._tarifas.obtener_todas()
        ahora = datetime.now()
        titular = self._es_titular_en_su_celda(veh, mov)
        minutos, horas, valor = calcular_cobro(mov.fecha_entrada, ahora, t["HORA_" + veh.tipo], t["TOLERANCIA_MIN"])
        return {"id_movimiento": mov.id_movimiento, "placa": veh.placa, "tipo": veh.tipo,
                "propietario": usr.nombre_completo(), "celda": celda["codigo"], "entrada": mov.fecha_entrada,
                "ahora": ahora, "minutos": minutos, "horas": horas, "valor": 0 if titular else valor,
                "titular": titular, "valor_hora": t["HORA_" + veh.tipo], "tolerancia": t["TOLERANCIA_MIN"]}

    def registrar_salida_con_cobro(self, id_movimiento, metodo, referencia, id_operador):
        """Cierra el movimiento, libera la celda y registra el cobro. Devuelve el pago o None si no hubo cobro."""
        mov = Movimiento.desde_doc(col("movimientos").find_one({"id_movimiento": id_movimiento, "abierto": True}))
        if not mov:
            raise ReglaNegocioError("El movimiento no existe o ya fue cerrado.")
        veh = Vehiculo.desde_doc(col("vehiculos").find_one({"id_vehiculo": mov.id_vehiculo}))
        titular = self._es_titular_en_su_celda(veh, mov)
        if not titular:
            metodo, referencia = self._validar_metodo(metodo, referencia)  # se valida antes de cerrar
        cerrado = self._mov.registrar_salida(id_movimiento)  # cierre atómico: solo un proceso puede cerrar
        if titular:
            return None
        t = self._tarifas.obtener_todas()
        minutos, horas, valor = calcular_cobro(cerrado["fecha_entrada"], cerrado["fecha_salida"],
                                               t["HORA_" + veh.tipo], t["TOLERANCIA_MIN"])
        if valor == 0:
            return None
        return self._insertar(
            tipo="OCASIONAL", id_usuario=veh.id_usuario, id_vehiculo=veh.id_vehiculo,
            id_movimiento=id_movimiento, concepto=f"Parqueadero {veh.tipo.lower()} {veh.placa}: {horas} h",
            minutos=minutos, horas=horas, valor=valor, metodo=metodo, referencia=referencia,
            id_operador=id_operador)

    # ---------- pago de mensualidad (RF-10) ----------
    def registrar_pago_mensualidad(self, documento, metodo, referencia, id_operador) -> dict:
        usr = Usuario.desde_doc(col("usuarios").find_one({"documento": (documento or "").strip()}))
        if not usr:
            raise ReglaNegocioError("No existe un usuario con ese documento.")
        if not usr.esta_activo():
            raise ReglaNegocioError("El cliente está inactivo.")
        contrato = Contrato.desde_doc(col("contratos").find_one({"id_usuario": usr.id_usuario, "estado": "ACTIVO"}))
        if not contrato:
            raise ReglaNegocioError("El cliente no tiene una mensualidad activa. "
                                    "Asigne primero una celda en el módulo Mensualidades.")
        metodo, referencia = self._validar_metodo(metodo, referencia)
        celda = col("celdas").find_one({"id_celda": contrato.id_celda})
        valor = self._tarifas.obtener_todas()["MENSUALIDAD_" + celda["tipo"]]
        base = max(contrato.fecha_fin, datetime.now())
        r = col("contratos").update_one({"id_contrato": contrato.id_contrato, "estado": "ACTIVO"},
                                        {"$set": {"fecha_fin": base + timedelta(days=DIAS_MENSUALIDAD)}})
        if r.matched_count == 0:
            raise ReglaNegocioError("El contrato cambió de estado mientras se procesaba el pago.")
        try:
            return self._insertar(
                tipo="MENSUALIDAD", id_usuario=usr.id_usuario, id_contrato=contrato.id_contrato,
                concepto=f"Mensualidad celda {celda['codigo']} (+{DIAS_MENSUALIDAD} días)",
                dias_extendidos=DIAS_MENSUALIDAD, valor=valor, metodo=metodo, referencia=referencia,
                id_operador=id_operador)
        except Exception:
            col("contratos").update_one({"id_contrato": contrato.id_contrato},
                                        {"$set": {"fecha_fin": contrato.fecha_fin}})
            raise

    # ---------- anulación (RF-15) ----------
    def anular(self, id_pago: int, motivo: str, id_admin: int):
        motivo = (motivo or "").strip()
        if len(motivo) < 5:
            raise ReglaNegocioError("Indique el motivo de la anulación (mínimo 5 caracteres).")
        p = col("pagos").find_one_and_update(
            {"id_pago": id_pago, "estado": "VALIDO"},
            {"$set": {"estado": "ANULADO", "motivo_anulacion": motivo, "fecha_anulacion": datetime.now(),
                      "id_anulador": id_admin}}, return_document=True)
        if not p:
            if col("pagos").find_one({"id_pago": id_pago}):
                raise ReglaNegocioError("El pago ya fue anulado.")
            raise ReglaNegocioError("El pago no existe.")
        if p["tipo"] == "MENSUALIDAD":  # revierte los días que había sumado
            c = col("contratos").find_one({"id_contrato": p["id_contrato"], "estado": "ACTIVO"})
            if c:
                col("contratos").update_one({"id_contrato": c["id_contrato"], "estado": "ACTIVO"},
                                            {"$set": {"fecha_fin": c["fecha_fin"] - timedelta(days=p["dias_extendidos"])}})

    # ---------- consultas (RF-12, RF-13, RF-14) ----------
    def _enriquecer(self, p: dict) -> dict:
        u = col("usuarios").find_one({"id_usuario": p["id_usuario"]}) or {}
        o = col("usuarios").find_one({"id_usuario": p.get("id_operador")}) or {}
        v = col("vehiculos").find_one({"id_vehiculo": p.get("id_vehiculo")}) or {}
        p = dict(p)
        p.update(cliente=f"{u.get('nombres', '')} {u.get('apellidos', '')}".strip(), documento=u.get("documento", ""),
                 cliente_estado=u.get("estado", ""), operador=f"{o.get('nombres', '')} {o.get('apellidos', '')}".strip(),
                 placa=v.get("placa", ""))
        return p

    def _filtro(self, desde=None, hasta=None, tipo="", metodo="", documento="", estado="", id_operador=None):
        f = {}
        if desde or hasta:
            f["fecha"] = {}
            if desde:
                f["fecha"]["$gte"] = datetime.combine(desde, time.min)
            if hasta:
                f["fecha"]["$lte"] = datetime.combine(hasta, time.max)
        for k, v in (("tipo", tipo), ("metodo", metodo), ("estado", estado)):
            if v:
                f[k] = v
        if documento:
            u = col("usuarios").find_one({"documento": documento.strip()})
            f["id_usuario"] = u["id_usuario"] if u else -1
        if id_operador is not None:
            f["id_operador"] = id_operador
        return f

    def listar(self, **filtros):
        pagos = col("pagos").find(self._filtro(**filtros)).sort("fecha", -1)
        filas = [self._enriquecer(p) for p in pagos]
        total = sum(p["valor"] for p in filas if p["estado"] == "VALIDO")
        return filas, total

    def obtener(self, id_pago: int) -> dict:
        p = col("pagos").find_one({"id_pago": id_pago})
        if not p:
            raise ReglaNegocioError("El pago no existe.")
        p = self._enriquecer(p)
        if p.get("id_movimiento"):
            m = col("movimientos").find_one({"id_movimiento": p["id_movimiento"]}) or {}
            p["entrada"], p["salida"] = m.get("fecha_entrada"), m.get("fecha_salida")
        if p.get("id_contrato"):
            c = col("contratos").find_one({"id_contrato": p["id_contrato"]}) or {}
            p["vigente_hasta"] = c.get("fecha_fin")
        return p

    def reporte(self, desde: date, hasta: date) -> dict:
        """RF-14: recaudo por tipo, método, operador y día. Los pagos anulados no se suman."""
        r = {"total": 0, "cantidad": 0, "anulados": 0, "valor_anulado": 0,
             "por_tipo": {}, "por_metodo": {}, "por_operador": {}, "por_dia": {}}
        pagos = [self._enriquecer(p) for p in col("pagos").find(self._filtro(desde=desde, hasta=hasta))]
        for p in pagos:
            if p["estado"] == "ANULADO":
                r["anulados"] += 1
                r["valor_anulado"] += p["valor"]
                continue
            r["total"] += p["valor"]
            r["cantidad"] += 1
            for clave, k in (("por_tipo", p["tipo"]), ("por_metodo", p["metodo"]),
                             ("por_operador", p["operador"]), ("por_dia", p["fecha"].strftime("%Y-%m-%d"))):
                d = r[clave].setdefault(k, {"n": 0, "total": 0})
                d["n"] += 1
                d["total"] += p["valor"]
        r["por_dia"] = dict(sorted(r["por_dia"].items()))
        return r
