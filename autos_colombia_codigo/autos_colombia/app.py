"""Autos Colombia - Iteraciones 1 y 2: vehículos, usuarios y celdas (Flask + MongoDB)."""
import os
from datetime import timedelta

from flask import Flask

from controladores.rutas import bp
from datos.db import inicializar


def crear_app():
    app = Flask(__name__)
    app.secret_key = os.environ.get("SECRET_KEY", "autos-colombia-dev")
    app.permanent_session_lifetime = timedelta(hours=8)
    app.register_blueprint(bp)

    @app.template_filter("fecha")
    def fecha(valor):
        return valor.strftime("%Y-%m-%d %H:%M") if valor else "—"

    return app


app = crear_app()

if __name__ == "__main__":
    inicializar()
    app.run(debug=True)
