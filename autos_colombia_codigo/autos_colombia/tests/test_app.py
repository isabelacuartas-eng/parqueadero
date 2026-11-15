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


if __name__ == "__main__":
    unittest.main()
