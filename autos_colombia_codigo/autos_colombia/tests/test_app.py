"""Pruebas de las iteraciones 1 y 2 (servicios y rutas) sobre un MongoDB simulado."""
import threading
import unittest

from datos import db
from servicios.errores import ReglaNegocioError
from tests.fake_mongo import FakeDB


def nuevo_entorno():
    db.usar_db(FakeDB())
    db.inicializar()


class Base(unittest.TestCase):
    def setUp(self):
        nuevo_entorno()
        from servicios.celda_service import CeldaService
        from servicios.contrato_service import ContratoService
        from servicios.movimiento_service import MovimientoService
        from servicios.usuario_service import UsuarioService
        from servicios.auth_service import AuthService
        self.u, self.c, self.ct, self.m, self.a = (UsuarioService(), CeldaService(), ContratoService(),
                                                   MovimientoService(), AuthService())

    def datos_usuario(self, **kw):
        d = dict(tipo_documento="CC", documento="1035440210", nombres="Andres", apellidos="Lopez",
                 telefono="3001234567", correo="andres@correo.co", rol="OPERADOR", password="Clave123*")
        d.update(kw)
        return d


class TestUsuarios(Base):
    def test_registro_con_hash(self):  # CP-01
        id_u = self.u.registrar(self.datos_usuario())
        guardado = db.col("usuarios").find_one({"id_usuario": id_u})
        self.assertNotEqual(guardado["password_hash"], "Clave123*")
        self.assertNotIn("Clave123*", guardado["password_hash"])

    def test_documento_duplicado(self):  # CP-02
        self.u.registrar(self.datos_usuario())
        with self.assertRaisesRegex(ReglaNegocioError, "documento ya se encuentra registrado"):
            self.u.registrar(self.datos_usuario(correo="otro@correo.co"))

    def test_correo_duplicado_y_validaciones(self):
        self.u.registrar(self.datos_usuario())
        with self.assertRaisesRegex(ReglaNegocioError, "correo"):
            self.u.registrar(self.datos_usuario(documento="999"))
        with self.assertRaises(ReglaNegocioError):
            self.u.registrar(self.datos_usuario(documento="1", correo="malo"))
        with self.assertRaises(ReglaNegocioError):
            self.u.registrar(self.datos_usuario(documento="2", correo="x@y.co", password="corta"))
        with self.assertRaises(ReglaNegocioError):
            self.u.registrar(self.datos_usuario(documento="3", correo="z@y.co", rol="REY"))

    def test_buscar_y_actualizar(self):  # CP-03
        id_u = self.u.registrar(self.datos_usuario())
        self.assertEqual([x.id_usuario for x in self.u.buscar("1035")], [id_u])
        self.assertEqual(len(self.u.buscar("lopez")), 1)
        self.assertTrue(all(x.rol == "OPERADOR" for x in self.u.buscar("", "OPERADOR")))
        self.u.actualizar(id_u, "3005559988", "andres@correo.co", "OPERADOR", id_actor=1)
        self.assertEqual(self.u.obtener(id_u).telefono, "3005559988")

    def test_inactivacion_bloquea_login_y_conserva_registro(self):  # CP-04
        id_u = self.u.registrar(self.datos_usuario())
        self.a.autenticar("andres@correo.co", "Clave123*")
        self.u.cambiar_estado(id_u, "INACTIVO", id_actor=1)
        with self.assertRaisesRegex(ReglaNegocioError, "inactivo"):
            self.a.autenticar("andres@correo.co", "Clave123*")
        self.assertEqual(self.u.obtener(id_u).estado, "INACTIVO")  # sigue existiendo

    def test_no_autoinactivarse(self):
        with self.assertRaises(ReglaNegocioError):
            self.u.cambiar_estado(1, "INACTIVO", id_actor=1)

    def test_login(self):
        self.assertEqual(self.a.autenticar("admin@autoscolombia.co", "Admin123*").rol, "ADMINISTRADOR")
        self.assertEqual(self.a.autenticar("1000000002", "Operador123*").rol, "OPERADOR")
        with self.assertRaisesRegex(ReglaNegocioError, "Credenciales"):
            self.a.autenticar("admin@autoscolombia.co", "mala")
        with self.assertRaisesRegex(ReglaNegocioError, "Credenciales"):
            self.a.autenticar("noexiste@x.co", "Admin123*")
        with self.assertRaisesRegex(ReglaNegocioError, "acceso"):
            self.a.autenticar("ana.gomez@correo.co", "Cliente123*")


