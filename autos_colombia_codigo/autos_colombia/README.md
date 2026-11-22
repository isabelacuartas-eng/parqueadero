# Autos Colombia – Iteraciones 1, 2 y 3

Sistema de información del parqueadero por mensualidad.

- **Iteración 1:** entrada y salida de vehículos, historial, registro de vehículos.
- **Iteración 3:** gestión de pagos: tarifas, cobro de vehículos ocasionales a la salida, pago de mensualidad
  (renueva el contrato 30 días), comprobante imprimible, historial con filtros, anulación y reporte de recaudo.
- **Iteración 2:** autenticación con roles, gestión de usuarios, gestión de celdas (estados, panel semáforo) y
  asignación de celdas reservadas a clientes con mensualidad.

**Tecnología:** Python 3.10+, Flask, MongoDB (pymongo). Arquitectura por capas:
`modelo` (entidades) · `servicios` (reglas de negocio) · `datos` (acceso a MongoDB) ·
`controladores` (rutas) · `templates` (vistas).

## Ejecutar
1. Tener MongoDB corriendo (local en `mongodb://localhost:27017` o un clúster de MongoDB Atlas).
2. Instalar dependencias y arrancar:

       pip install -r requirements.txt
       python app.py

   Abrir http://127.0.0.1:5000

Variables de entorno opcionales: `MONGO_URI` (por defecto `mongodb://localhost:27017`), `MONGO_DB`
(por defecto `autos_colombia`) y `SECRET_KEY`.

Al primer arranque se crean los índices y datos de demostración (15 celdas, un cliente con la placa ABC123).

| Rol | Usuario | Contraseña |
|---|---|---|
| Administrador | admin@autoscolombia.co | Admin123* |
| Operador | operador@autoscolombia.co | Operador123* |

## Datos de ejemplo (para demostraciones y el video)
    py cargar_demo.py              # agrega clientes, vehículos, historial, mensualidades y celdas en mantenimiento
    py cargar_demo.py --limpiar    # borra TODA la base y la recarga desde cero

Los usuarios de ejemplo usan la contraseña `Cliente123*` (los clientes no inician sesión; solo
administrador y operador tienen acceso a la plataforma). Incluye pagos de ejemplo (válidos y uno anulado).

## Permisos
- **Administrador:** todo, incluido el módulo de usuarios y la creación de celdas.
- **Operador:** vehículos, entrada/salida, panel de celdas (cambiar disponible ↔ mantenimiento) y mensualidades.

## Pagos (iteración 3)
- **Tarifas** (solo administrador): mensualidad y valor por hora para carro y moto, y minutos de tolerancia sin cobro.
  Valores iniciales de ejemplo: mensualidad carro $180.000 / moto $90.000; hora carro $4.000 / moto $2.000; tolerancia 10 min.
- **Cobro a la salida:** el vehículo ocasional paga por hora o fracción (mínimo una hora, después de la tolerancia).
  El titular de una mensualidad que sale de su celda reservada no paga.
- **Pago de mensualidad:** toma la tarifa según el tipo de la celda y renueva el contrato 30 días.
- **Anulación** (solo administrador): el pago no se borra, queda `ANULADO` con motivo y responsable; si era una
  mensualidad se revierten los 30 días.
- **Permisos:** el operador registra pagos y ve únicamente los suyos; el administrador ve todos, configura tarifas,
  anula pagos y consulta el reporte de recaudo.
- Los valores se guardan como enteros en pesos (sin decimales) y un movimiento solo puede tener un cobro válido
  (índice único parcial en `pagos.id_movimiento`).

## Decisiones de diseño
- Contraseñas con hash (`werkzeug.security`); nunca en texto plano (RNF-01).
- Los usuarios no se eliminan: se inactivan y conservan su historial (RF-03).
- Concurrencia (RNF-03): la asignación de celda usa `find_one_and_update` atómico sobre
  `estado = DISPONIBLE`, y los índices únicos parciales impiden dos movimientos abiertos sobre la misma celda
  o dos contratos activos para una misma celda o cliente.
- Estados de celda: `DISPONIBLE` (verde), `OCUPADA` (rojo), `MANTENIMIENTO` (amarillo), `RESERVADA` (azul).
  Una celda ocupada o reservada no se modifica manualmente.

## Pruebas
    python -m unittest discover -s . -t . -v

Las pruebas automáticas usan un MongoDB simulado en memoria (`tests/fake_mongo.py`), por lo que no requieren
servidor. Antes de la sustentación conviene ejecutar el flujo manual contra un MongoDB real.
