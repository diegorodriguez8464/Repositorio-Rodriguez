# ============================================================
# CONTROL DE ACCESO Y ESTADO VEHICULAR
# app/db.py: toda la comunicación con Supabase está aquí.
# Ningún otro módulo usa supabase.table(...) directamente.
#
# Esquema de la base institucional:
#   conductores     (id, rut, nombre_completo, grado_o_cargo,
#                    unidad_destino, estado)
#   vehiculos       (id, patente, tipo_vehiculo, marca_modelo,
#                    anio, kilometraje_actual, estado_operativo)
#   autorizaciones  (id, patente, rut_conductor, fecha_asignacion,
#                    vigente)
#   reportes_estado (id, patente, rut_conductor, fecha_reporte,
#                    kilometraje_salida, nivel_combustible,
#                    presion_neumaticos, luces_operativas,
#                    observaciones, foto_evidencia_url)
#
# Nota de diseño: las tablas se relacionan por patente y por RUT
# (llaves naturales), no por identificadores numéricos.
# ============================================================

import io

import streamlit as st
from PIL import Image
from supabase import Client, create_client

# ------------------------------------------------------------
# Nombres de tablas, bucket y columnas (un solo lugar de cambio)
# ------------------------------------------------------------
TABLA_CONDUCTORES = "conductores"
TABLA_VEHICULOS = "vehiculos"
TABLA_AUTORIZACIONES = "autorizaciones"
TABLA_REPORTES = "reportes_estado"
BUCKET = "evidencias-vehiculares"

# Tamaño máximo de imagen exigido por la actividad
MAX_KB_IMAGEN = 800

# Estados del vehículo que maneja la lógica de negocio
ESTADO_OPERATIVO = "Operativo"
ESTADO_MANTENCION = "Requiere Mantención"
ESTADO_INMOVILIZADO = "Inmovilizado"

# Estado del conductor que habilita la conducción
CONDUCTOR_ACTIVO = "Activo"


# ------------------------------------------------------------
# Conexión: el cliente se crea una sola vez y se reutiliza.
# Las credenciales se leen desde .streamlit/secrets.toml, nunca
# desde el código fuente (requisito de la Sección A).
# ------------------------------------------------------------
@st.cache_resource
def obtener_cliente() -> Client:
    try:
        url = st.secrets["supabase"]["url"]
        key = st.secrets["supabase"]["key"]
    except Exception:
        st.error("No se encontraron las credenciales en .streamlit/secrets.toml")
        st.stop()
    return create_client(url, key)


# ------------------------------------------------------------
# Consultas (lectura)
# ------------------------------------------------------------
def obtener_vehiculos():
    return (obtener_cliente().table(TABLA_VEHICULOS)
            .select("*").order("patente").execute().data)


def obtener_conductores():
    return (obtener_cliente().table(TABLA_CONDUCTORES)
            .select("*").order("nombre_completo").execute().data)


def obtener_autorizaciones():
    return obtener_cliente().table(TABLA_AUTORIZACIONES).select("*").execute().data


def obtener_reportes():
    """Bitácora completa, del reporte más reciente al más antiguo."""
    return (obtener_cliente().table(TABLA_REPORTES)
            .select("*").order("id", desc=True).execute().data)


def buscar_vehiculo_por_patente(patente):
    """Busca el vehículo tolerando guiones y mayúsculas.

    El OCR puede entregar la patente sin guion (ABCD12) mientras la
    base la almacena con guion (ABCD-12); por eso, si la búsqueda
    exacta falla, se compara ignorando los separadores.
    """
    patente = (patente or "").strip().upper()
    if not patente:
        return None

    datos = (obtener_cliente().table(TABLA_VEHICULOS)
             .select("*").eq("patente", patente).execute().data)
    if datos:
        return datos[0]

    # Segundo intento: comparación sin separadores.
    objetivo = solo_alfanumerico(patente)
    for vehiculo in obtener_vehiculos():
        if solo_alfanumerico(vehiculo.get("patente")) == objetivo:
            return vehiculo
    return None


def buscar_conductor_por_rut(rut):
    datos = (obtener_cliente().table(TABLA_CONDUCTORES)
             .select("*").eq("rut", rut).execute().data)
    return datos[0] if datos else None


def obtener_autorizaciones_de_patente(patente):
    """Autorizaciones vigentes de un vehículo (consulta cruzada)."""
    return (obtener_cliente().table(TABLA_AUTORIZACIONES)
            .select("*").eq("patente", patente).execute().data)


def obtener_reportes_de_patente(patente):
    return (obtener_cliente().table(TABLA_REPORTES)
            .select("*").eq("patente", patente)
            .order("id", desc=True).execute().data)


# ------------------------------------------------------------
# Escritura
# ------------------------------------------------------------
def insertar_reporte(registro):
    """Inserta una fila en la bitácora de estado."""
    respuesta = obtener_cliente().table(TABLA_REPORTES).insert(registro).execute()
    return respuesta.data[0] if respuesta.data else None


def actualizar_estado_vehiculo(patente, nuevo_estado):
    """Actualiza el estado operativo del vehículo en la tabla maestra."""
    (obtener_cliente().table(TABLA_VEHICULOS)
     .update({"estado_operativo": nuevo_estado})
     .eq("patente", patente).execute())


def actualizar_kilometraje(patente, kilometraje):
    """Actualiza el odómetro registrado del vehículo."""
    (obtener_cliente().table(TABLA_VEHICULOS)
     .update({"kilometraje_actual": kilometraje})
     .eq("patente", patente).execute())


# ------------------------------------------------------------
# Almacenamiento de evidencias fotográficas
# ------------------------------------------------------------
def comprimir_imagen(bytes_imagen, max_kb=MAX_KB_IMAGEN):
    """Reduce la imagen hasta quedar bajo el máximo exigido (800 kb).

    Se baja la calidad JPEG por pasos; si aún no alcanza, se reduce
    la resolución. Así ninguna evidencia supera el límite del bucket.
    """
    imagen = Image.open(io.BytesIO(bytes_imagen))
    if imagen.mode in ("RGBA", "P"):
        imagen = imagen.convert("RGB")

    for calidad in (85, 70, 55, 40, 25):
        buffer = io.BytesIO()
        imagen.save(buffer, format="JPEG", quality=calidad, optimize=True)
        if buffer.tell() <= max_kb * 1024:
            return buffer.getvalue()

    imagen = imagen.resize((imagen.width // 2, imagen.height // 2))
    buffer = io.BytesIO()
    imagen.save(buffer, format="JPEG", quality=60, optimize=True)
    return buffer.getvalue()


def subir_evidencia(bytes_imagen, nombre_archivo):
    """Sube la imagen al bucket y devuelve su URL pública."""
    imagen_comprimida = comprimir_imagen(bytes_imagen)
    cliente = obtener_cliente()
    cliente.storage.from_(BUCKET).upload(
        nombre_archivo, imagen_comprimida,
        file_options={"content-type": "image/jpeg"})
    return cliente.storage.from_(BUCKET).get_public_url(nombre_archivo)


# ------------------------------------------------------------
# Utilidades
# ------------------------------------------------------------
def solo_alfanumerico(texto):
    """Deja únicamente letras y números, en mayúsculas."""
    return "".join(c for c in str(texto or "").upper() if c.isalnum())


def nombre_archivo_seguro(patente, prefijo, marca_tiempo):
    """Nombre de archivo sin guiones ni caracteres problemáticos."""
    return prefijo + "_" + solo_alfanumerico(patente) + "_" + marca_tiempo + ".jpg"
