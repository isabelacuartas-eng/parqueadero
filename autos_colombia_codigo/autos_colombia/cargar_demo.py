"""Carga datos de ejemplo (historial, clientes, mensualidades, celdas en mantenimiento...) para demostraciones.

Uso:
    py cargar_demo.py              agrega los datos de ejemplo (no duplica si ya se cargaron)
    py cargar_demo.py --limpiar    borra TODA la base y la vuelve a crear con los datos de ejemplo
"""
import sys
from datetime import datetime, timedelta

from werkzeug.security import generate_password_hash

from datos.db import col, inicializar, obtener_db, siguiente_id
from servicios.pago_service import calcular_cobro

CLAVE_DEMO = "Cliente123*"


def _usuario(tipo_doc, doc, nombres, apellidos, tel, correo, rol="CLIENTE", estado="ACTIVO"):
    existente = col("usuarios").find_one({"documento": doc})
    if existente:
        return existente["id_usuario"]
    id_u = siguiente_id("usuarios")
    col("usuarios").insert_one({
        "id_usuario": id_u, "tipo_documento": tipo_doc, "documento": doc, "nombres": nombres,
        "apellidos": apellidos, "telefono": tel, "correo": correo, "rol": rol,
        "password_hash": generate_password_hash(CLAVE_DEMO), "estado": estado, "creado": datetime.now()})
    return id_u


def _vehiculo(placa, marca, color, tipo, id_usuario):
    existente = col("vehiculos").find_one({"placa": placa})
    if existente:
        return existente["id_vehiculo"]
    id_v = siguiente_id("vehiculos")
    col("vehiculos").insert_one({"id_vehiculo": id_v, "placa": placa, "marca": marca, "color": color,
                                 "tipo": tipo, "id_usuario": id_usuario})
    return id_v


def _celda(codigo, zona, tipo):
    existente = col("celdas").find_one({"codigo": codigo})
    if existente:
        return existente["id_celda"]
    id_c = siguiente_id("celdas")
    col("celdas").insert_one({"id_celda": id_c, "codigo": codigo, "zona": zona, "tipo": tipo,
                              "estado": "DISPONIBLE"})
    return id_c


def _id_celda(codigo):
    return col("celdas").find_one({"codigo": codigo})["id_celda"]


def _movimiento(id_vehiculo, id_celda, entrada, salida=None, obs="", id_operador=2):
    col("movimientos").insert_one({
        "id_movimiento": siguiente_id("movimientos"), "id_vehiculo": id_vehiculo, "id_celda": id_celda,
        "fecha_entrada": entrada, "fecha_salida": salida, "observacion": obs,
        "abierto": salida is None, "id_operador": id_operador})


