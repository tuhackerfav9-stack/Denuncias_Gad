-- =========================================================
-- SISTEMA DE DENUNCIAS (PostgreSQL) - VERSION FINAL
-- =========================================================

CREATE EXTENSION IF NOT EXISTS "pgcrypto"; -- gen_random_uuid()

-- =========================
-- ENUMS
-- =========================
DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'usuario_tipo') THEN
    CREATE TYPE usuario_tipo AS ENUM ('ciudadano', 'funcionario');
  END IF;

  IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'denuncia_estado') THEN
    CREATE TYPE denuncia_estado AS ENUM ('pendiente','en_revision','asignada','en_proceso','resuelta','rechazada');
  END IF;

  IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'evidencia_tipo') THEN
    CREATE TYPE evidencia_tipo AS ENUM ('foto','video','audio','documento');
  END IF;

  IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'denuncia_origen') THEN
    CREATE TYPE denuncia_origen AS ENUM ('formulario','chat');
  END IF;
END $$;

-- =========================
-- updated_at TRIGGER
-- =========================
CREATE OR REPLACE FUNCTION set_updated_at()
RETURNS TRIGGER AS $$
BEGIN
  NEW.updated_at = now();
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- =========================================================
-- 1) USUARIOS (LOGIN / AUTH COMÚN)
-- =========================================================
CREATE TABLE IF NOT EXISTS usuarios (
  id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tipo             usuario_tipo NOT NULL,
  correo           VARCHAR(150) NOT NULL UNIQUE,
  password_hash    TEXT NOT NULL,
  activo           BOOLEAN NOT NULL DEFAULT TRUE,
  correo_verificado BOOLEAN NOT NULL DEFAULT FALSE,
  created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);

DROP TRIGGER IF EXISTS tr_usuarios_updated ON usuarios;
CREATE TRIGGER tr_usuarios_updated
BEFORE UPDATE ON usuarios
FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- =========================================================
-- 2) CIUDADANOS (PERFIL)
-- =========================================================
CREATE TABLE IF NOT EXISTS ciudadanos (
  usuario_id       UUID PRIMARY KEY REFERENCES usuarios(id) ON DELETE CASCADE,

  cedula           VARCHAR(15) NOT NULL UNIQUE,
  nombres          VARCHAR(100) NOT NULL,
  apellidos        VARCHAR(100) NOT NULL,
  telefono         VARCHAR(20),
  fecha_nacimiento DATE,

  foto_perfil_url  TEXT,
  firma_url        TEXT,   -- opcional
  firma_base64     TEXT,   -- opcional

  created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at       TIMESTAMPTZ NOT NULL DEFAULT now(),

  -- permite ambos NULL o solo uno lleno, pero no ambos llenos
  CHECK ((firma_url IS NULL) OR (firma_base64 IS NULL))
);

DROP TRIGGER IF EXISTS tr_ciudadanos_updated ON ciudadanos;
CREATE TRIGGER tr_ciudadanos_updated
BEFORE UPDATE ON ciudadanos
FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- Documentos del ciudadano (cédula frontal/trasera)
CREATE TABLE IF NOT EXISTS ciudadano_documentos (
  id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  ciudadano_id   UUID NOT NULL REFERENCES ciudadanos(usuario_id) ON DELETE CASCADE,
  tipo_documento VARCHAR(50) NOT NULL DEFAULT 'cedula',
  url_frontal    TEXT,
  url_trasera    TEXT,
  created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);

DROP TRIGGER IF EXISTS tr_ciudadano_documentos_updated ON ciudadano_documentos;
CREATE TRIGGER tr_ciudadano_documentos_updated
BEFORE UPDATE ON ciudadano_documentos
FOR EACH ROW EXECUTE FUNCTION set_updated_at();

CREATE INDEX IF NOT EXISTS idx_ciudadano_documentos_ciudadano
ON ciudadano_documentos(ciudadano_id);

