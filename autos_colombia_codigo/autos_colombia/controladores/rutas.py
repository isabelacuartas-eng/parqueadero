"""Paquete controladores: rutas HTTP (Flask Blueprint) y control de acceso por rol."""
from functools import wraps

from datetime import date, datetime

from flask import Blueprint, flash, g, redirect, render_template, request, session, url_for

from modelo.entidades import ROLES, TIPOS_DOCUMENTO, TIPOS_VEHICULO
from servicios.auth_service import AuthService
from servicios.celda_service import CeldaService
from servicios.contrato_service import ContratoService
from servicios.errores import ReglaNegocioError
from servicios.movimiento_service import MovimientoService
from servicios.pago_service import METODOS, PagoService
from servicios.tarifa_service import TarifaService
from servicios.usuario_service import UsuarioService

bp = Blueprint("rutas", __name__)
auth_srv, usr_srv, celda_srv = AuthService(), UsuarioService(), CeldaService()
mov_srv, ctr_srv = MovimientoService(), ContratoService()
pago_srv, tarifa_srv = PagoService(), TarifaService()

RUTAS_PUBLICAS = {"rutas.login", "static"}


@bp.before_app_request
def exigir_sesion():
    """RF-04: todas las pantallas, salvo el login, exigen sesión iniciada."""
    g.usuario = session.get("usuario")
    if request.endpoint not in RUTAS_PUBLICAS and g.usuario is None:
        return redirect(url_for("rutas.login"))


def rol_requerido(*roles):
    """Restringe una ruta a ciertos roles."""
    def deco(f):
        @wraps(f)
        def interior(*a, **k):
            if g.usuario["rol"] not in roles:
                flash("No tiene permisos para acceder a esta opción.", "error")
                return redirect(url_for("rutas.index"))
            return f(*a, **k)
        return interior
    return deco


ADMIN = "ADMINISTRADOR"
STAFF = ("ADMINISTRADOR", "OPERADOR")


# ---------- Autenticación ----------
@bp.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        try:
            u = auth_srv.autenticar(request.form.get("identificador"), request.form.get("clave"))
            session.clear()
            session["usuario"] = {"id": u.id_usuario, "nombre": u.nombre_completo(), "rol": u.rol}
            return redirect(url_for("rutas.index"))
        except ReglaNegocioError as e:
            flash(str(e), "error")
    return render_template("login.html")


@bp.route("/logout", methods=["POST"])
def logout():
    session.clear()
    return redirect(url_for("rutas.login"))


# ---------- Vehículos (iteración 1) ----------
@bp.route("/")
def index():
    dentro, libres = mov_srv.listar_vehiculos_dentro()
    return render_template("index.html", dentro=dentro, libres=libres)


@bp.route("/entrada", methods=["GET", "POST"])
def entrada():
    if request.method == "POST":
        try:
            celda = mov_srv.registrar_entrada(request.form.get("placa"), request.form.get("observacion", ""),
                                              g.usuario["id"])
            flash(f"Entrada registrada. Celda asignada: {celda}", "ok")
            return redirect(url_for("rutas.index"))
        except ReglaNegocioError as e:
            flash(str(e), "error")
    return render_template("entrada.html")


@bp.route("/salida/<int:id_mov>", methods=["GET", "POST"])
def salida(id_mov):
    """Salida de un vehículo: muestra el cobro (RF-11) y, al confirmar, cierra el movimiento."""
    if request.method == "POST":
        try:
            pago = pago_srv.registrar_salida_con_cobro(id_mov, request.form.get("metodo"),
                                                       request.form.get("referencia"), g.usuario["id"])
            if pago:
                flash(f"Salida registrada y pago {pago['consecutivo']} generado.", "ok")
                return redirect(url_for("rutas.comprobante", id_pago=pago["id_pago"]))
            flash("Salida registrada. No generó cobro.", "ok")
            return redirect(url_for("rutas.index"))
        except ReglaNegocioError as e:
            flash(str(e), "error")
    try:
        return render_template("salida.html", v=pago_srv.vista_previa_salida(id_mov), metodos=METODOS)
    except ReglaNegocioError as e:
        flash(str(e), "error")
        return redirect(url_for("rutas.index"))


@bp.route("/historial")
def historial():
    return render_template("historial.html", filas=mov_srv.listar_historial())


