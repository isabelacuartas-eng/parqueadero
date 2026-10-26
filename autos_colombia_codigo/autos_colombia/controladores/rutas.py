"""Paquete controladores: rutas HTTP (Flask Blueprint)."""
from flask import Blueprint, flash, redirect, render_template, request, url_for

from servicios.movimiento_service import MovimientoService, ReglaNegocioError
from servicios.registro_service import RegistroService

bp = Blueprint("rutas", __name__)
mov_srv = MovimientoService()
reg_srv = RegistroService()


@bp.route("/")
def index():
    dentro, libres = mov_srv.listar_vehiculos_dentro()
    return render_template("index.html", dentro=dentro, libres=libres)


@bp.route("/entrada", methods=["GET", "POST"])
def entrada():
    if request.method == "POST":
        try:
            celda = mov_srv.registrar_entrada(request.form["placa"], request.form.get("observacion", ""))
            flash(f"Entrada registrada. Celda asignada: {celda}", "ok")
            return redirect(url_for("rutas.index"))
        except ReglaNegocioError as e:
            flash(str(e), "error")
    return render_template("entrada.html")


@bp.route("/salida/<int:id_mov>", methods=["POST"])
def salida(id_mov):
    try:
        mov_srv.registrar_salida(id_mov)
        flash("Salida registrada. Celda liberada.", "ok")
    except ReglaNegocioError as e:
        flash(str(e), "error")
    return redirect(url_for("rutas.index"))


@bp.route("/historial")
def historial():
    return render_template("historial.html", filas=mov_srv.listar_historial())


@bp.route("/registro", methods=["GET", "POST"])
def registro():
    if request.method == "POST":
        try:
            if request.form["accion"] == "usuario":
                reg_srv.registrar_usuario(request.form["documento"], request.form["nombre"],
                                          request.form.get("telefono", ""))
                flash("Usuario registrado.", "ok")
            else:
                reg_srv.registrar_vehiculo(request.form["placa"], request.form.get("marca", ""),
                                           request.form.get("color", ""), request.form["id_tipo"],
                                           request.form["documento"])
                flash("Vehículo registrado.", "ok")
        except ReglaNegocioError as e:
            flash(str(e), "error")
        return redirect(url_for("rutas.registro"))
    return render_template("registro.html")
