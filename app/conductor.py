# ============================================================
# CONTROL DE ACCESO Y ESTADO VEHICULAR
# app/conductor.py: módulo de autogestión (perfil Conductor).
#
# El conductor reporta las condiciones operativas de su unidad.
# Si algún parámetro crítico queda fuera de norma, la lógica
# actualiza automáticamente el estado del vehículo en la tabla
# maestra a "Requiere Mantención".
# ============================================================

from datetime import datetime

import streamlit as st

from app import db
from app import evaluacion as ev


def vista():
    st.title("Check-in Operativo - Conductor")
    st.caption("Reporte periódico de las condiciones de la unidad.")

    vehiculos = db.obtener_vehiculos()
    conductores = db.obtener_conductores()

    if not vehiculos or not conductores:
        st.warning("No hay vehículos o conductores cargados en la base.")
        return

    # Diccionarios para recuperar el registro completo desde el texto elegido.
    opciones_vehiculo = {
        str(v.get("patente")) + " · " + str(v.get("marca_modelo")): v
        for v in vehiculos}
    opciones_conductor = {
        str(c.get("grado_o_cargo", "")) + " " + str(c.get("nombre_completo")): c
        for c in conductores}

    with st.form("form_reporte"):
        col1, col2 = st.columns(2)
        texto_conductor = col1.selectbox("Conductor",
                                         list(opciones_conductor.keys()))
        texto_vehiculo = col2.selectbox("Vehículo a cargo",
                                        list(opciones_vehiculo.keys()))

        st.subheader("Odómetro y combustible")
        col1, col2 = st.columns(2)
        kilometraje = col1.number_input("Kilometraje de salida (km)",
                                        min_value=0, step=100, value=0)
        combustible = col2.number_input("Nivel de combustible (%)",
                                        min_value=0.0, max_value=100.0,
                                        value=80.0, step=1.0)

        st.subheader("Estado de los sistemas")
        col1, col2, col3 = st.columns(3)
        presion_ok = col1.radio("Presión de neumáticos",
                                ["Conforme", "Fuera de norma"]) == "Conforme"
        luces_ok = col2.radio("Sistema de luces",
                              ["Conforme", "Con falla"]) == "Conforme"
        frenos_ok = col3.radio("Sistema de frenos",
                               ["Conforme", "Con falla"]) == "Conforme"

        novedades = st.text_area("Novedades mecánicas observadas")

        st.subheader("Evidencia fotográfica")
        foto = st.camera_input("Fotografía del odómetro o de la novedad")

        enviar = st.form_submit_button("Enviar reporte de estado")

    if not enviar:
        return

    vehiculo = opciones_vehiculo[texto_vehiculo]
    conductor = opciones_conductor[texto_conductor]
    patente = vehiculo["patente"]

    # --- Evaluación: Kill-Switch, ISV y condición (Evaluación N°02) ---
    resultado = ev.evaluar_reporte(frenos_ok, presion_ok, luces_ok, combustible)
    fallas = resultado["motivos_kill_switch"]

    # --- Evidencia fotográfica, comprimida bajo 800 kb ---
    url_imagen = None
    if foto is not None:
        try:
            marca = datetime.now().strftime("%Y%m%d_%H%M%S")
            nombre = db.nombre_archivo_seguro(patente, "reporte", marca)
            url_imagen = db.subir_evidencia(foto.getvalue(), nombre)
        except Exception as e:
            st.warning("No se pudo subir la evidencia: " + str(e))

    # El resultado del algoritmo se consolida en el campo observaciones,
    # porque la tabla institucional no tiene columnas para ISV ni condición.
    texto = ("[REPORTE] ISV: " + str(resultado["isv"]) +
             " | Condición: " + resultado["condicion"] +
             " | Frenos: " + ("Conformes" if frenos_ok else "CON FALLA"))
    if resultado["kill_switch"]:
        texto += " | KILL-SWITCH: " + " ".join(fallas)
    if novedades:
        texto += " | Novedades: " + novedades

    registro = {
        "patente": patente,
        "rut_conductor": conductor.get("rut"),
        "kilometraje_salida": kilometraje,
        "nivel_combustible": combustible,
        "presion_neumaticos": presion_ok,
        "luces_operativas": luces_ok,
        "observaciones": texto,
        "foto_evidencia_url": url_imagen,
    }

    try:
        db.insertar_reporte(registro)
    except Exception as e:
        st.error("Error al guardar el reporte: " + str(e))
        return

    # El odómetro de la tabla maestra se actualiza con la última lectura.
    if kilometraje > 0:
        try:
            db.actualizar_kilometraje(patente, kilometraje)
        except Exception:
            pass

    # --- Resultado en pantalla ---
    st.subheader("Resultado de la evaluación")
    col1, col2, col3 = st.columns(3)
    col1.metric("ISV calculado", f"{resultado['isv']:.2f}")
    col2.metric("Condición", resultado["condicion"])
    col3.metric("Indicadores con falla", resultado["num_fallas"])

    # Si hay Kill-Switch, se actualiza el estado en la tabla maestra.
    nuevo_estado = ev.estado_operativo_segun_condicion(resultado["condicion"])

    if resultado["kill_switch"]:
        try:
            db.actualizar_estado_vehiculo(patente, nuevo_estado)
            st.error("KILL-SWITCH ACTIVADO: parámetro crítico fuera de norma.")
            st.write("La unidad **" + patente + "** fue marcada "
                     "automáticamente como **" + nuevo_estado +
                     "** en la tabla maestra de vehículos.")
        except Exception as e:
            st.warning("No se pudo actualizar el estado del vehículo: " + str(e))
        for falla in fallas:
            st.write("- " + falla)
    else:
        st.success("Reporte registrado. La unidad se mantiene operativa.")

    if resultado["fallas"]:
        st.warning("Indicadores bajo el 100%: " + " | ".join(resultado["fallas"]))
