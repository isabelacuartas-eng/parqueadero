"""Paquete datos: conexión a MongoDB, índices y datos iniciales."""
import os
from datetime import datetime

from werkzeug.security import generate_password_hash

try:
    from pymongo import MongoClient
    from pymongo.errors import DuplicateKeyError
    from pymongo.collection import ReturnDocument
except ImportError:  # permite importar el proyecto sin pymongo (p. ej. en pruebas)
    MongoClient = None
    ReturnDocument = type("ReturnDocument", (), {"AFTER": True, "BEFORE": False})

    class DuplicateKeyError(Exception):
        """Clave duplicada (equivalente a pymongo.errors.DuplicateKeyError)."""

# Tarifas iniciales (pesos colombianos). El administrador las puede modificar desde la pantalla Tarifas.
TARIFAS_DEFECTO = {"MENSUALIDAD_Carro": 180000, "MENSUALIDAD_Moto": 90000,
                   "HORA_Carro": 4000, "HORA_Moto": 2000, "TOLERANCIA_MIN": 10}

_db = None


def obtener_db():
    """Devuelve la base de datos (se conecta la primera vez que se usa)."""
    global _db
    if _db is None:
        if MongoClient is None:
            raise RuntimeError("Falta pymongo. Ejecute: pip install -r requirements.txt")
        uri = os.environ.get("MONGO_URI", "mongodb://localhost:27017")
        nombre = os.environ.get("MONGO_DB", "autos_colombia")
        _db = MongoClient(uri, serverSelectionTimeoutMS=5000)[nombre]
    return _db


def usar_db(db):
    """Permite inyectar otra base de datos (usado por las pruebas)."""
    global _db
    _db = db


def col(nombre):
    return obtener_db()[nombre]


def siguiente_id(nombre):
    """Identificador numérico autoincremental por colección."""
    r = col("contadores").find_one_and_update(
        {"_id": nombre}, {"$inc": {"seq": 1}}, upsert=True, return_document=ReturnDocument.AFTER)
    return r["seq"]


def inicializar():
    """Crea los índices (integridad y concurrencia) y los datos de demostración."""
    col("usuarios").create_index("documento", unique=True)
    col("usuarios").create_index("correo", unique=True)
    col("vehiculos").create_index("placa", unique=True)
    col("celdas").create_index("codigo", unique=True)
    # una celda solo puede tener un contrato activo y un cliente un solo contrato activo
    col("contratos").create_index("id_celda", unique=True, partialFilterExpression={"estado": "ACTIVO"})
    col("contratos").create_index("id_usuario", unique=True, partialFilterExpression={"estado": "ACTIVO"})
    # una celda y un vehículo solo pueden tener un movimiento abierto a la vez
    col("movimientos").create_index("id_celda", unique=True, partialFilterExpression={"abierto": True})
    col("movimientos").create_index("id_vehiculo", unique=True, partialFilterExpression={"abierto": True})

    # tarifas: un concepto no se repite; un movimiento solo puede tener un cobro válido (RNF-06)
    col("tarifas").create_index("concepto", unique=True)
    col("pagos").create_index("id_movimiento", unique=True,
                              partialFilterExpression={"tipo": "OCASIONAL", "estado": "VALIDO"})
    col("pagos").create_index("fecha")
    for concepto, valor in TARIFAS_DEFECTO.items():
        if not col("tarifas").find_one({"concepto": concepto}):
            col("tarifas").insert_one({"concepto": concepto, "valor": valor, "actualizado": datetime.now()})

    if col("usuarios").count_documents({}) == 0:
        def usuario(tipo_doc, doc, nom, ape, tel, correo, rol, clave):
            col("usuarios").insert_one({
                "id_usuario": siguiente_id("usuarios"), "tipo_documento": tipo_doc, "documento": doc,
                "nombres": nom, "apellidos": ape, "telefono": tel, "correo": correo, "rol": rol,
                "password_hash": generate_password_hash(clave), "estado": "ACTIVO",
                "creado": datetime.now()})
        usuario("CC", "1000000001", "Administrador", "Autos Colombia", "3000000001",
                "admin@autoscolombia.co", "ADMINISTRADOR", "Admin123*")
        usuario("CC", "1000000002", "Operador", "Autos Colombia", "3000000002",
                "operador@autoscolombia.co", "OPERADOR", "Operador123*")
        usuario("CC", "1001", "Ana", "Gómez", "3001112233", "ana.gomez@correo.co", "CLIENTE", "Cliente123*")
        col("vehiculos").insert_one({"id_vehiculo": siguiente_id("vehiculos"), "placa": "ABC123",
                                     "marca": "Mazda", "color": "Rojo", "tipo": "Carro", "id_usuario": 3})
    if col("celdas").count_documents({}) == 0:
        def celda(codigo, zona, tipo):
            col("celdas").insert_one({"id_celda": siguiente_id("celdas"), "codigo": codigo, "zona": zona,
                                      "tipo": tipo, "estado": "DISPONIBLE"})
        for i in range(1, 7):
            celda(f"C-{i:02d}", "Nivel 1", "Carro")
        for i in range(7, 11):
            celda(f"C-{i:02d}", "Nivel 2", "Carro")
        for i in range(1, 6):
            celda(f"M-{i:02d}", "Zona motos", "Moto")