def _cargar_pagos():
    """Pagos de ejemplo: cobros de los movimientos cerrados de vehículos ocasionales y mensualidades."""
    ahora = datetime.now()
    t = {x["concepto"]: x["valor"] for x in col("tarifas").find({})}
    contratos = {c["id_usuario"]: c for c in col("contratos").find({})}
    operadores = [u["id_usuario"] for u in col("usuarios").find({"rol": "OPERADOR"})] or [2]
    n = 0
    for m in col("movimientos").find({"abierto": False}).sort("fecha_entrada", 1):
        v = col("vehiculos").find_one({"id_vehiculo": m["id_vehiculo"]})
        if v["id_usuario"] in contratos:
            continue  # titular de mensualidad: no paga por visita
        minutos, horas, valor = calcular_cobro(m["fecha_entrada"], m["fecha_salida"], t["HORA_" + v["tipo"]],
                                               t["TOLERANCIA_MIN"])
        if valor == 0:
            continue
        id_p = siguiente_id("pagos"); n += 1
        metodo = ("EFECTIVO", "TRANSFERENCIA", "TARJETA")[n % 3]
        col("pagos").insert_one({
            "id_pago": id_p, "consecutivo": f"PG-{id_p:06d}", "fecha": m["fecha_salida"], "estado": "VALIDO",
            "tipo": "OCASIONAL", "id_usuario": v["id_usuario"], "id_vehiculo": v["id_vehiculo"],
            "id_movimiento": m["id_movimiento"], "concepto": f"Parqueadero {v['tipo'].lower()} {v['placa']}: {horas} h",
            "minutos": minutos, "horas": horas, "valor": valor, "metodo": metodo,
            "referencia": "" if metodo == "EFECTIVO" else f"REF-{1000 + n}", "id_operador": operadores[n % len(operadores)]})
    for doc_cli, dias_atras, metodo, ref in (("1003", 10, "TRANSFERENCIA", "TRF-884201"), ("1005", 5, "EFECTIVO", "")):
        u = col("usuarios").find_one({"documento": doc_cli}); c = contratos.get(u["id_usuario"]) if u else None
        if not c:
            continue
        celda = col("celdas").find_one({"id_celda": c["id_celda"]})
        id_p = siguiente_id("pagos")
        col("pagos").insert_one({
            "id_pago": id_p, "consecutivo": f"PG-{id_p:06d}", "fecha": ahora - timedelta(days=dias_atras),
            "estado": "VALIDO", "tipo": "MENSUALIDAD", "id_usuario": u["id_usuario"], "id_contrato": c["id_contrato"],
            "concepto": f"Mensualidad celda {celda['codigo']} (+30 días)", "dias_extendidos": 30,
            "valor": t["MENSUALIDAD_" + celda["tipo"]], "metodo": metodo, "referencia": ref, "id_operador": operadores[0]})
    # un pago anulado para mostrar la trazabilidad
    ultimo = col("pagos").find_one({"tipo": "OCASIONAL"})
    if ultimo:
        id_p = siguiente_id("pagos")
        col("pagos").insert_one({
            "id_pago": id_p, "consecutivo": f"PG-{id_p:06d}", "fecha": ahora - timedelta(hours=30), "estado": "ANULADO",
            "tipo": "MENSUALIDAD", "id_usuario": ultimo["id_usuario"], "id_contrato": 0,
            "concepto": "Mensualidad (registrada por error)", "dias_extendidos": 30, "valor": 180000,
            "metodo": "EFECTIVO", "referencia": "", "id_operador": operadores[0],
            "motivo_anulacion": "Cliente equivocado, se registró de nuevo", "fecha_anulacion": ahora - timedelta(hours=29),
            "id_anulador": 1})


