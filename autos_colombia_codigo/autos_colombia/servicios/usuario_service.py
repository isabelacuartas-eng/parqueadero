"""Gestión de usuarios (RF-01, RF-02, RF-03)."""
import re
from datetime import datetime

from werkzeug.security import generate_password_hash

from datos.db import DuplicateKeyError, col, siguiente_id
from modelo.entidades import ROLES, TIPOS_DOCUMENTO, Usuario
from servicios.errores import ReglaNegocioError

CORREO = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class UsuarioService:
    def _validar_contacto(self, telefono, correo, rol):
        if not CORREO.match(correo):
            raise ReglaNegocioError("El correo electrónico no es válido.")
        if telefono and not re.fullmatch(r"[0-9+\- ]{7,15}", telefono):
            raise ReglaNegocioError("El teléfono no es válido.")
        if rol not in ROLES:
            raise ReglaNegocioError("Rol no válido.")

    def registrar(self, d: dict) -> int:
        """RF-01: registra un usuario. Documento y correo no se pueden repetir."""
        d = {k: (v or "").strip() for k, v in d.items()}
        for campo, etiqueta in (("tipo_documento", "tipo de documento"), ("documento", "número de documento"),
                                ("nombres", "nombres"), ("apellidos", "apellidos"), ("correo", "correo"),
                                ("rol", "rol"), ("password", "contraseña")):
            if not d.get(campo):
                raise ReglaNegocioError(f"El campo {etiqueta} es obligatorio.")
        if d["tipo_documento"] not in TIPOS_DOCUMENTO:
            raise ReglaNegocioError("Tipo de documento no válido.")
        d["correo"] = d["correo"].lower()
        self._validar_contacto(d.get("telefono", ""), d["correo"], d["rol"])
        if len(d["password"]) < 8:
            raise ReglaNegocioError("La contraseña debe tener al menos 8 caracteres.")
        if col("usuarios").find_one({"documento": d["documento"]}):
            raise ReglaNegocioError("El número de documento ya se encuentra registrado")
        if col("usuarios").find_one({"correo": d["correo"]}):
            raise ReglaNegocioError("El correo electrónico ya se encuentra registrado")
        id_usuario = siguiente_id("usuarios")
        try:
            col("usuarios").insert_one({
                "id_usuario": id_usuario, "tipo_documento": d["tipo_documento"], "documento": d["documento"],
                "nombres": d["nombres"], "apellidos": d["apellidos"], "telefono": d.get("telefono", ""),
                "correo": d["correo"], "rol": d["rol"],
                "password_hash": generate_password_hash(d["password"]),  # RNF-01: nunca en texto plano
                "estado": "ACTIVO", "creado": datetime.now()})
        except DuplicateKeyError:  # carrera entre dos registros simultáneos
            raise ReglaNegocioError("El número de documento o el correo ya se encuentran registrados")
        return id_usuario

    def buscar(self, criterio: str = "", rol: str = ""):
        """RF-02: busca por documento, nombre o rol."""
        filtro = {}
        criterio = (criterio or "").strip()
        if criterio:
            rx = {"$regex": re.escape(criterio), "$options": "i"}
            filtro["$or"] = [{"documento": rx}, {"nombres": rx}, {"apellidos": rx}, {"correo": rx}]
        if rol:
            filtro["rol"] = rol
        return [Usuario.desde_doc(x) for x in col("usuarios").find(filtro).sort("id_usuario", 1)]

    def obtener(self, id_usuario: int) -> Usuario:
        u = Usuario.desde_doc(col("usuarios").find_one({"id_usuario": id_usuario}))
        if not u:
            raise ReglaNegocioError("Usuario no encontrado.")
        return u

    def actualizar(self, id_usuario: int, telefono: str, correo: str, rol: str, id_actor: int):
        """RF-02: actualiza datos de contacto y rol."""
        u = self.obtener(id_usuario)
        correo = (correo or "").strip().lower()
        telefono = (telefono or "").strip()
        self._validar_contacto(telefono, correo, rol)
        if id_usuario == id_actor and rol != u.rol:
            raise ReglaNegocioError("No puede cambiar su propio rol.")
        otro = col("usuarios").find_one({"correo": correo, "id_usuario": {"$ne": id_usuario}})
        if otro:
            raise ReglaNegocioError("El correo electrónico ya se encuentra registrado")
        try:
            col("usuarios").update_one({"id_usuario": id_usuario},
                                       {"$set": {"telefono": telefono, "correo": correo, "rol": rol}})
        except DuplicateKeyError:
            raise ReglaNegocioError("El correo electrónico ya se encuentra registrado")

    def cambiar_estado(self, id_usuario: int, estado: str, id_actor: int):
        """RF-03: inactivación lógica (no se elimina el registro)."""
        if estado not in ("ACTIVO", "INACTIVO"):
            raise ReglaNegocioError("Estado no válido.")
        if id_usuario == id_actor and estado == "INACTIVO":
            raise ReglaNegocioError("No puede inactivar su propio usuario.")
        self.obtener(id_usuario)
        col("usuarios").update_one({"id_usuario": id_usuario}, {"$set": {"estado": estado}})
