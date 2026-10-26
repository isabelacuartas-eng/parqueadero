PRAGMA foreign_keys = ON;
CREATE TABLE IF NOT EXISTS tipo_vehiculo (
  id_tipo INTEGER PRIMARY KEY AUTOINCREMENT,
  nombre  VARCHAR(30) NOT NULL UNIQUE
);
CREATE TABLE IF NOT EXISTS usuario (
  id_usuario INTEGER PRIMARY KEY AUTOINCREMENT,
  documento  VARCHAR(20) NOT NULL UNIQUE,
  nombre     VARCHAR(80) NOT NULL,
  telefono   VARCHAR(20),
  estado     VARCHAR(10) NOT NULL DEFAULT 'ACTIVO'
);
CREATE TABLE IF NOT EXISTS vehiculo (
  id_vehiculo INTEGER PRIMARY KEY AUTOINCREMENT,
  placa       VARCHAR(10) NOT NULL UNIQUE,
  marca       VARCHAR(40),
  color       VARCHAR(30),
  id_tipo     INTEGER NOT NULL REFERENCES tipo_vehiculo(id_tipo),
  id_usuario  INTEGER NOT NULL REFERENCES usuario(id_usuario)
);
CREATE TABLE IF NOT EXISTS celda (
  id_celda INTEGER PRIMARY KEY AUTOINCREMENT,
  codigo   VARCHAR(10) NOT NULL UNIQUE,
  id_tipo  INTEGER NOT NULL REFERENCES tipo_vehiculo(id_tipo),
  estado   VARCHAR(13) NOT NULL DEFAULT 'DISPONIBLE'
           CHECK (estado IN ('DISPONIBLE','OCUPADA','MANTENIMIENTO'))
);
CREATE TABLE IF NOT EXISTS movimiento (
  id_movimiento INTEGER PRIMARY KEY AUTOINCREMENT,
  id_vehiculo   INTEGER NOT NULL REFERENCES vehiculo(id_vehiculo),
  id_celda      INTEGER NOT NULL REFERENCES celda(id_celda),
  fecha_entrada DATETIME NOT NULL,
  fecha_salida  DATETIME,
  observacion   VARCHAR(200)
);
INSERT OR IGNORE INTO tipo_vehiculo(id_tipo,nombre) VALUES (1,'Carro'),(2,'Moto');
