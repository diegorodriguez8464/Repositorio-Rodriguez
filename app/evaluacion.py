# ============================================================
# CONTROL DE ACCESO Y ESTADO VEHICULAR
# app/evaluacion.py: algoritmo de evaluación del estado del
# vehículo, reutilizado de la Evaluación N°02 y adaptado a los
# indicadores que registra la base institucional.
#
# Etapa A: Kill-Switches (fallas críticas, tienen prioridad)
# Etapa B: Índice de Salud del Vehículo (ISV) y clasificación
#
# El algoritmo no depende de Streamlit ni de Supabase, por lo
# que puede probarse de forma aislada.
# ============================================================

# ------------------------------------------------------------
# Condiciones de operación (las mismas de la Evaluación N°02)
# ------------------------------------------------------------
APTO = "Apto"
APTO_ACEPTABLES = "Apto con fallas aceptables"
APTO_CRITICAS = "Apto con fallas críticas"
NO_APTO = "No Apto"
CONDICIONES = [APTO, APTO_ACEPTABLES, APTO_CRITICAS, NO_APTO]

# ------------------------------------------------------------
# Pesos del ISV (wi). Deben sumar exactamente 1.00
# Se redistribuyeron los pesos de la Evaluación N°02 sobre los
# cuatro indicadores que registra la tabla reportes_estado.
# ------------------------------------------------------------
PESOS = {
    "frenos": 0.30,        # sistema vital: el de mayor ponderación
    "neumaticos": 0.30,    # equivale al 20% de las 4 ruedas más su margen
    "combustible": 0.20,
    "luces": 0.20,
}

NOMBRES_INDICADORES = {
    "frenos": "Sistema de frenos",
    "neumaticos": "Presión de neumáticos",
    "combustible": "Nivel de combustible",
    "luces": "Sistema de luces",
}

# Se comprueba al importar el módulo: si alguien cambia un peso y
# la suma deja de ser 1.00, el programa avisa de inmediato.
assert abs(sum(PESOS.values()) - 1.0) < 1e-9, "Los pesos del ISV deben sumar 1.00"

# ------------------------------------------------------------
# Umbrales (centralizados para no repartir números mágicos)
# ------------------------------------------------------------
COMBUSTIBLE_OPTIMO = 50.0    # %: sobre este valor, calificación 100
COMBUSTIBLE_MINIMO = 15.0    # %: bajo este valor, Kill-Switch

ISV_APTO = 90.0
ISV_ACEPTABLE = 70.0
ISV_CRITICO = 50.0


# ------------------------------------------------------------
# Calificación (ci, de 0 a 100) de cada indicador
# ------------------------------------------------------------
def calificar_frenos(frenos_ok):
    return 100 if frenos_ok else 0


def calificar_neumaticos(presion_ok):
    return 100 if presion_ok else 0


def calificar_luces(luces_ok):
    return 100 if luces_ok else 0


def calificar_combustible(porcentaje):
    # Sobre 50% la unidad está en condiciones; entre 15% y 50% a
    # media autonomía; bajo 15% no puede salir a ruta.
    if porcentaje > COMBUSTIBLE_OPTIMO:
        return 100
    if porcentaje >= COMBUSTIBLE_MINIMO:
        return 50
    return 0


def calcular_calificaciones(frenos_ok, presion_ok, luces_ok, combustible):
    """Convierte las lecturas del reporte en las calificaciones ci."""
    return {
        "frenos": calificar_frenos(frenos_ok),
        "neumaticos": calificar_neumaticos(presion_ok),
        "combustible": calificar_combustible(combustible),
        "luces": calificar_luces(luces_ok),
    }


# ------------------------------------------------------------
# ETAPA A: Kill-Switches (sistemas vitales)
# ------------------------------------------------------------
def detectar_kill_switch(frenos_ok, presion_ok, combustible):
    """Devuelve la lista de fallas críticas. Lista vacía = sin bloqueo.

    Las luces no son Kill-Switch: su falla descuenta puntos en el
    ISV, pero no impide por sí sola el movimiento de la unidad.
    """
    motivos = []

    if not frenos_ok:
        motivos.append("Falla declarada en el sistema de frenos.")

    if not presion_ok:
        motivos.append("Presión de neumáticos fuera de norma.")

    if combustible < COMBUSTIBLE_MINIMO:
        motivos.append("Nivel de combustible " + str(combustible) +
                       "% bajo el mínimo operativo (" +
                       str(COMBUSTIBLE_MINIMO) + "%).")

    return motivos


# ------------------------------------------------------------
# ETAPA B: ISV = suma(wi * ci)
# ------------------------------------------------------------
def calcular_isv(calificaciones):
    isv = sum(PESOS[indicador] * c for indicador, c in calificaciones.items())
    # Se redondea para evitar errores de coma flotante en los límites.
    return round(isv, 2)


def contar_fallas(calificaciones):
    """Cantidad de indicadores que no están al 100%."""
    return sum(1 for c in calificaciones.values() if c < 100)


def listar_fallas(calificaciones):
    return [NOMBRES_INDICADORES[k] + " (" + str(c) + "/100)"
            for k, c in calificaciones.items() if c < 100]


# ------------------------------------------------------------
# Clasificación final de la condición del vehículo
# ------------------------------------------------------------
def clasificar_condicion(isv, kill_switch, num_fallas):
    # 1) El Kill-Switch tiene prioridad sobre el ISV: una falla en
    #    un sistema vital fuerza No Apto aunque el índice sea alto.
    if kill_switch:
        return NO_APTO

    # 2) Sin bloqueo, se clasifica por rangos de ISV.
    if isv >= ISV_APTO and num_fallas == 0:
        return APTO
    if isv >= ISV_ACEPTABLE:
        return APTO_ACEPTABLES
    if isv >= ISV_CRITICO:
        return APTO_CRITICAS
    return NO_APTO


def evaluar_reporte(frenos_ok, presion_ok, luces_ok, combustible):
    """Ejecuta las dos etapas y devuelve el resultado completo."""
    motivos = detectar_kill_switch(frenos_ok, presion_ok, combustible)
    calificaciones = calcular_calificaciones(frenos_ok, presion_ok,
                                             luces_ok, combustible)
    isv = calcular_isv(calificaciones)
    num_fallas = contar_fallas(calificaciones)

    return {
        "calificaciones": calificaciones,
        "motivos_kill_switch": motivos,
        "kill_switch": len(motivos) > 0,
        "isv": isv,
        "num_fallas": num_fallas,
        "condicion": clasificar_condicion(isv, len(motivos) > 0, num_fallas),
        "fallas": listar_fallas(calificaciones),
    }


# ------------------------------------------------------------
# Puente entre la condición del algoritmo y el estado que
# almacena la tabla maestra de vehículos.
# ------------------------------------------------------------
def estado_operativo_segun_condicion(condicion):
    if condicion in (APTO, APTO_ACEPTABLES):
        return "Operativo"
    return "Requiere Mantención"