@bp.route("/vehiculos", methods=["GET", "POST"])
def vehiculos():
    if request.method == "POST":
        try:
            mov_srv.registrar_vehiculo(request.form.get("placa"), request.form.get("marca"),
                                       request.form.get("color"), request.form.get("tipo"),
                                       request.form.get("documento"))
            flash("Vehículo registrado.", "ok")
        except ReglaNegocioError as e:
            flash(str(e), "error")
        return redirect(url_for("rutas.vehiculos"))
    return render_template("vehiculos.html", tipos=TIPOS_VEHICULO)


# ---------- Usuarios (solo administrador) ----------
@bp.route("/usuarios")
@rol_requerido(ADMIN)
def usuarios():
    criterio, rol = request.args.get("q", ""), request.args.get("rol", "")
    return render_template("usuarios.html", filas=usr_srv.buscar(criterio, rol), q=criterio, rol=rol, roles=ROLES)


@bp.route("/usuarios/nuevo", methods=["GET", "POST"])
@rol_requerido(ADMIN)
def usuario_nuevo():
    datos = {}
    if request.method == "POST":
        datos = request.form.to_dict()
        try:
            id_u = usr_srv.registrar(datos)
            flash(f"Usuario registrado correctamente. ID asignado: {id_u}", "ok")
            return redirect(url_for("rutas.usuarios"))
        except ReglaNegocioError as e:
            flash(str(e), "error")
    return render_template("usuario_form.html", u=None, datos=datos, roles=ROLES, tipos=TIPOS_DOCUMENTO)


@bp.route("/usuarios/<int:id_u>/editar", methods=["GET", "POST"])
@rol_requerido(ADMIN)
def usuario_editar(id_u):
    try:
        u = usr_srv.obtener(id_u)
    except ReglaNegocioError as e:
        flash(str(e), "error")
        return redirect(url_for("rutas.usuarios"))
    if request.method == "POST":
        try:
            usr_srv.actualizar(id_u, request.form.get("telefono"), request.form.get("correo"),
                               request.form.get("rol"), g.usuario["id"])
            flash("Usuario actualizado.", "ok")
            return redirect(url_for("rutas.usuarios"))
        except ReglaNegocioError as e:
            flash(str(e), "error")
    return render_template("usuario_form.html", u=u, datos={}, roles=ROLES, tipos=TIPOS_DOCUMENTO)


@bp.route("/usuarios/<int:id_u>/estado", methods=["POST"])
@rol_requerido(ADMIN)
def usuario_estado(id_u):
    try:
        usr_srv.cambiar_estado(id_u, request.form.get("estado"), g.usuario["id"])
        flash("Estado del usuario actualizado.", "ok")
    except ReglaNegocioError as e:
        flash(str(e), "error")
    return redirect(url_for("rutas.usuarios"))


# ---------- Celdas ----------
@bp.route("/celdas")
def celdas():
    ctr_srv.vencer_vencidos()
    tipo, zona = request.args.get("tipo", ""), request.args.get("zona", "")
    lista = celda_srv.listar(tipo, zona)
    por_zona = {}
    for c in lista:
        por_zona.setdefault(c.zona, []).append(c)
    return render_template("celdas.html", por_zona=por_zona, resumen=celda_srv.resumen(lista),
                           zonas=celda_srv.zonas(), tipos=TIPOS_VEHICULO, tipo=tipo, zona=zona,
                           en_uso=celda_srv.en_uso())


@bp.route("/celdas/nueva", methods=["GET", "POST"])
@rol_requerido(ADMIN)
def celda_nueva():
    if request.method == "POST":
        try:
            celda_srv.crear(request.form.get("codigo"), request.form.get("zona"), request.form.get("tipo"))
            flash("Celda creada con estado Disponible.", "ok")
            return redirect(url_for("rutas.celdas"))
        except ReglaNegocioError as e:
            flash(str(e), "error")
    return render_template("celda_form.html", tipos=TIPOS_VEHICULO, zonas=celda_srv.zonas())


@bp.route("/celdas/<int:id_c>/estado", methods=["POST"])
@rol_requerido(*STAFF)
def celda_estado(id_c):
    try:
        celda_srv.cambiar_estado(id_c, request.form.get("estado"))
        flash("Estado de la celda actualizado.", "ok")
    except ReglaNegocioError as e:
        flash(str(e), "error")
    return redirect(url_for("rutas.celdas", **{k: v for k, v in request.args.items()}))