class TestCeldas(Base):
    def test_crear_y_codigo_unico(self):  # CP-06
        id_c = self.c.crear("car-15", "Nivel 1", "Carro")
        self.assertEqual(self.c.obtener(id_c).estado, "DISPONIBLE")
        self.assertEqual(self.c.obtener(id_c).codigo, "CAR-15")
        with self.assertRaisesRegex(ReglaNegocioError, "Ya existe"):
            self.c.crear("CAR-15", "Nivel 2", "Carro")

    def test_mantenimiento_impide_entrada(self):  # CP-07
        for ce in self.c.listar("Carro"):
            self.c.cambiar_estado(ce.id_celda, "MANTENIMIENTO")
        with self.assertRaisesRegex(ReglaNegocioError, "No hay celdas disponibles"):
            self.m.registrar_entrada("ABC123")
        self.assertEqual(self.c.resumen(self.c.listar("Carro"))["MANTENIMIENTO"], 10)

    def test_transiciones_invalidas(self):
        self.m.registrar_entrada("ABC123")
        ocupada = [x for x in self.c.listar() if x.estado == "OCUPADA"][0]
        with self.assertRaises(ReglaNegocioError):
            self.c.cambiar_estado(ocupada.id_celda, "MANTENIMIENTO")

    def test_resumen_y_filtros(self):
        self.assertEqual(len(self.c.listar("Moto")), 5)
        self.assertEqual(len(self.c.listar("", "Nivel 2")), 4)
        self.assertEqual(self.c.resumen(self.c.listar())["DISPONIBLE"], 15)


class TestMensualidad(Base):
    def test_asignar_y_uso_exclusivo(self):  # CP-08
        id_c = self.c.crear("CAR-10", "Nivel 1", "Carro")
        self.ct.asignar("1001", id_c, 30)
        self.assertEqual(self.c.obtener(id_c).estado, "RESERVADA")
        self.assertEqual(self.m.registrar_entrada("ABC123"), "CAR-10")  # el titular usa su celda
        # un ocasional nunca recibe la celda reservada
        self.u.registrar(self.datos_usuario(documento="55", correo="oc@x.co", rol="CLIENTE"))
        self.m.registrar_vehiculo("OCA111", "Kia", "Gris", "Carro", "55")
        self.assertNotEqual(self.m.registrar_entrada("OCA111"), "CAR-10")
        # al salir el titular la celda sigue reservada
        self.m.registrar_salida(self.m.listar_vehiculos_dentro()[0][-1]["id_movimiento"])
        self.assertEqual(self.c.obtener(id_c).estado, "RESERVADA")

    def test_reglas(self):
        id_c = self.c.crear("CAR-10", "Nivel 1", "Carro")
        with self.assertRaises(ReglaNegocioError):
            self.ct.asignar("9999", id_c, 30)             # cliente inexistente
        with self.assertRaises(ReglaNegocioError):
            self.ct.asignar("1001", id_c, 0)              # vigencia inválida
        self.ct.asignar("1001", id_c, 30)
        with self.assertRaises(ReglaNegocioError):
            self.ct.asignar("1001", id_c, 30)             # cliente ya con contrato
        otro = self.c.crear("CAR-11", "Nivel 1", "Carro")
        with self.assertRaises(ReglaNegocioError):
            self.ct.asignar("1000000002", otro, 30)       # no es rol cliente
        self.c.cambiar_estado(otro, "MANTENIMIENTO")
        self.u.registrar(self.datos_usuario(documento="77", correo="c77@x.co", rol="CLIENTE"))
        with self.assertRaises(ReglaNegocioError):
            self.ct.asignar("77", otro, 30)               # celda no disponible

    def test_finalizar_libera(self):
        id_c = self.c.crear("CAR-10", "Nivel 1", "Carro")
        self.ct.asignar("1001", id_c, 30)
        self.ct.finalizar(self.ct.listar_activos()[0]["contrato"].id_contrato)
        self.assertEqual(self.c.obtener(id_c).estado, "DISPONIBLE")

    def test_vencimiento(self):
        from datetime import datetime, timedelta
        id_c = self.c.crear("CAR-10", "Nivel 1", "Carro")
        self.ct.asignar("1001", id_c, 1)
        db.col("contratos").update_one({"estado": "ACTIVO"}, {"$set": {"fecha_fin": datetime.now() - timedelta(days=1)}})
        self.ct.vencer_vencidos()
        self.assertEqual(self.c.obtener(id_c).estado, "DISPONIBLE")


