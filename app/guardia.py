# ============================================================
# CONTROL DE ACCESO Y ESTADO VEHICULAR
# app/guardia.py: módulo de garita (perfil Guardia).
#
# Ingresa o escanea una patente, efectúa la consulta cruzada
# vehículo - autorización - conductor y resuelve el acceso en
# tres estados: AUTORIZADO, DENEGADO o ALERTA DE ESTADO.
# ============================================================

from datetime import datetime

import streamlit as st

from app import db

AUTORIZADO = "AUTORIZADO"
DENEGADO = "DENEGADO"
ALERTA = "ALERTA DE ESTADO"


def leer_patente_ocr(bytes_imagen):
    """Reconoce la patente con OCR. Si EasyOCR no está instalado,
    la aplicación sigue operando con ingreso manual."""
    try:
        import io

        import easyocr
        import numpy as np
        from PIL import Image

        @st.cache_resource
        def cargar_lector():
            return easyocr.Reader(["es", "en"], gpu=False)

        lector = cargar_lector()
        imagen = np.array(Image.open(io.BytesIO(bytes_imagen)))
        resultados = lector.readtext(imagen)
        if resultados:
            return max(resultados, key=lambda r: r[2])[1].upper().strip()
    except Exception:
        return ""
    return ""


def resolver_acceso(vehiculo, conductor, autorizacion):
    """Cruza las tres entidades y determina el resultado del control.

    Regla de negocio, en orden de prioridad:
      1. Sin autorización vigente que vincule patente y RUT: DENEGADO.
      2. Conductor no activo: DENEGADO.
      3. Vehículo fuera de estado Operativo: ALERTA DE ESTADO.
      4. Todo conforme: AUTORIZADO.
    """
    motivos = []

    if autorizacion is None:
        motivos.append("No existe autorización que vincule al conductor "
                       "con el vehículo.")
    elif not autorizacion.get("vigente", False):
        motivos.append("La autorización registrada no se encuentra vigente.")

    if conductor is None:
        motivos.append("El conductor no figura en el registro institucional.")
    elif str(conductor.get("estado", "")) != db.CONDUCTOR_ACTIVO:
        motivos.append("El conductor no está activo (estado: " +
                       str(conductor.get("estado")) + ").")

    if motivos:
        return DENEGADO, motivos

    estado = str(vehiculo.get("estado_operativo", db.ESTADO_OPERATIVO))
    if estado != db.ESTADO_OPERATIVO:
        return ALERTA, ["Estado operativo del vehículo: " + estado]

    return AUTORIZADO, []