def cargar():
    """Devuelve True si cargó datos y False si ya estaban cargados."""
    inicializar()
    if col("vehiculos").find_one({"placa": "XYZ789"}):
        if col("pagos").count_documents({}) == 0:   # demo de iteración 2 ya cargada: agrega solo los pagos
            _cargar_pagos()
            return True
        return False
    ahora = datetime.now()

    def hace(dias, hora, minuto=0):
        d = ahora - timedelta(days=dias)
        return d.replace(hour=hora, minute=minuto, second=0, microsecond=0)

    # --- usuarios y vehículos ---
    _usuario("CC", "1035440210", "Andrés", "López", "3005559988", "andres.lopez@autoscolombia.co", "OPERADOR")
    ana = col("usuarios").find_one({"documento": "1001"})["id_usuario"]
    laura = _usuario("CC", "1003", "Laura", "Martínez", "3012223344", "laura.martinez@correo.co")
    carlos = _usuario("CC", "1002", "Carlos", "Ramírez", "3023334455", "carlos.ramirez@correo.co")
    pedro = _usuario("CC", "1004", "Pedro", "Sánchez", "3034445566", "pedro.sanchez@correo.co")
    maria = _usuario("CE", "1005", "María", "Torres", "3045556677", "maria.torres@correo.co")
    jorge = _usuario("CC", "1006", "Jorge", "Díaz", "3056667788", "jorge.diaz@correo.co", estado="INACTIVO")

    v_ana = _vehiculo("ABC123", "Mazda", "Rojo", "Carro", ana)
    v_laura = _vehiculo("XYZ789", "Renault Logan", "Gris", "Carro", laura)
    v_carlos = _vehiculo("KLM45A", "Yamaha", "Negro", "Moto", carlos)
    v_carlos2 = _vehiculo("UIO98B", "Honda", "Rojo", "Moto", carlos)
    v_pedro = _vehiculo("QWE321", "Kia Picanto", "Azul", "Carro", pedro)
    v_maria = _vehiculo("RTY654", "Toyota Corolla", "Plata", "Carro", maria)
    v_jorge = _vehiculo("PQR111", "Chevrolet Spark", "Blanco", "Carro", jorge)

    # --- celdas adicionales (las del plan de pruebas) ---
    for codigo in ("CAR-10", "CAR-15"):
        _celda(codigo, "Nivel 1", "Carro")

    # --- historial de movimientos cerrados de los últimos días ---
    c = _id_celda
    _movimiento(v_ana, c("C-01"), hace(6, 7, 40), hace(6, 17, 55))
    _movimiento(v_pedro, c("C-02"), hace(6, 8, 10), hace(6, 18, 20))
    _movimiento(v_carlos, c("M-01"), hace(5, 6, 55), hace(5, 19, 5), "Casco en la celda")
    _movimiento(v_maria, c("C-03"), hace(5, 8, 30), hace(5, 17, 45))
    _movimiento(v_ana, c("C-01"), hace(4, 7, 35), hace(4, 17, 50))
    _movimiento(v_jorge, c("C-04"), hace(4, 9, 0), hace(4, 15, 30), "Usuario hoy inactivo: historial conservado")
    _movimiento(v_carlos2, c("M-02"), hace(3, 7, 15), hace(3, 18, 40))
    _movimiento(v_pedro, c("C-02"), hace(3, 8, 5), hace(3, 18, 0))
    _movimiento(v_maria, c("C-03"), hace(2, 8, 20), hace(2, 17, 30))
    _movimiento(v_laura, c("CAR-10"), hace(2, 7, 50), hace(2, 18, 10), "Celda de mensualidad")
    _movimiento(v_ana, c("C-01"), hace(1, 7, 45), hace(1, 17, 55))
    _movimiento(v_carlos, c("M-01"), hace(1, 7, 0), hace(1, 18, 30))

    # --- mensualidades (celdas reservadas) ---
    def contrato(id_usuario, codigo, dias_atras, vigencia):
        inicio = ahora - timedelta(days=dias_atras)
        col("contratos").insert_one({
            "id_contrato": siguiente_id("contratos"), "id_usuario": id_usuario, "id_celda": c(codigo),
            "fecha_inicio": inicio, "fecha_fin": inicio + timedelta(days=vigencia), "estado": "ACTIVO"})
        col("celdas").update_one({"codigo": codigo}, {"$set": {"estado": "RESERVADA"}})
    contrato(laura, "CAR-10", 10, 30)
    contrato(maria, "C-05", 5, 20)

    # --- mantenimiento ---
    for codigo in ("C-06", "M-05"):
        col("celdas").update_one({"codigo": codigo}, {"$set": {"estado": "MANTENIMIENTO"}})

    # --- vehículos que están dentro hoy ---
    _movimiento(v_pedro, c("C-01"), hace(0, 7, 30), None, "Entrada de la mañana")
    col("celdas").update_one({"codigo": "C-01"}, {"$set": {"estado": "OCUPADA"}})
    _movimiento(v_carlos, c("M-01"), hace(0, 8, 10))
    col("celdas").update_one({"codigo": "M-01"}, {"$set": {"estado": "OCUPADA"}})
    _movimiento(v_laura, c("CAR-10"), hace(0, 7, 55), None, "Usa su celda de mensualidad")  # sigue RESERVADA
    _cargar_pagos()
    return True


if __name__ == "__main__":
    if "--limpiar" in sys.argv:
        if input("Esto BORRA toda la base de datos. Escriba SI para continuar: ").strip() != "SI":
            sys.exit("Cancelado.")
        db = obtener_db()
        for nombre in db.list_collection_names():
            db.drop_collection(nombre)
    if cargar():
        print("Datos de ejemplo cargados (incluye pagos). Contraseña de los usuarios de ejemplo:", CLAVE_DEMO)
    else:
        print("Los datos de ejemplo ya estaban cargados (use --limpiar para recargarlos desde cero).")
