# ============================================================
# CONTROL DE ACCESO Y ESTADO VEHICULAR - INSTALACIONES MILITARES
# Programación Avanzada - I CRIM Sistemas de Armas
# Academia Politécnica Militar
# Profesor: Dr. Carlos Santibáñez Rodríguez
#
# Integrante: Tte Diego Rodríguez Uribe
# Fecha: 12 de noviembre de 2026
#
# Librerías principales:
# - Streamlit (interfaz web y móvil)
# - Supabase (PostgreSQL y Storage en la nube)
# - Pandas (analítica del panel de mando)
# - Pillow (compresión de evidencias bajo 800 kb)
# - EasyOCR (lectura de patentes, opcional)
#
# app.py: punto de entrada. Gestiona la sesión, la autenticación
# por perfil y la navegación condicional entre las tres vistas.
# Las credenciales se leen desde .streamlit/secrets.toml.
# ============================================================

import streamlit as st

from app import admin, conductor, guardia

st.set_page_config(page_title="Control Vehicular - Regimiento",
                   page_icon="🚨", layout="wide")

# ------------------------------------------------------------
# Perfiles del sistema y credenciales de prueba
# En producción estas credenciales se validarían contra la tabla
# de usuarios o contra Supabase Auth; aquí se mantienen locales
# para no exponer datos personales en el repositorio público.
# ------------------------------------------------------------
PERFILES = {
    "guardia":   {"clave": "guardia123",   "rol": "Guardia",
                  "nombre": "Guardia de Garita"},
    "conductor": {"clave": "conductor123", "rol": "Conductor",
                  "nombre": "Conductor Operativo"},
    "admin":     {"clave": "admin123",     "rol": "Administrador",
                  "nombre": "Administrador de Puesto de Mando"},
}


def iniciar_estado():
    """Inicializa las variables de sesión la primera vez."""
    if "autenticado" not in st.session_state:
        st.session_state.autenticado = False
    if "rol" not in st.session_state:
        st.session_state.rol = None
    if "nombre" not in st.session_state:
        st.session_state.nombre = ""


def pantalla_login():
    """Formulario de acceso. Mientras no se valide, no se muestra nada más."""
    st.title("Sistema de Control Vehicular")
    st.caption("Acceso restringido. Ingrese sus credenciales institucionales.")

    with st.form("form_login"):
        usuario = st.text_input("Usuario")
        clave = st.text_input("Contraseña", type="password")
        ingresar = st.form_submit_button("Ingresar")

    if not ingresar:
        st.info("Perfiles de prueba: guardia / conductor / admin")
        return

    perfil = PERFILES.get(usuario.strip().lower())
    if perfil and clave == perfil["clave"]:
        # La sesión queda almacenada en st.session_state, que persiste
        # entre las re-ejecuciones del script.
        st.session_state.autenticado = True
        st.session_state.rol = perfil["rol"]
        st.session_state.nombre = perfil["nombre"]
        st.rerun()
    else:
        st.error("Usuario o contraseña incorrectos.")


def barra_lateral():
    """Muestra el perfil activo y el botón de cierre de sesión."""
    st.sidebar.title("Panel de Control")
    st.sidebar.success("Perfil: " + st.session_state.rol)
    st.sidebar.caption(st.session_state.nombre)
    st.sidebar.divider()
    if st.sidebar.button("Cerrar sesión"):
        st.session_state.autenticado = False
        st.session_state.rol = None
        st.rerun()


def main():
    iniciar_estado()

    # Navegación condicional: sin sesión válida solo existe el login.
    if not st.session_state.autenticado:
        pantalla_login()
        return

    barra_lateral()

    # Cada perfil accede únicamente a su propio módulo.
    if st.session_state.rol == "Guardia":
        guardia.vista()
    elif st.session_state.rol == "Conductor":
        conductor.vista()
    else:
        admin.vista()


if __name__ == "__main__":
    main()
