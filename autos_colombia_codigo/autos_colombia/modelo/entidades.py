"""Paquete modelo: clases de dominio."""
from dataclasses import dataclass
from typing import Optional


@dataclass
class TipoVehiculo:
    id_tipo: int
    nombre: str


@dataclass
class Usuario:
    id_usuario: int
    documento: str
    nombre: str
    telefono: str
    estado: str = "ACTIVO"

    def esta_activo(self) -> bool:
        return self.estado == "ACTIVO"


@dataclass
class Vehiculo:
    id_vehiculo: int
    placa: str
    marca: str
    color: str
    id_tipo: int
    id_usuario: int


@dataclass
class Celda:
    id_celda: int
    codigo: str
    id_tipo: int
    estado: str = "DISPONIBLE"

    def esta_disponible(self) -> bool:
        return self.estado == "DISPONIBLE"

    def ocupar(self):
        self.estado = "OCUPADA"

    def liberar(self):
        self.estado = "DISPONIBLE"


@dataclass
class Movimiento:
    id_movimiento: int
    id_vehiculo: int
    id_celda: int
    fecha_entrada: str
    fecha_salida: Optional[str] = None
    observacion: str = ""

    def esta_abierto(self) -> bool:
        return self.fecha_salida is None