-- =========================================================
-- 3) FUNCIONARIOS (PERFIL)
-- =========================================================
CREATE TABLE IF NOT EXISTS departamentos (
  id         BIGSERIAL PRIMARY KEY,
  nombre     VARCHAR(120) NOT NULL UNIQUE,
  activo     BOOLEAN NOT NULL DEFAULT TRUE,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
ALTER TABLE departamentos ADD COLUMN IF NOT EXISTS color_hex VARCHAR(7);


DROP TRIGGER IF EXISTS tr_departamentos_updated ON departamentos;
CREATE TRIGGER tr_departamentos_updated
BEFORE UPDATE ON departamentos
FOR EACH ROW EXECUTE FUNCTION set_updated_at();

CREATE TABLE IF NOT EXISTS funcionarios (
  usuario_id      UUID PRIMARY KEY REFERENCES usuarios(id) ON DELETE CASCADE,

  cedula          VARCHAR(15) NOT NULL UNIQUE,
  nombres         VARCHAR(100) NOT NULL,
  apellidos       VARCHAR(100) NOT NULL,
  telefono        VARCHAR(20),

  departamento_id BIGINT REFERENCES departamentos(id) ON DELETE SET NULL,
  cargo           VARCHAR(100),
  activo          BOOLEAN NOT NULL DEFAULT TRUE,

  created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

DROP TRIGGER IF EXISTS tr_funcionarios_updated ON funcionarios;
CREATE TRIGGER tr_funcionarios_updated
BEFORE UPDATE ON funcionarios
FOR EACH ROW EXECUTE FUNCTION set_updated_at();

CREATE INDEX IF NOT EXISTS idx_funcionarios_depto
ON funcionarios(departamento_id);

-- Roles
CREATE TABLE IF NOT EXISTS roles (
  id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  nombre      VARCHAR(40) NOT NULL UNIQUE,  -- ADMIN, JEFE, OPERADOR, LECTOR
  descripcion TEXT,
  created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

DROP TRIGGER IF EXISTS tr_roles_updated ON roles;
CREATE TRIGGER tr_roles_updated
BEFORE UPDATE ON roles
FOR EACH ROW EXECUTE FUNCTION set_updated_at();

CREATE TABLE IF NOT EXISTS funcionario_roles (
  funcionario_id UUID NOT NULL REFERENCES funcionarios(usuario_id) ON DELETE CASCADE,
  rol_id         UUID NOT NULL REFERENCES roles(id) ON DELETE CASCADE,
  created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (funcionario_id, rol_id)
);

-- =========================================================
-- 4) TIPOS DE DENUNCIA
-- =========================================================
CREATE TABLE IF NOT EXISTS tipos_denuncia (
  id          BIGSERIAL PRIMARY KEY,
  nombre      VARCHAR(120) NOT NULL UNIQUE,
  descripcion TEXT,
  activo      BOOLEAN NOT NULL DEFAULT TRUE,
  created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

DROP TRIGGER IF EXISTS tr_tipos_denuncia_updated ON tipos_denuncia;
CREATE TRIGGER tr_tipos_denuncia_updated
BEFORE UPDATE ON tipos_denuncia
FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- =========================================================
-- 5) DENUNCIAS 
-- =========================================================
CREATE TABLE IF NOT EXISTS denuncias (
  id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  ciudadano_id      UUID NOT NULL REFERENCES ciudadanos(usuario_id) ON DELETE RESTRICT,
  tipo_denuncia_id  BIGINT NOT NULL REFERENCES tipos_denuncia(id) ON DELETE RESTRICT,

  descripcion       TEXT NOT NULL,
  referencia        TEXT,

  latitud           DOUBLE PRECISION NOT NULL,
  longitud          DOUBLE PRECISION NOT NULL,
  direccion_texto   TEXT,

  origen            denuncia_origen NOT NULL DEFAULT 'formulario',
  estado            denuncia_estado NOT NULL DEFAULT 'pendiente',

  asignado_departamento_id BIGINT REFERENCES departamentos(id) ON DELETE SET NULL,
  asignado_funcionario_id  UUID REFERENCES funcionarios(usuario_id) ON DELETE SET NULL,

  created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at        TIMESTAMPTZ NOT NULL DEFAULT now()
);

DROP TRIGGER IF EXISTS tr_denuncias_updated ON denuncias;
CREATE TRIGGER tr_denuncias_updated
BEFORE UPDATE ON denuncias
FOR EACH ROW EXECUTE FUNCTION set_updated_at();

CREATE INDEX IF NOT EXISTS idx_denuncias_ciudadano ON denuncias(ciudadano_id);
CREATE INDEX IF NOT EXISTS idx_denuncias_estado ON denuncias(estado);
CREATE INDEX IF NOT EXISTS idx_denuncias_tipo ON denuncias(tipo_denuncia_id);
CREATE INDEX IF NOT EXISTS idx_denuncias_geo ON denuncias(latitud, longitud);
CREATE INDEX IF NOT EXISTS idx_denuncias_fecha ON denuncias(created_at);

-- Evidencias
CREATE TABLE IF NOT EXISTS denuncia_evidencias (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  denuncia_id     UUID NOT NULL REFERENCES denuncias(id) ON DELETE CASCADE,
  tipo            evidencia_tipo NOT NULL,
  url_archivo     TEXT NOT NULL,
  nombre_archivo  TEXT,
  created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

DROP TRIGGER IF EXISTS tr_denuncia_evidencias_updated ON denuncia_evidencias;
CREATE TRIGGER tr_denuncia_evidencias_updated
BEFORE UPDATE ON denuncia_evidencias
FOR EACH ROW EXECUTE FUNCTION set_updated_at();

CREATE INDEX IF NOT EXISTS idx_denuncia_evidencias_denuncia
ON denuncia_evidencias(denuncia_id);

-- Firma por denuncia (1:1)
CREATE TABLE IF NOT EXISTS denuncia_firmas (
  id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  denuncia_id  UUID NOT NULL UNIQUE REFERENCES denuncias(id) ON DELETE CASCADE,
  firma_url    TEXT,
  firma_base64 TEXT,
  created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
  CHECK ((firma_url IS NOT NULL) OR (firma_base64 IS NOT NULL))
);

DROP TRIGGER IF EXISTS tr_denuncia_firmas_updated ON denuncia_firmas;
CREATE TRIGGER tr_denuncia_firmas_updated
BEFORE UPDATE ON denuncia_firmas
FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- Historial de estados (auditoría)
CREATE TABLE IF NOT EXISTS denuncia_historial (
  id                    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  denuncia_id           UUID NOT NULL REFERENCES denuncias(id) ON DELETE CASCADE,
  estado_anterior       denuncia_estado,
  estado_nuevo          denuncia_estado NOT NULL,
  comentario            TEXT,
  cambiado_por_funcionario UUID REFERENCES funcionarios(usuario_id) ON DELETE SET NULL,
  created_at            TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_denuncia_historial_denuncia
ON denuncia_historial(denuncia_id);

-- Asignaciones (historial)
CREATE TABLE IF NOT EXISTS denuncia_asignaciones (
  id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  denuncia_id    UUID NOT NULL REFERENCES denuncias(id) ON DELETE CASCADE,
  funcionario_id UUID NOT NULL REFERENCES funcionarios(usuario_id) ON DELETE CASCADE,
  asignado_en    TIMESTAMPTZ NOT NULL DEFAULT now(),
  activo         BOOLEAN NOT NULL DEFAULT TRUE
);

CREATE INDEX IF NOT EXISTS idx_denuncia_asignaciones_denuncia
ON denuncia_asignaciones(denuncia_id);

-- Respuestas del funcionario al ciudadano
CREATE TABLE IF NOT EXISTS denuncia_respuestas (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  denuncia_id     UUID NOT NULL REFERENCES denuncias(id) ON DELETE CASCADE,
  funcionario_id  UUID REFERENCES funcionarios(usuario_id) ON DELETE SET NULL,
  mensaje         TEXT NOT NULL,
  created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

DROP TRIGGER IF EXISTS tr_denuncia_respuestas_updated ON denuncia_respuestas;
CREATE TRIGGER tr_denuncia_respuestas_updated
BEFORE UPDATE ON denuncia_respuestas
FOR EACH ROW EXECUTE FUNCTION set_updated_at();

CREATE INDEX IF NOT EXISTS idx_denuncia_respuestas_denuncia
ON denuncia_respuestas(denuncia_id);

-- =========================================================
-- 6) RECUPERACIÓN CONTRASEÑA
-- =========================================================
CREATE TABLE IF NOT EXISTS password_reset_tokens (
  id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  usuario_id UUID NOT NULL REFERENCES usuarios(id) ON DELETE CASCADE,
  codigo_6   VARCHAR(6) NOT NULL,
  expira_en  TIMESTAMPTZ NOT NULL,
  usado      BOOLEAN NOT NULL DEFAULT FALSE,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

DROP TRIGGER IF EXISTS tr_password_reset_tokens_updated ON password_reset_tokens;
CREATE TRIGGER tr_password_reset_tokens_updated
BEFORE UPDATE ON password_reset_tokens
FOR EACH ROW EXECUTE FUNCTION set_updated_at();

CREATE INDEX IF NOT EXISTS idx_reset_usuario ON password_reset_tokens(usuario_id);
CREATE INDEX IF NOT EXISTS idx_reset_expira ON password_reset_tokens(expira_en);

-- =========================================================
-- 7) CHAT + BORRADOR
-- =========================================================
CREATE TABLE IF NOT EXISTS chat_conversaciones (
  id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  ciudadano_id UUID NOT NULL REFERENCES ciudadanos(usuario_id) ON DELETE CASCADE,
  denuncia_id  UUID REFERENCES denuncias(id) ON DELETE SET NULL, -- cuando ya se envía
  created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

DROP TRIGGER IF EXISTS tr_chat_conversaciones_updated ON chat_conversaciones;
CREATE TRIGGER tr_chat_conversaciones_updated
BEFORE UPDATE ON chat_conversaciones
FOR EACH ROW EXECUTE FUNCTION set_updated_at();

CREATE TABLE IF NOT EXISTS chat_mensajes (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  conversacion_id UUID NOT NULL REFERENCES chat_conversaciones(id) ON DELETE CASCADE,
  emisor          VARCHAR(10) NOT NULL CHECK (emisor IN ('usuario','bot')),
  mensaje         TEXT NOT NULL,
  created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_chat_mensajes_conversacion
ON chat_mensajes(conversacion_id);

-- Borrador que el chat va llenando
CREATE TABLE IF NOT EXISTS denuncia_borradores (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  ciudadano_id    UUID NOT NULL REFERENCES ciudadanos(usuario_id) ON DELETE CASCADE,
  conversacion_id UUID REFERENCES chat_conversaciones(id) ON DELETE SET NULL,

  datos_json      JSONB NOT NULL DEFAULT '{}'::jsonb,  -- tipo, descripcion, ubicacion, etc.
  listo_para_enviar BOOLEAN NOT NULL DEFAULT FALSE,

  created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

DROP TRIGGER IF EXISTS tr_denuncia_borradores_updated ON denuncia_borradores;
CREATE TRIGGER tr_denuncia_borradores_updated
BEFORE UPDATE ON denuncia_borradores
FOR EACH ROW EXECUTE FUNCTION set_updated_at();

CREATE INDEX IF NOT EXISTS idx_borradores_ciudadano
ON denuncia_borradores(ciudadano_id);

-- 1 borrador por conversación
CREATE UNIQUE INDEX IF NOT EXISTS uq_borrador_conversacion
ON denuncia_borradores(conversacion_id);

-- =========================================================
-- 8) VISTA PARA MAPA
-- =========================================================
CREATE OR REPLACE VIEW v_mapa_denuncias AS
SELECT
  d.id AS denuncia_id,
  d.latitud,
  d.longitud,
  d.descripcion,
  d.created_at AS fecha,
  d.estado,
  td.nombre AS tipo_denuncia,
  (c.nombres || ' ' || c.apellidos) AS ciudadano
FROM denuncias d
JOIN tipos_denuncia td ON td.id = d.tipo_denuncia_id
JOIN ciudadanos c ON c.usuario_id = d.ciudadano_id;

-- =========================================================
-- 9) insert basicos
-- =========================================================
INSERT INTO roles (nombre, descripcion)
VALUES
('ADMIN', 'Admin del sistema (panel TIC)'),
('JEFE', 'Jefe de área / asignación'),
('OPERADOR', 'Gestiona denuncias'),
('LECTOR', 'Solo lectura / reportes')
ON CONFLICT (nombre) DO NOTHING;

INSERT INTO departamentos (nombre, color_hex) VALUES
('Dirección de Servicios Públicos', '#0d6efd'),
('Dirección de Agua Potable y Alcantarillado', '#0dcaf0'),
('Dirección de Gestión Ambiental y Desechos Sólidos', '#198754'),
('Dirección de Obras Públicas', '#fd7e14'),
('Dirección de Desarrollo Social, Económico, Cultura y Turismo', '#6f42c1'),
('Dirección de Seguridad Ciudadana, Control Público y Gestión de Riesgos', '#dc3545'),
('Registro de la Propiedad y Mercantil', '#20c997'),
('Junta Cantonal de Protección de Derechos', '#d63384')
ON CONFLICT (nombre) DO NOTHING;

INSERT INTO tipos_denuncia (nombre, descripcion)
VALUES
--  Dirección de Servicios Públicos
('Falta de alumbrado público', 'Ausencia total de iluminación en calles, avenidas o espacios públicos'),
('Luminarias dañadas', 'Postes o luminarias que no funcionan, parpadean o están rotas'),
('Acumulación de basura en vía pública', 'Basura acumulada en calles, veredas o espacios públicos'),
('Parques o espacios públicos abandonados', 'Falta de mantenimiento, limpieza o cuidado en parques y áreas recreativas'),

--  Dirección de Agua Potable y Alcantarillado
('Falta de agua potable', 'Corte total o parcial del suministro de agua potable'),
('Agua contaminada o turbia', 'Agua con mal olor, color o presencia de residuos'),
('Fuga de agua', 'Escapes visibles de agua en calles, veredas o domicilios'),
('Alcantarillado tapado o colapsado', 'Desbordamiento o bloqueo del sistema de alcantarillado'),

--  Dirección de Gestión Ambiental y Desechos Sólidos
('Botadero clandestino', 'Depósitos ilegales de basura o escombros en espacios no autorizados'),
('Quema de basura', 'Incineración ilegal de desechos que provoca contaminación'),
('Manejo inadecuado de residuos', 'Desechos mal dispuestos o fuera de horarios establecidos'),
('Contaminación ambiental', 'Afectación al aire, suelo o agua por actividades contaminantes'),

--  Dirección de Obras Públicas
('Calles en mal estado', 'Vías con deterioro general que dificultan la circulación'),
('Baches o huecos en la vía', 'Huecos peligrosos en calles o avenidas'),
('Aceras o veredas dañadas', 'Infraestructura peatonal rota o en mal estado'),
('Obra pública abandonada', 'Obras municipales paralizadas o sin concluir'),

--  Dirección de Desarrollo Social, Económico, Cultura y Turismo
('Problemas en programas sociales', 'Incumplimiento o fallas en proyectos y ayudas sociales'),
('Maltrato a grupos vulnerables', 'Abuso o negligencia hacia adultos mayores, personas con discapacidad u otros grupos'),
('Uso indebido de espacios culturales', 'Mal uso o deterioro de centros y espacios culturales'),
('Eventos culturales mal organizados', 'Deficiencias en la planificación o ejecución de eventos municipales'),

--  Dirección de Seguridad Ciudadana, Control Público y Gestión de Riesgos
('Comercio informal o ilegal', 'Actividad comercial sin permisos en espacios públicos'),
('Uso indebido del espacio público', 'Ocupación no autorizada de calles, veredas o plazas'),
('Riesgo estructural', 'Edificaciones con peligro de colapso o daños graves'),
('Falta de control municipal', 'Ausencia de supervisión o control por parte de autoridades'),

--  Registro de la Propiedad y Mercantil
('Trámite irregular', 'Procesos administrativos con anomalías o posibles irregularidades'),
('Error en escrituras o registros', 'Datos incorrectos en documentos legales registrados'),
('Demora injustificada en trámites', 'Retrasos excesivos sin explicación válida'),

--  Junta Cantonal de Protección de Derechos
('Vulneración de derechos', 'Violación de derechos de niños, niñas o adolescentes'),
('Maltrato infantil', 'Abuso físico, psicológico o negligencia hacia menores'),
('Violencia intrafamiliar', 'Agresiones dentro del núcleo familiar'),

--  General
('Otro', 'Cualquier otro tipo de denuncia no contemplada en las categorías anteriores')
ON CONFLICT (nombre) DO NOTHING;

-- =========================================================
-- 10) AUTOMATIZACIÓN: tipo_denuncia -> departamento
-- =========================================================
CREATE TABLE IF NOT EXISTS tipo_denuncia_departamento (
  tipo_denuncia_id BIGINT PRIMARY KEY
    REFERENCES tipos_denuncia(id) ON DELETE CASCADE,
  departamento_id BIGINT NOT NULL
    REFERENCES departamentos(id) ON DELETE RESTRICT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

DROP TRIGGER IF EXISTS tr_tipo_denuncia_departamento_updated ON tipo_denuncia_departamento;
CREATE TRIGGER tr_tipo_denuncia_departamento_updated
BEFORE UPDATE ON tipo_denuncia_departamento
FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- ---------------------
-- inserts donde unimos departamento con su tipo denuncia

INSERT INTO tipo_denuncia_departamento (tipo_denuncia_id, departamento_id)
SELECT td.id, d.id
FROM tipos_denuncia td
JOIN departamentos d ON d.nombre = 'Dirección de Servicios Públicos'
WHERE td.nombre IN (
  'Falta de alumbrado público',
  'Luminarias dañadas',
  'Acumulación de basura en vía pública',
  'Parques o espacios públicos abandonados'
)
ON CONFLICT (tipo_denuncia_id) DO NOTHING;

INSERT INTO tipo_denuncia_departamento (tipo_denuncia_id, departamento_id)
SELECT td.id, d.id
FROM tipos_denuncia td
JOIN departamentos d ON d.nombre = 'Dirección de Agua Potable y Alcantarillado'
WHERE td.nombre IN (
  'Falta de agua potable',
  'Agua contaminada o turbia',
  'Fuga de agua',
  'Alcantarillado tapado o colapsado'
)
ON CONFLICT (tipo_denuncia_id) DO NOTHING;

INSERT INTO tipo_denuncia_departamento (tipo_denuncia_id, departamento_id)
SELECT td.id, d.id
FROM tipos_denuncia td
JOIN departamentos d ON d.nombre = 'Dirección de Gestión Ambiental y Desechos Sólidos'
WHERE td.nombre IN (
  'Botadero clandestino',
  'Quema de basura',
  'Manejo inadecuado de residuos',
  'Contaminación ambiental'
)
ON CONFLICT (tipo_denuncia_id) DO NOTHING;

INSERT INTO tipo_denuncia_departamento (tipo_denuncia_id, departamento_id)
SELECT td.id, d.id
FROM tipos_denuncia td
JOIN departamentos d ON d.nombre = 'Dirección de Obras Públicas'
WHERE td.nombre IN (
  'Calles en mal estado',
  'Baches o huecos en la vía',
  'Aceras o veredas dañadas',
  'Obra pública abandonada'
)
ON CONFLICT (tipo_denuncia_id) DO NOTHING;

INSERT INTO tipo_denuncia_departamento (tipo_denuncia_id, departamento_id)
SELECT td.id, d.id
FROM tipos_denuncia td
JOIN departamentos d ON d.nombre = 'Dirección de Desarrollo Social, Económico, Cultura y Turismo'
WHERE td.nombre IN (
  'Problemas en programas sociales',
  'Maltrato a grupos vulnerables',
  'Uso indebido de espacios culturales',
  'Eventos culturales mal organizados'
)
ON CONFLICT (tipo_denuncia_id) DO NOTHING;

INSERT INTO tipo_denuncia_departamento (tipo_denuncia_id, departamento_id)
SELECT td.id, d.id
FROM tipos_denuncia td
JOIN departamentos d ON d.nombre = 'Dirección de Seguridad Ciudadana, Control Público y Gestión de Riesgos'
WHERE td.nombre IN (
  'Comercio informal o ilegal',
  'Uso indebido del espacio público',
  'Riesgo estructural',
  'Falta de control municipal'
)
ON CONFLICT (tipo_denuncia_id) DO NOTHING;

INSERT INTO tipo_denuncia_departamento (tipo_denuncia_id, departamento_id)
SELECT td.id, d.id
FROM tipos_denuncia td
JOIN departamentos d ON d.nombre = 'Registro de la Propiedad y Mercantil'
WHERE td.nombre IN (
  'Trámite irregular',
  'Error en escrituras o registros',
  'Demora injustificada en trámites'
)
ON CONFLICT (tipo_denuncia_id) DO NOTHING;

INSERT INTO tipo_denuncia_departamento (tipo_denuncia_id, departamento_id)
SELECT td.id, d.id
FROM tipos_denuncia td
JOIN departamentos d ON d.nombre = 'Junta Cantonal de Protección de Derechos'
WHERE td.nombre IN (
  'Vulneración de derechos',
  'Maltrato infantil',
  'Violencia intrafamiliar'
)
ON CONFLICT (tipo_denuncia_id) DO NOTHING;

INSERT INTO tipo_denuncia_departamento (tipo_denuncia_id, departamento_id)
SELECT td.id, d.id
FROM tipos_denuncia td
JOIN departamentos d ON d.nombre = 'Dirección de Seguridad Ciudadana, Control Público y Gestión de Riesgos'
WHERE td.nombre = 'Otro'
ON CONFLICT (tipo_denuncia_id) DO NOTHING;


-- =========================================================
-- 11) TRIGGER: asignar departamento automático (BEFORE INSERT)
-- =========================================================
CREATE OR REPLACE FUNCTION asignar_departamento_automatico()
RETURNS TRIGGER AS $$
DECLARE
  v_departamento_id BIGINT;
BEGIN
  SELECT departamento_id
  INTO v_departamento_id
  FROM tipo_denuncia_departamento
  WHERE tipo_denuncia_id = NEW.tipo_denuncia_id;

  IF v_departamento_id IS NOT NULL THEN
    NEW.asignado_departamento_id := v_departamento_id;
    NEW.estado := 'asignada';
  END IF;

  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS tr_asignar_departamento ON denuncias;
CREATE TRIGGER tr_asignar_departamento
BEFORE INSERT ON denuncias
FOR EACH ROW
EXECUTE FUNCTION asignar_departamento_automatico();

-- =========================================================
-- 12) HISTORIAL AUTOMÁTICO
--   A) Al INSERT: registra asignación automática
--   B) Al UPDATE: registra cambios de estado
-- =========================================================

-- A) Insert
CREATE OR REPLACE FUNCTION historial_asignacion_automatica()
RETURNS TRIGGER AS $$
BEGIN
  IF NEW.asignado_departamento_id IS NOT NULL THEN
    INSERT INTO denuncia_historial (
      denuncia_id, estado_anterior, estado_nuevo, comentario
    )
    VALUES (
      NEW.id, NULL, NEW.estado, 'Asignación automática según tipo de denuncia'
    );
  END IF;

  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS tr_historial_auto_insert ON denuncias;