# ---------- Mensualidades ----------
@bp.route("/mensualidades", methods=["GET", "POST"])
@rol_requerido(*STAFF)
def mensualidades():
    if request.method == "POST":
        try:
            ctr_srv.asignar(request.form.get("documento"), int(request.form.get("id_celda") or 0),
                            request.form.get("dias"))
            flash("Contrato de mensualidad registrado. La celda quedó reservada.", "ok")
        except ReglaNegocioError as e:
            flash(str(e), "error")
        return redirect(url_for("rutas.mensualidades"))
    ctr_srv.vencer_vencidos()
    libres = [c for c in celda_srv.listar() if c.estado == "DISPONIBLE"]
    return render_template("mensualidades.html", contratos=ctr_srv.listar_activos(), libres=libres,
                           ahora=datetime.now())


@bp.route("/mensualidades/<int:id_ct>/finalizar", methods=["POST"])
@rol_requerido(*STAFF)
def mensualidad_finalizar(id_ct):
    try:
        ctr_srv.finalizar(id_ct)
        flash("Contrato finalizado. La celda fue liberada.", "ok")
    except ReglaNegocioError as e:
        flash(str(e), "error")
    return redirect(url_for("rutas.mensualidades"))


# ---------- Pagos (iteración 3) ----------
def _fecha(txt):
    try:
        return datetime.strptime(txt, "%Y-%m-%d").date() if txt else None
    except ValueError:
        return None


@bp.route("/pagos")
@rol_requerido(*STAFF)
def pagos():
    f = {k: request.args.get(k, "") for k in ("desde", "hasta", "tipo", "metodo", "documento", "estado")}
    # el operador solo ve los pagos que él registró; el administrador ve todos
    solo_mios = g.usuario["id"] if g.usuario["rol"] == "OPERADOR" else None
    filas, total = pago_srv.listar(desde=_fecha(f["desde"]), hasta=_fecha(f["hasta"]), tipo=f["tipo"],
                                   metodo=f["metodo"], documento=f["documento"], estado=f["estado"],
                                   id_operador=solo_mios)
    return render_template("pagos.html", filas=filas, total=total, f=f, metodos=METODOS)


@bp.route("/pagos/mensualidad", methods=["GET", "POST"])
@rol_requerido(*STAFF)
def pago_mensualidad():
    if request.method == "POST":
        try:
            pago = pago_srv.registrar_pago_mensualidad(request.form.get("documento"), request.form.get("metodo"),
                                                       request.form.get("referencia"), g.usuario["id"])
            flash(f"Pago {pago['consecutivo']} registrado. Mensualidad renovada por 30 días.", "ok")
            return redirect(url_for("rutas.comprobante", id_pago=pago["id_pago"]))
        except ReglaNegocioError as e:
            flash(str(e), "error")
    return render_template("pago_form.html", documento=request.values.get("documento", ""), metodos=METODOS,
                           tarifas=tarifa_srv.obtener_todas())


@bp.route("/pagos/<int:id_pago>/comprobante")
@rol_requerido(*STAFF)
def comprobante(id_pago):
    try:
        p = pago_srv.obtener(id_pago)
    except ReglaNegocioError as e:
        flash(str(e), "error")
        return redirect(url_for("rutas.pagos"))
    if g.usuario["rol"] == "OPERADOR" and p.get("id_operador") != g.usuario["id"]:
        flash("No tiene permisos para ver este comprobante.", "error")
        return redirect(url_for("rutas.pagos"))
    return render_template("comprobante.html", p=p)


@bp.route("/pagos/<int:id_pago>/anular", methods=["POST"])
@rol_requerido(ADMIN)
def pago_anular(id_pago):
    try:
        pago_srv.anular(id_pago, request.form.get("motivo"), g.usuario["id"])
        flash("Pago anulado. El registro se conserva para auditoría.", "ok")
    except ReglaNegocioError as e:
        flash(str(e), "error")
    return redirect(url_for("rutas.pagos"))


@bp.route("/pagos/reporte")
@rol_requerido(ADMIN)
def pagos_reporte():
    hoy = date.today()
    desde, hasta = _fecha(request.args.get("desde")) or hoy, _fecha(request.args.get("hasta")) or hoy
    return render_template("reporte_pagos.html", r=pago_srv.reporte(desde, hasta), desde=desde, hasta=hasta)


@bp.route("/tarifas", methods=["GET", "POST"])
@rol_requerido(ADMIN)
def tarifas():
    if request.method == "POST":
        try:
            tarifa_srv.actualizar(request.form.to_dict(), g.usuario["id"])
            flash("Tarifas actualizadas. Se aplican a los cobros nuevos.", "ok")
        except ReglaNegocioError as e:
            flash(str(e), "error")
        return redirect(url_for("rutas.tarifas"))
    return render_template("tarifas.html", t=tarifa_srv.obtener_todas())