class TestMovimientos(Base):
    def test_entrada_salida(self):
        celda = self.m.registrar_entrada("abc123")
        self.assertEqual(celda, "C-01")
        with self.assertRaisesRegex(ReglaNegocioError, "ya se encuentra"):
            self.m.registrar_entrada("ABC123")
        dentro, libres = self.m.listar_vehiculos_dentro()
        self.assertEqual((len(dentro), libres), (1, 14))
        self.m.registrar_salida(dentro[0]["id_movimiento"])
        self.assertEqual(self.m.listar_vehiculos_dentro()[1], 15)
        with self.assertRaises(ReglaNegocioError):
            self.m.registrar_salida(dentro[0]["id_movimiento"])

    def test_propietario_inactivo_y_placa_desconocida(self):
        self.u.cambiar_estado(3, "INACTIVO", id_actor=1)
        with self.assertRaisesRegex(ReglaNegocioError, "inactivo"):
            self.m.registrar_entrada("ABC123")
        with self.assertRaisesRegex(ReglaNegocioError, "no registrada"):
            self.m.registrar_entrada("ZZZ999")

    def test_historial_conserva_usuario_inactivo(self):  # HU-02 criterio 2.2
        self.m.registrar_entrada("ABC123")
        self.m.registrar_salida(self.m.listar_vehiculos_dentro()[0][0]["id_movimiento"])
        self.u.cambiar_estado(3, "INACTIVO", id_actor=1)
        self.assertEqual(self.m.listar_historial()[0]["placa"], "ABC123")

    def test_no_se_asigna_la_misma_celda_dos_veces(self):  # RNF-03
        for i in range(10):
            self.u.registrar(self.datos_usuario(documento=f"9{i}", correo=f"v{i}@x.co", rol="CLIENTE"))
            self.m.registrar_vehiculo(f"VEH{i:03d}", "X", "Y", "Carro", f"9{i}")
        resultados = []
        def entrar(p):
            try: resultados.append(self.m.registrar_entrada(p))
            except ReglaNegocioError as e: resultados.append(str(e))
        hilos = [threading.Thread(target=entrar, args=(f"VEH{i:03d}",)) for i in range(10)]
        [h.start() for h in hilos]; [h.join() for h in hilos]
        celdas = [r for r in resultados if r.startswith("C-")]
        self.assertEqual(len(celdas), len(set(celdas)))


