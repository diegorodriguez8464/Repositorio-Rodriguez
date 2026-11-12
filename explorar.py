# ============================================================
# explorar.py: muestra la estructura de las tablas de Supabase.
# Utilitario de apoyo, no forma parte de la aplicación.
# Ejecutar con:  python explorar.py
# ============================================================

import toml
from supabase import create_client

secretos = toml.load(".streamlit/secrets.toml")["supabase"]
supabase = create_client(secretos["url"], secretos["key"])

tablas = ["conductores", "vehiculos", "autorizaciones", "reportes_estado"]

for tabla in tablas:
    try:
        respuesta = supabase.table(tabla).select("*").limit(2).execute()
        datos = respuesta.data
        print("\n=== " + tabla + " (" + str(len(datos)) + " filas de muestra) ===")
        if datos:
            for columna, valor in datos[0].items():
                print("  " + columna + ": " + str(valor))
        else:
            print("  (tabla vacia)")
    except Exception as e:
        print("\n=== " + tabla + " ===")
        print("  ERROR: " + str(e))