def vista():
    st.title("Control de Acceso - Garita")
    st.caption("Consulta cruzada de vehículo, conductor y autorización vigente.")

    # --- 1) Identificación del vehículo ---
    st.subheader("1. Identificación del vehículo")

    bytes_imagen = None
    patente_detectada = ""

    imagen = st.camera_input("Fotografiar la patente (opcional)")
    if imagen is not None:
        bytes_imagen = imagen.getvalue()
        with st.spinner("Procesando OCR..."):
            patente_detectada = leer_patente_ocr(bytes_imagen)
        if patente_detectada:
            st.success("Texto detectado: " + patente_detectada)
        else:
            st.info("No se reconoció texto. Ingrese la patente manualmente.")

    patente_ingresada = st.text_input("Patente (ejemplo: ABCD-12)",
                                      value=patente_detectada).strip()
    if not patente_ingresada:
        st.stop()

    vehiculo = db.buscar_vehiculo_por_patente(patente_ingresada)
    if vehiculo is None:
        st.error("ACCESO DENEGADO")
        st.write("- La patente no figura en el catálogo institucional.")
        st.stop()

    patente = vehiculo["patente"]

    # --- 2) Antecedentes del vehículo ---
    st.subheader("2. Antecedentes del vehículo")
    col1, col2, col3 = st.columns(3)
    col1.metric("Patente", patente)
    col2.metric("Estado operativo", str(vehiculo.get("estado_operativo", "-")))
    col3.metric("Kilometraje", str(vehiculo.get("kilometraje_actual", "-")))
    st.write("**Tipo:** " + str(vehiculo.get("tipo_vehiculo", "-")) +
             " · **Material:** " + str(vehiculo.get("marca_modelo", "-")) +
             " · **Año:** " + str(vehiculo.get("anio", "-")))

    # --- 3) Verificación cruzada del conductor ---
    st.subheader("3. Verificación del conductor")

    autorizaciones = db.obtener_autorizaciones_de_patente(patente)
    if not autorizaciones:
        st.error("ACCESO DENEGADO")
        st.write("- El vehículo no tiene conductores autorizados registrados.")
        st.stop()

    # Se indexan los conductores por RUT para cruzar con las autorizaciones.
    conductores = {c["rut"]: c for c in db.obtener_conductores()}

    opciones = {}
    for aut in autorizaciones:
        conductor = conductores.get(aut.get("rut_conductor"))
        if conductor:
            etiqueta = (str(conductor.get("grado_o_cargo", "")) + " " +
                        str(conductor.get("nombre_completo", "")) +
                        " · " + str(conductor.get("rut", "")))
        else:
            etiqueta = "RUT " + str(aut.get("rut_conductor")) + " (no registrado)"
        opciones[etiqueta] = (conductor, aut)

    etiqueta = st.selectbox("Conductor que presenta el vehículo",
                            list(opciones.keys()))
    conductor, autorizacion = opciones[etiqueta]

    if conductor:
        st.write("**Unidad de destino:** " +
                 str(conductor.get("unidad_destino", "-")) +
                 " · **Estado:** " + str(conductor.get("estado", "-")))

    # --- 4) Resolución del control ---
    st.subheader("4. Resolución del control de acceso")
    resultado, motivos = resolver_acceso(vehiculo, conductor, autorizacion)

    if resultado == AUTORIZADO:
        st.success("ACCESO AUTORIZADO")
    elif resultado == ALERTA:
        st.warning("ALERTA DE ESTADO — autorización vigente, pero la unidad "
                   "presenta novedades mecánicas pendientes.")
    else:
        st.error("ACCESO DENEGADO")

    for motivo in motivos:
        st.write("- " + motivo)

    # --- 5) Registro del movimiento en la bitácora ---
    st.subheader("5. Registro del movimiento")
    with st.form("form_acceso"):
        movimiento = st.selectbox("Movimiento", ["ENTRADA", "SALIDA"])
        observacion = st.text_input("Observaciones del guardia (opcional)")
        registrar = st.form_submit_button("Registrar movimiento")

    if not registrar:
        return

    # La evidencia fotográfica se comprime bajo 800 kb antes de subir.
    url_imagen = None
    if bytes_imagen is not None:
        try:
            marca = datetime.now().strftime("%Y%m%d_%H%M%S")
            nombre = db.nombre_archivo_seguro(patente, "acceso", marca)
            url_imagen = db.subir_evidencia(bytes_imagen, nombre)
        except Exception as e:
            st.warning("No se pudo subir la evidencia: " + str(e))

    # El movimiento se escribe en reportes_estado con un prefijo que
    # identifica su origen, manteniendo una bitácora única y auditable.
    texto = ("[ACCESO " + movimiento + "] Resultado: " + resultado)
    if motivos:
        texto += " | " + " ".join(motivos)
    if observacion:
        texto += " | Obs: " + observacion

    registro = {
        "patente": patente,
        "rut_conductor": (conductor or {}).get("rut"),
        "kilometraje_salida": vehiculo.get("kilometraje_actual"),
        "observaciones": texto,
        "foto_evidencia_url": url_imagen,
    }

    try:
        db.insertar_reporte(registro)
        st.success(movimiento + " registrada para " + patente + ".")
    except Exception as e:
        st.error("Error al registrar el movimiento: " + str(e))