class TestRutas(Base):
    def setUp(self):
        super().setUp()
        from app import crear_app
        self.app = crear_app(); self.app.testing = True

    def login(self, ident, clave):
        cl = self.app.test_client()
        cl.post("/login", data={"identificador": ident, "clave": clave})
        return cl

    def test_exige_sesion(self):
        r = self.app.test_client().get("/celdas")
        self.assertEqual(r.status_code, 302); self.assertIn("/login", r.headers["Location"])

    def test_login_malo(self):
        r = self.app.test_client().post("/login", data={"identificador": "x", "clave": "y"})
        self.assertIn("Credenciales inválidas", r.get_data(as_text=True))

    def test_operador_sin_usuarios(self):  # CP-05
        cl = self.login("operador@autoscolombia.co", "Operador123*")
        self.assertEqual(cl.get("/usuarios").status_code, 302)
        self.assertNotIn(">Usuarios<", cl.get("/celdas").get_data(as_text=True))
        self.assertEqual(cl.get("/celdas").status_code, 200)
        self.assertEqual(cl.get("/celdas/nueva").status_code, 302)

    def test_admin_flujo(self):
        cl = self.login("admin@autoscolombia.co", "Admin123*")
        r = cl.post("/usuarios/nuevo", data=self.datos_usuario(), follow_redirects=True)
        self.assertIn("Usuario registrado correctamente", r.get_data(as_text=True))
        r = cl.post("/usuarios/nuevo", data=self.datos_usuario(correo="o@x.co"), follow_redirects=True)
        self.assertIn("ya se encuentra registrado", r.get_data(as_text=True))
        self.assertIn("1035440210", cl.get("/usuarios?q=1035").get_data(as_text=True))
        r = cl.post("/celdas/nueva", data={"codigo": "CAR-15", "zona": "Nivel 1", "tipo": "Carro"}, follow_redirects=True)
        self.assertIn("CAR-15", r.get_data(as_text=True))
        html = cl.get("/celdas?tipo=Moto").get_data(as_text=True)
        self.assertIn("M-01", html); self.assertNotIn("C-01", html)
        self.assertIn("class=\"celda verde\"", html)
        cl.post("/entrada", data={"placa": "ABC123"})
        self.assertIn("class=\"celda rojo\"", cl.get("/celdas").get_data(as_text=True))
        for ruta in ("/", "/historial", "/vehiculos", "/mensualidades", "/usuarios/nuevo", "/celdas/nueva"):
            self.assertEqual(cl.get(ruta).status_code, 200, ruta)

    def test_inactivo_no_entra(self):
        self.u.cambiar_estado(2, "INACTIVO", id_actor=1)
        r = self.app.test_client().post("/login", data={"identificador": "operador@autoscolombia.co",
                                                        "clave": "Operador123*"})
        self.assertIn("inactivo", r.get_data(as_text=True))


class TestDemo(Base):
    def test_carga_demo_consistente_e_idempotente(self):
        import cargar_demo
        self.assertTrue(cargar_demo.cargar())
        self.assertFalse(cargar_demo.cargar())          # no duplica
        abiertos = list(db.col("movimientos").find({"abierto": True}))
        self.assertEqual(len(abiertos), 3)
        self.assertEqual(len({m["id_celda"] for m in abiertos}), 3)   # una celda, un vehículo
        self.assertGreaterEqual(len(self.m.listar_historial()), 12)
        r = self.c.resumen(self.c.listar())
        self.assertEqual((r["MANTENIMIENTO"], r["RESERVADA"]), (2, 2))
        self.assertEqual(len(self.ct.listar_activos()), 2)
        # cada celda OCUPADA tiene un vehículo dentro y viceversa (salvo las reservadas)
        for m in abiertos:
            estado = self.c.obtener(m["id_celda"]).estado
            self.assertIn(estado, ("OCUPADA", "RESERVADA"))
        self.assertEqual(self.u.buscar("1006")[0].estado, "INACTIVO")


