"""Paquete modelo: clases de dominio."""
from dataclasses import dataclass, fields
from datetime import datetime
from typing import Optional

TIPOS_VEHICULO = ("Carro", "Moto")
TIPOS_DOCUMENTO = ("CC", "CE", "NIT", "PASAPORTE", "TI")
ROLES = ("ADMINISTRADOR", "OPERADOR", "CLIENTE")
ESTADOS_CELDA = ("DISPONIBLE", "OCUPADA", "MANTENIMIENTO", "RESERVADA")


class _Documento:
    @classmethod
    def desde_doc(cls, doc):
        if doc is None:
            return None
        nombres = {f.name for f in fields(cls)}
        return cls(**{k: v for k, v in doc.items() if k in nombres})


@dataclass
class Usuario(_Documento):
    id_usuario: int
    tipo_documento: str
    documento: str
    nombres: str
    apellidos: str
    telefono: str
    correo: str
    rol: str
    password_hash: str
    estado: str = "ACTIVO"

    def esta_activo(self) -> bool:
        return self.estado == "ACTIVO"

    def nombre_completo(self) -> str:
        return f"{self.nombres} {self.apellidos}".strip()

    def puede_iniciar_sesion(self) -> bool:
        return self.rol in ("ADMINISTRADOR", "OPERADOR")


@dataclass
class Vehiculo(_Documento):
    id_vehiculo: int
    placa: str
    marca: str
    color: str
    tipo: str
    id_usuario: int


@dataclass
class Celda(_Documento):
    id_celda: int
    codigo: str
    zona: str
    tipo: str
    estado: str = "DISPONIBLE"

    def esta_disponible(self) -> bool:
        return self.estado == "DISPONIBLE"


@dataclass
class Contrato(_Documento):
    id_contrato: int
    id_usuario: int
    id_celda: int
    fecha_inicio: datetime
    fecha_fin: datetime
    estado: str = "ACTIVO"

    def esta_vigente(self, ahora: Optional[datetime] = None) -> bool:
        return self.estado == "ACTIVO" and self.fecha_fin >= (ahora or datetime.now())


@dataclass
class Movimiento(_Documento):
    id_movimiento: int
    id_vehiculo: int
    id_celda: int
    fecha_entrada: datetime
    fecha_salida: Optional[datetime] = None
    observacion: str = ""
    abierto: bool = True
    id_operador: Optional[int] = None
