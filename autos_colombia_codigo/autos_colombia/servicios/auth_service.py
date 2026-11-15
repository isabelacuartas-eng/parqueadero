"""Autenticación de usuarios (RF-04, RNF-01)."""
from werkzeug.security import check_password_hash

from datos.db import col
from modelo.entidades import Usuario
from servicios.errores import ReglaNegocioError


class AuthService:
    def autenticar(self, identificador: str, clave: str) -> Usuario:
        """Valida credenciales. El usuario se identifica con su correo o su documento."""
        identificador = (identificador or "").strip()
        doc = col("usuarios").find_one({"$or": [{"correo": identificador.lower()},
                                                {"documento": identificador}]})
        usuario = Usuario.desde_doc(doc)
        # mismo mensaje para usuario inexistente y clave incorrecta
        if not usuario or not check_password_hash(usuario.password_hash, clave or ""):
            raise ReglaNegocioError("Credenciales inválidas.")
        if not usuario.esta_activo():
            raise ReglaNegocioError("El usuario está inactivo. Contacte al administrador.")
        if not usuario.puede_iniciar_sesion():
            raise ReglaNegocioError("Este usuario no tiene acceso a la plataforma.")
        return usuario