class TestPagos(Base):
    def setUp(self):
        super().setUp()
        from datetime import datetime, timedelta
        from servicios.pago_service import PagoService, calcular_cobro
        from servicios.tarifa_service import TarifaService
        self.p, self.t, self.calc = PagoService(), TarifaService(), calcular_cobro
        self.dt, self.td = datetime, timedelta

    def entrar_hace(self, placa, minutos):
        self.m.registrar_entrada(placa)
        db.col("movimientos").update_one({"abierto": True, "id_vehiculo": db.col("vehiculos").find_one({"placa": placa})["id_vehiculo"]},
                                         {"$set": {"fecha_entrada": self.dt.now() - self.td(minutes=minutos)}})
        return db.col("movimientos").find_one({"abierto": True, "id_vehiculo": db.col("vehiculos").find_one({"placa": placa})["id_vehiculo"]})["id_movimiento"]

    def test_calculo_de_cobro(self):  # RNF-08
        e = self.dt(2026, 1, 1, 8, 0)
        casos = [(5, 0), (10, 0), (11, 4000), (60, 4000), (61, 8000), (180, 12000), (181, 16000)]
        for minutos, esperado in casos:
            self.assertEqual(self.calc(e, e + self.td(minutes=minutos), 4000, 10)[2], esperado, minutos)
        self.assertEqual(self.calc(e, e + self.td(minutes=70), 2000, 10)[2], 4000)  # moto
        self.assertEqual(self.calc(e, e - self.td(minutes=5), 4000, 10)[2], 0)      # fechas invertidas

    def test_tarifas_por_defecto_y_actualizar(self):  # CP-09
        t = self.t.obtener_todas()
        self.assertEqual((t["HORA_Carro"], t["TOLERANCIA_MIN"]), (4000, 10))
        self.t.actualizar({"MENSUALIDAD_Carro": "200.000", "MENSUALIDAD_Moto": "100000", "HORA_Carro": "5000",
                           "HORA_Moto": "2500", "TOLERANCIA_MIN": "15"}, 1)
        self.assertEqual(self.t.obtener_todas()["MENSUALIDAD_Carro"], 200000)
        for malo in ({"HORA_Carro": "abc"}, {"HORA_Carro": "0"}, {"TOLERANCIA_MIN": "90"}):
            datos = {"MENSUALIDAD_Carro": "1", "MENSUALIDAD_Moto": "1", "HORA_Carro": "1", "HORA_Moto": "1",
                     "TOLERANCIA_MIN": "5"}; datos.update(malo)
            with self.assertRaises(ReglaNegocioError):
                self.t.actualizar(datos, 1)

    def test_salida_ocasional_cobra_y_libera(self):  # CP-10
        id_m = self.entrar_hace("ABC123", 130)  # 3 horas por fracción
        vp = self.p.vista_previa_salida(id_m)
        self.assertEqual((vp["valor"], vp["horas"], vp["titular"]), (12000, 3, False))
        pago = self.p.registrar_salida_con_cobro(id_m, "efectivo", "", 2)
        self.assertEqual((pago["valor"], pago["consecutivo"], pago["estado"]), (12000, "PG-000001", "VALIDO"))
        self.assertEqual(self.m.listar_vehiculos_dentro()[1], 15)   # celda liberada
        with self.assertRaises(ReglaNegocioError):                  # no se cobra dos veces
            self.p.registrar_salida_con_cobro(id_m, "efectivo", "", 2)
        self.assertEqual(db.col("pagos").count_documents({}), 1)

    def test_dentro_de_tolerancia_no_cobra(self):
        id_m = self.entrar_hace("ABC123", 4)
        self.assertIsNone(self.p.registrar_salida_con_cobro(id_m, "efectivo", "", 2))
        self.assertEqual(db.col("pagos").count_documents({}), 0)
        self.assertEqual(self.m.listar_vehiculos_dentro()[1], 15)

    def test_titular_de_mensualidad_no_paga(self):  # CP-11
        id_c = self.c.crear("CAR-10", "Nivel 1", "Carro")
        self.ct.asignar("1001", id_c, 30)
        id_m = self.entrar_hace("ABC123", 600)
        self.assertTrue(self.p.vista_previa_salida(id_m)["titular"])
        self.assertIsNone(self.p.registrar_salida_con_cobro(id_m, "", "", 2))
        self.assertEqual(self.c.obtener(id_c).estado, "RESERVADA")

    def test_metodo_y_referencia(self):  # CP-12
        id_m = self.entrar_hace("ABC123", 90)
        with self.assertRaisesRegex(ReglaNegocioError, "método"):
            self.p.registrar_salida_con_cobro(id_m, "CHEQUE", "", 2)
        with self.assertRaisesRegex(ReglaNegocioError, "referencia"):
            self.p.registrar_salida_con_cobro(id_m, "TRANSFERENCIA", "", 2)
        self.assertEqual(self.m.listar_vehiculos_dentro()[0][0]["placa"], "ABC123")  # sigue dentro: no se cerró
        pago = self.p.registrar_salida_con_cobro(id_m, "TARJETA", "AUT-9981", 2)
        self.assertEqual((pago["metodo"], pago["referencia"]), ("TARJETA", "AUT-9981"))

    def test_pago_mensualidad_renueva_30_dias(self):  # CP-13
        id_c = self.c.crear("CAR-10", "Nivel 1", "Carro")
        self.ct.asignar("1001", id_c, 5)
        antes = self.ct.listar_activos()[0]["contrato"].fecha_fin
        pago = self.p.registrar_pago_mensualidad("1001", "TRANSFERENCIA", "TRF-1", 2)
        self.assertEqual(pago["valor"], 180000)
        despues = self.ct.listar_activos()[0]["contrato"].fecha_fin
        self.assertEqual(despues - antes, self.td(days=30))
        with self.assertRaisesRegex(ReglaNegocioError, "referencia"):
            self.p.registrar_pago_mensualidad("1001", "TARJETA", "", 2)

    def test_pago_mensualidad_reglas(self):
        with self.assertRaisesRegex(ReglaNegocioError, "mensualidad activa"):
            self.p.registrar_pago_mensualidad("1001", "EFECTIVO", "", 2)   # sin contrato
        with self.assertRaisesRegex(ReglaNegocioError, "No existe"):
            self.p.registrar_pago_mensualidad("0000", "EFECTIVO", "", 2)
        m = self.c.crear("M-20", "Zona motos", "Moto")
        self.ct.asignar("1001", m, 30)
        self.assertEqual(self.p.registrar_pago_mensualidad("1001", "EFECTIVO", "", 2)["valor"], 90000)  # tarifa moto

    def test_anulacion_conserva_registro_y_revierte(self):  # CP-14
        id_c = self.c.crear("CAR-10", "Nivel 1", "Carro")
        self.ct.asignar("1001", id_c, 5)
        inicial = self.ct.listar_activos()[0]["contrato"].fecha_fin
        pago = self.p.registrar_pago_mensualidad("1001", "EFECTIVO", "", 2)
        with self.assertRaisesRegex(ReglaNegocioError, "motivo"):
            self.p.anular(pago["id_pago"], "  ", 1)
        self.p.anular(pago["id_pago"], "Cliente equivocado", 1)
        self.assertEqual(self.ct.listar_activos()[0]["contrato"].fecha_fin, inicial)
        self.assertEqual(db.col("pagos").find_one({"id_pago": pago["id_pago"]})["estado"], "ANULADO")  # no se borra
        with self.assertRaisesRegex(ReglaNegocioError, "ya fue anulado"):
            self.p.anular(pago["id_pago"], "Otra vez", 1)
        with self.assertRaisesRegex(ReglaNegocioError, "no existe"):
            self.p.anular(999, "No existe el pago", 1)

    def test_listado_y_reporte_excluyen_anulados(self):  # CP-15, CP-16
        a = self.p.registrar_salida_con_cobro(self.entrar_hace("ABC123", 90), "EFECTIVO", "", 2)   # 8.000
        self.u.registrar(self.datos_usuario(documento="55", correo="oc@x.co", rol="CLIENTE"))
        self.m.registrar_vehiculo("MOT11A", "Honda", "Rojo", "Moto", "55")
        b = self.p.registrar_salida_con_cobro(self.entrar_hace("MOT11A", 30), "TRANSFERENCIA", "R1", 3)  # 2.000
        id_c = self.c.crear("CAR-10", "Nivel 1", "Carro"); self.ct.asignar("1001", id_c, 5)
        c = self.p.registrar_pago_mensualidad("1001", "EFECTIVO", "", 2)  # 180.000
        self.p.anular(c["id_pago"], "Error de digitación", 1)
        filas, total = self.p.listar()
        self.assertEqual((len(filas), total), (3, 10000))
        self.assertEqual(len(self.p.listar(estado="ANULADO")[0]), 1)
        self.assertEqual(len(self.p.listar(tipo="OCASIONAL", metodo="TRANSFERENCIA")[0]), 1)
        self.assertEqual(len(self.p.listar(documento="55")[0]), 1)
        self.assertEqual(len(self.p.listar(id_operador=3)[0]), 1)  # solo lo que registró ese operador
        hoy = self.dt.now().date()
        r = self.p.reporte(hoy, hoy)
        self.assertEqual((r["total"], r["cantidad"], r["anulados"], r["valor_anulado"]), (10000, 2, 1, 180000))
        self.assertEqual(r["por_tipo"]["OCASIONAL"]["total"], 10000)
        self.assertEqual(r["por_metodo"]["TRANSFERENCIA"]["total"], 2000)
        self.assertEqual(self.p.reporte(hoy - self.td(days=3), hoy - self.td(days=2))["total"], 0)
        self.assertEqual(self.p.obtener(a["id_pago"])["placa"], "ABC123")

    def test_historial_de_pagos_sobrevive_a_inactivar_usuario(self):  # HU-02 criterio 2.2
        self.p.registrar_salida_con_cobro(self.entrar_hace("ABC123", 90), "EFECTIVO", "", 2)
        self.u.cambiar_estado(3, "INACTIVO", id_actor=1)
        fila = self.p.listar()[0][0]
        self.assertEqual((fila["cliente"], fila["cliente_estado"]), ("Ana Gómez", "INACTIVO"))

    def test_demo_incluye_pagos(self):
        import cargar_demo
        cargar_demo.cargar()
        filas, total = self.p.listar()
        self.assertGreaterEqual(len(filas), 8)
        self.assertGreater(total, 0)
        self.assertEqual(len(self.p.listar(estado="ANULADO")[0]), 1)
        self.assertEqual(db.col("pagos").count_documents({"tipo": "MENSUALIDAD", "estado": "VALIDO"}), 2)


