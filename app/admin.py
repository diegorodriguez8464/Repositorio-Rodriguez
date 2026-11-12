# ============================================================
# CONTROL DE ACCESO Y ESTADO VEHICULAR
# app/admin.py: panel de Inteligencia de Negocios (Puesto de Mando).
#
# Sección C de la actividad:
#   - Monitoreo operativo: disponibilidad, unidades inmovilizadas
#     y matriz de estado por color (Verde / Amarillo / Rojo).
#   - Analítica de uso: kilometraje y frecuencia de accesos.
#   - Auditoría de incidencias: visor de bitácora con fotografías.
# ============================================================

import pandas as pd
import streamlit as st

from app import db
from app import evaluacion as ev

VERDE = "🟢"
AMARILLO = "🟡"
ROJO = "🔴"


def color_de_estado(estado):
    """Traduce el estado operativo del vehículo a un código de color."""
    estado = str(estado)
    if estado == db.ESTADO_OPERATIVO:
        return VERDE + " Operativo"
    if "Mant" in estado:
        return AMARILLO + " " + estado
    return ROJO + " " + estado


def vista():
    st.title("Puesto de Mando - Panel Operativo")
    st.caption("Estado de apresto de la flota, analítica de uso y auditoría.")

    vehiculos = db.obtener_vehiculos()
    reportes = db.obtener_reportes()

    if not vehiculos:
        st.warning("No hay vehículos en el catálogo.")
        return

    df_vehiculos = pd.DataFrame(vehiculos)
    df_reportes = pd.DataFrame(reportes) if reportes else pd.DataFrame()

    # ------------------------------------------------------------
    # 1) Monitoreo operativo
    # ------------------------------------------------------------
    st.header("Monitoreo operativo")

    estados = df_vehiculos["estado_operativo"].astype(str)
    total = len(df_vehiculos)
    operativos = int((estados == db.ESTADO_OPERATIVO).sum())
    mantencion = int(estados.str.contains("Mant").sum())
    inmovilizados = total - operativos - mantencion
    disponibilidad = (operativos / total * 100) if total else 0

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Disponibilidad de la flota", f"{disponibilidad:.1f} %")
    col2.metric("Unidades operativas", operativos)
    col3.metric("Requieren mantención", mantencion)
    col4.metric("Inmovilizadas", inmovilizados)

    st.progress(min(disponibilidad / 100, 1.0))

    if mantencion or inmovilizados:
        st.warning("Unidades no disponibles: " + str(mantencion + inmovilizados) +
                   " de " + str(total))

    st.subheader("Matriz de estado por vehículo")
    matriz = pd.DataFrame({
        "Estado": estados.apply(color_de_estado),
        "Patente": df_vehiculos.get("patente", ""),
        "Tipo": df_vehiculos.get("tipo_vehiculo", ""),
        "Material": df_vehiculos.get("marca_modelo", ""),
        "Año": df_vehiculos.get("anio", ""),
        "Kilometraje": df_vehiculos.get("kilometraje_actual", ""),
    })
    st.dataframe(matriz, hide_index=True, use_container_width=True)
    st.caption("🟢 Operativo · 🟡 Requiere mantención · 🔴 Inmovilizado")

    # ------------------------------------------------------------
    # 1.b) Índice de Salud del Vehículo (Evaluación N°02)
    # El ISV se recalcula sobre el último reporte de cada unidad,
    # aplicando los mismos pesos y Kill-Switch del algoritmo anterior.
    # ------------------------------------------------------------
    if not df_reportes.empty:
        st.subheader("Índice de Salud del Vehículo (ISV)")

        filas_isv = []
        for patente in df_reportes["patente"].dropna().unique():
            ultimo = df_reportes[df_reportes["patente"] == patente].iloc[0]
            resultado = ev.evaluar_reporte(
                frenos_ok="CON FALLA" not in str(ultimo.get("observaciones", "")),
                presion_ok=bool(ultimo.get("presion_neumaticos")),
                luces_ok=bool(ultimo.get("luces_operativas")),
                combustible=float(ultimo.get("nivel_combustible") or 0))
            filas_isv.append({
                "Patente": patente,
                "ISV": resultado["isv"],
                "Condición": resultado["condicion"],
                "Kill-Switch": "Sí" if resultado["kill_switch"] else "No",
                "Indicadores con falla": resultado["num_fallas"],
            })

        df_isv = pd.DataFrame(filas_isv)
        col1, col2 = st.columns([1, 2])
        col1.metric("ISV promedio de la flota", f"{df_isv['ISV'].mean():.2f}")
        col2.dataframe(df_isv, hide_index=True, use_container_width=True)
        st.bar_chart(df_isv.set_index("Patente")["ISV"])

    # ------------------------------------------------------------
    # 2) Analítica de uso y consumo
    # ------------------------------------------------------------
    st.header("Analítica de uso y consumo")

    col1, col2 = st.columns(2)

    with col1:
        st.subheader("Kilometraje por unidad")
        if "kilometraje_actual" in df_vehiculos.columns:
            km = df_vehiculos.set_index("patente")["kilometraje_actual"]
            st.bar_chart(km)

    with col2:
        st.subheader("Frecuencia de registros por unidad")
        if not df_reportes.empty and "patente" in df_reportes.columns:
            st.bar_chart(df_reportes["patente"].value_counts())
        else:
            st.info("Aún no hay registros en la bitácora.")

    # Distribución de la flota por tipo de vehículo
    if "tipo_vehiculo" in df_vehiculos.columns:
        st.subheader("Composición de la flota por tipo")
        st.bar_chart(df_vehiculos["tipo_vehiculo"].value_counts())

    # ------------------------------------------------------------
    # 3) Auditoría de incidencias
    # ------------------------------------------------------------
    st.header("Auditoría de incidencias")

    if df_reportes.empty:
        st.info("Aún no hay reportes ni accesos registrados.")
        return

    patentes = ["Todas"] + sorted(
        df_vehiculos["patente"].dropna().astype(str).tolist())
    patente_elegida = st.selectbox("Seleccione una patente para auditar",
                                   patentes)

    filtrados = df_reportes
    if patente_elegida != "Todas":
        filtrados = df_reportes[df_reportes["patente"] == patente_elegida]

    if filtrados.empty:
        st.info("Sin registros para la patente seleccionada.")
        return

    st.write("Registros encontrados: " + str(len(filtrados)))

    # Feed cronológico con la evidencia fotográfica del Storage
    for _, fila in filtrados.iterrows():
        with st.container():
            col_datos, col_foto = st.columns([2, 1])
            with col_datos:
                st.write("**Registro N°" + str(fila.get("id")) + "** · " +
                         str(fila.get("patente")))
                st.write("**Fecha:** " + str(fila.get("fecha_reporte", "-")))
                st.write("**Conductor (RUT):** " +
                         str(fila.get("rut_conductor", "-")))
                st.write("**Kilometraje:** " +
                         str(fila.get("kilometraje_salida", "-")) +
                         " · **Combustible:** " +
                         str(fila.get("nivel_combustible", "-")) + "%")
                st.write("**Neumáticos:** " +
                         ("Conforme" if fila.get("presion_neumaticos") else "Fuera de norma") +
                         " · **Luces:** " +
                         ("Conforme" if fila.get("luces_operativas") else "Con falla"))
                observaciones = fila.get("observaciones")
                if isinstance(observaciones, str) and observaciones.strip():
                    st.write("**Observaciones:** " + observaciones)
            with col_foto:
                url = fila.get("foto_evidencia_url")
                if isinstance(url, str) and url.strip():
                    st.image(url, width=180, caption="Evidencia")
                else:
                    st.caption("Sin evidencia fotográfica")
            st.divider()