CREATE TRIGGER tr_historial_auto_insert
AFTER INSERT ON denuncias
FOR EACH ROW
EXECUTE FUNCTION historial_asignacion_automatica();

-- B) Update de estado
CREATE OR REPLACE FUNCTION historial_estado_update()
RETURNS TRIGGER AS $$
BEGIN
  IF NEW.estado IS DISTINCT FROM OLD.estado THEN
    INSERT INTO denuncia_historial (
      denuncia_id, estado_anterior, estado_nuevo, comentario, cambiado_por_funcionario
    )
    VALUES (
      NEW.id,
      OLD.estado,
      NEW.estado,
      'Cambio de estado',
      NEW.asignado_funcionario_id
    );
  END IF;

  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS tr_historial_estado_update ON denuncias;
CREATE TRIGGER tr_historial_estado_update
AFTER UPDATE ON denuncias
FOR EACH ROW
EXECUTE FUNCTION historial_estado_update();

-- =========================================================
-- 13) FAQ (ayuda)
-- =========================================================
CREATE TABLE IF NOT EXISTS faq (
  id         BIGSERIAL PRIMARY KEY,
  pregunta   TEXT NOT NULL,
  respuesta  TEXT NOT NULL,
  visible    BOOLEAN NOT NULL DEFAULT TRUE,

  creado_por UUID REFERENCES usuarios(id) ON DELETE SET NULL,

  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

DROP TRIGGER IF EXISTS tr_faq_updated ON faq;
CREATE TRIGGER tr_faq_updated
BEFORE UPDATE ON faq
FOR EACH ROW EXECUTE FUNCTION set_updated_at();

ALTER TABLE faq ADD COLUMN IF NOT EXISTS categoria VARCHAR(40) NOT NULL DEFAULT 'general';
CREATE INDEX IF NOT EXISTS idx_faq_categoria ON faq(categoria);


-- =========================================================
-- 14) NOTIFICACIONES (para notificacions push o whatsap o email)
-- =========================================================
CREATE TABLE IF NOT EXISTS notificaciones (
  id         BIGSERIAL PRIMARY KEY,

  usuario_id UUID NOT NULL REFERENCES usuarios(id) ON DELETE CASCADE,

  titulo     VARCHAR(150) NOT NULL,
  mensaje    TEXT NOT NULL,

  tipo       VARCHAR(30) NOT NULL DEFAULT 'sistema', 
  -- sistema | email | push | sms | whatsapp

  leido      BOOLEAN NOT NULL DEFAULT FALSE,

  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

DROP TRIGGER IF EXISTS tr_notificaciones_updated ON notificaciones;
CREATE TRIGGER tr_notificaciones_updated
BEFORE UPDATE ON notificaciones
FOR EACH ROW EXECUTE FUNCTION set_updated_at();

CREATE INDEX IF NOT EXISTS idx_notificaciones_usuario
ON notificaciones(usuario_id);

-- =========================================================
-- 15) AUDITORÍA
-- =========================================================
CREATE TABLE IF NOT EXISTS auditoria (
  id            BIGSERIAL PRIMARY KEY,

  usuario_id    UUID REFERENCES usuarios(id) ON DELETE SET NULL,

  accion        VARCHAR(100) NOT NULL,
  tabla_afectada VARCHAR(100),

  registro_id   TEXT, -- puede ser UUID o BIGINT convertido a texto

  detalle       TEXT,
  ip_origen     VARCHAR(45),

  created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

DROP TRIGGER IF EXISTS tr_auditoria_updated ON auditoria;
CREATE TRIGGER tr_auditoria_updated
BEFORE UPDATE ON auditoria
FOR EACH ROW EXECUTE FUNCTION set_updated_at();



-- ------------------------------flujo para la pap movil---------------------------------------
CREATE TABLE IF NOT EXISTS registro_ciudadano_borrador (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

  -- Paso 1
  cedula VARCHAR(15) NOT NULL,
  nombres VARCHAR(100) NOT NULL,
  apellidos VARCHAR(100) NOT NULL,
  telefono VARCHAR(20),

  -- Paso 2
  correo VARCHAR(150),
  codigo_6 VARCHAR(6),
  codigo_expira TIMESTAMPTZ,
  correo_verificado BOOLEAN NOT NULL DEFAULT FALSE,

  -- Paso 3
  fecha_nacimiento DATE,

  -- Paso 4 (guardamos URL en texto como tu BD)
  cedula_frontal_url TEXT,
  cedula_trasera_url TEXT,

  -- Estado del borrador
  finalizado BOOLEAN NOT NULL DEFAULT FALSE,

  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_registro_borrador_correo
ON registro_ciudadano_borrador(correo);

CREATE INDEX IF NOT EXISTS idx_registro_borrador_cedula
ON registro_ciudadano_borrador(cedula);