class TestRutasPagos(Base):
    def setUp(self):
        super().setUp()
        from app import crear_app
        self.app = crear_app(); self.app.testing = True

    def login(self, ident, clave):
        cl = self.app.test_client(); cl.post("/login", data={"identificador": ident, "clave": clave}); return cl

    def test_flujo_salida_con_cobro_y_comprobante(self):
        from datetime import datetime, timedelta
        cl = self.login("operador@autoscolombia.co", "Operador123*")
        cl.post("/entrada", data={"placa": "ABC123"})
        db.col("movimientos").update_one({"abierto": True}, {"$set": {"fecha_entrada": datetime.now() - timedelta(minutes=75)}})
        id_m = db.col("movimientos").find_one({"abierto": True})["id_movimiento"]
        html = cl.get(f"/salida/{id_m}").get_data(as_text=True)
        self.assertIn("$ 8.000", html)
        r = cl.post(f"/salida/{id_m}", data={"metodo": "EFECTIVO", "referencia": ""}, follow_redirects=True)
        txt = r.get_data(as_text=True)
        self.assertIn("PG-000001", txt); self.assertIn("$ 8.000", txt); self.assertIn("Imprimir", txt)
        self.assertIn("PG-000001", cl.get("/pagos").get_data(as_text=True))

    def test_permisos_de_pagos(self):  # CP-17
        op = self.login("operador@autoscolombia.co", "Operador123*")
        self.assertEqual(op.get("/tarifas").status_code, 302)
        self.assertEqual(op.get("/pagos/reporte").status_code, 302)
        self.assertEqual(op.post("/pagos/1/anular", data={"motivo": "intento"}).status_code, 302)
        ad = self.login("admin@autoscolombia.co", "Admin123*")
        for ruta in ("/tarifas", "/pagos/reporte", "/pagos", "/pagos/mensualidad", "/mensualidades"):
            self.assertEqual(ad.get(ruta).status_code, 200, ruta)
        self.assertIn("Tarifas", ad.get("/").get_data(as_text=True))
        self.assertNotIn(">Tarifas<", op.get("/").get_data(as_text=True))

    def test_operador_solo_ve_sus_pagos_y_comprobantes(self):
        from datos.db import col
        import cargar_demo
        cargar_demo.cargar()
        op = self.login("operador@autoscolombia.co", "Operador123*")
        propios = col("pagos").count_documents({"id_operador": 2})
        ajeno = col("pagos").find_one({"id_operador": {"$ne": 2}})
        html = op.get("/pagos").get_data(as_text=True)
        self.assertEqual(html.count("/comprobante"), propios)
        self.assertEqual(op.get(f"/pagos/{ajeno['id_pago']}/comprobante").status_code, 302)

    def test_admin_anula_desde_la_interfaz(self):
        from datos.db import col
        import cargar_demo
        cargar_demo.cargar()
        ad = self.login("admin@autoscolombia.co", "Admin123*")
        pago = col("pagos").find_one({"estado": "VALIDO", "tipo": "OCASIONAL"})
        r = ad.post(f"/pagos/{pago['id_pago']}/anular", data={"motivo": "Valor mal digitado"}, follow_redirects=True)
        self.assertIn("Pago anulado", r.get_data(as_text=True))
        self.assertIn("PAGO ANULADO", ad.get(f"/pagos/{pago['id_pago']}/comprobante").get_data(as_text=True))
        self.assertIn("Recaudo total", ad.get("/pagos/reporte?desde=2000-01-01&hasta=2100-01-01").get_data(as_text=True))


if __name__ == "__main__":
    unittest.main()
