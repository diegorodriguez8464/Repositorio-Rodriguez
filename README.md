# Sistema de Control de Acceso y Estado Vehicular

Solución web y móvil para la gestión de acceso y el control del estado operativo del material rodante en instalaciones militares.

**Programación Avanzada** · I CRIM Sistemas de Armas · Academia Politécnica Militar
Profesor: Dr. Carlos Santibáñez Rodríguez · Noviembre de 2026

---

## Descripción

El sistema reemplaza el registro manual de guardia y las inspecciones mecánicas en papel por una aplicación conectada a una base de datos en la nube. Opera bajo un esquema de tres perfiles de usuario, cada uno con su propio módulo:

| Perfil | Función |
|---|---|
| **Guardia de Garita** | Identifica la patente, cruza vehículo, conductor y autorización, y resuelve el acceso. |
| **Conductor Operativo** | Reporta las condiciones de la unidad y adjunta evidencia fotográfica. |
| **Administrador de Puesto de Mando** | Consulta el estado de apresto de la flota, la analítica de uso y la bitácora auditable. |

## Arquitectura

```
Navegador  ──▶  Streamlit (app.py)
                     │
                     ├── app/guardia.py     consulta cruzada y resolución de acceso
                     ├── app/conductor.py   reporte de novedades
                     ├── app/admin.py       panel de inteligencia de negocios
                     ├── app/evaluacion.py  algoritmo ISV y Kill-Switch
                     └── app/db.py          única puerta hacia la nube
                                │
                     Supabase ──┴── PostgreSQL + Storage
```

La aplicación está organizada en capas. `db.py` concentra todo el acceso a Supabase, de modo que ningún otro módulo consulta la base directamente. `evaluacion.py` contiene el algoritmo puro, sin dependencias de Streamlit ni de la base de datos, por lo que puede verificarse de forma aislada.

## Estructura del proyecto

```
.
├── app.py                 punto de entrada: sesión y navegación condicional
├── app/
│   ├── db.py              acceso a PostgreSQL y a Storage
│   ├── guardia.py         módulo de garita
│   ├── conductor.py       módulo de autogestión
│   ├── admin.py           panel de mando
│   └── evaluacion.py      algoritmo de evaluación del estado
├── sql/
│   └── esquema.sql        script de inyección del modelo relacional
├── .streamlit/
│   └── secrets.toml       credenciales (excluido del repositorio)
├── explorar.py            utilitario de inspección del esquema
├── requirements.txt
└── packages.txt
```

## Modelo de datos

Cuatro entidades relacionadas mediante llaves naturales (patente y RUT):

- **conductores** — personal habilitado: RUT, nombre, grado, unidad de destino y estado.
- **vehiculos** — catálogo maestro: patente, tipo, material, año, kilometraje y estado operativo.
- **autorizaciones** — tabla transaccional que vincula qué conductor puede operar qué vehículo y su vigencia.
- **reportes_estado** — bitácora de accesos y de reportes de novedades, con la URL de la evidencia fotográfica.

Las imágenes se almacenan en el bucket **evidencias-vehiculares**, comprimidas bajo 800 kb antes de subirse.

## Lógica de negocio

### Resolución del control de acceso

La validación cruza tres tablas y devuelve uno de tres resultados:

| Resultado | Condición |
|---|---|
| **AUTORIZADO** | Autorización vigente, conductor activo y vehículo operativo. |
| **ALERTA DE ESTADO** | Autorización vigente, pero la unidad presenta novedades mecánicas. |
| **DENEGADO** | Sin autorización vigente, o conductor no activo, o patente no registrada. |

### Índice de Salud del Vehículo

El algoritmo, reutilizado de la Evaluación N°02, opera en dos etapas. La **Etapa A** detecta fallas en sistemas vitales (Kill-Switch) y tiene prioridad sobre el índice. La **Etapa B** calcula el ISV como suma ponderada de los indicadores:

| Indicador | Peso |
|---|---|
| Sistema de frenos | 0,30 |
| Presión de neumáticos | 0,30 |
| Nivel de combustible | 0,20 |
| Sistema de luces | 0,20 |

Cuando un reporte activa el Kill-Switch, la aplicación actualiza automáticamente el estado del vehículo a **Requiere Mantención** en la tabla maestra. Desde ese momento la garita devuelve ALERTA DE ESTADO para esa unidad y el panel de mando la muestra en amarillo.

## Instalación

```bash
python -m venv .venv
.venv\Scripts\activate          # Windows
python -m pip install -r requirements.txt
```

Crear el archivo `.streamlit/secrets.toml` con las credenciales:

```toml
[supabase]
url = "https://TU_PROYECTO.supabase.co"
key = "TU_CLAVE"
```

Ejecutar:

```bash
python -m streamlit run app.py
```

## Perfiles de prueba

| Usuario | Contraseña | Perfil |
|---|---|---|
| `guardia` | `guardia123` | Guardia de Garita |
| `conductor` | `conductor123` | Conductor Operativo |
| `admin` | `admin123` | Administrador de Puesto de Mando |

## Seguridad

Las credenciales de la base de datos no están escritas en el código: se leen desde `.streamlit/secrets.toml`, archivo excluido del repositorio mediante `.gitignore`. En el despliegue, las mismas claves se cargan en el gestor de secretos de la plataforma.

## Tecnologías

Python · Streamlit · Supabase (PostgreSQL y Storage) · Pandas · Pillow · EasyOCR
