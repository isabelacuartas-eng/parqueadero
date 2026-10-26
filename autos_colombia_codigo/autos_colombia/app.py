"""Autos Colombia - Iteración 1: Gestión de entrada y salida de vehículos."""
from flask import Flask

from controladores.rutas import bp
from datos.db import inicializar

app = Flask(__name__)
app.secret_key = "autos-colombia-dev"
app.register_blueprint(bp)

if __name__ == "__main__":
    inicializar()
    app.run(debug=True)
