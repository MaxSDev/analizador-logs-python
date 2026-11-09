import argparse
from datetime import datetime
from pathlib import Path
import re
import sys


NIVELES = ("INFO", "WARNING", "ERROR")
PATRON_FECHA = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}(?: [0-9]{2}:[0-9]{2}:[0-9]{2})?")
PATRON_SEVERIDAD = re.compile(r"\[([^\[\]]*)\]")


def validar_fecha(texto):
    # Comprueba el formato exacto y la existencia de la fecha y hora.
    if not PATRON_FECHA.fullmatch(texto):
        return False
    formato = "%Y-%m-%d %H:%M:%S" if " " in texto else "%Y-%m-%d"
    try:
        datetime.strptime(texto, formato)
    except ValueError:
        return False
    return True


def separar_fecha_mensaje(texto):
    # Separa la fecha inicial y su hora opcional del mensaje restante.
    campos = texto.split(maxsplit=1)
    if not campos:
        return "", ""
    # Si comienza con palabras, falta la fecha; esas palabras son el mensaje.
    if not re.match(r"[0-9]", campos[0]):
        return "", texto
    fecha = campos[0]
    mensaje = campos[1] if len(campos) == 2 else ""
    if mensaje:
        partes = mensaje.split(maxsplit=1)
        if ":" in partes[0]:
            fecha += " " + partes[0]
            mensaje = partes[1] if len(partes) == 2 else ""
    return fecha, mensaje


def analizar_linea(linea):
    # Devuelve la severidad reconocida y todos los motivos de invalidez.
    texto = linea.strip()
    if not texto:
        return None, ["Línea vacía"]

    motivos = []
    # strip() permite espacios iniciales; match() exige la etiqueta al inicio.
    coincidencia = PATRON_SEVERIDAD.match(texto)
    nivel = None
    if coincidencia:
        etiqueta = coincidencia.group(1)
        if etiqueta in NIVELES:
            nivel = etiqueta
        else:
            motivos.append(f"severidad desconocida: [{etiqueta}]")
        fecha, mensaje = separar_fecha_mensaje(texto[coincidencia.end():].strip())
    else:
        motivos.append("severidad ausente o sin corchetes válidos")
        # Sin etiqueta, se examina la fecha inicial sin inventar un nivel.
        campos = texto.split(maxsplit=1)
        fecha = campos[0]
        mensaje = campos[1] if len(campos) == 2 else ""
        if mensaje and re.match(r"[0-9]{2}:[0-9]{2}:[0-9]{2}(?:\s|$)", mensaje):
            partes = mensaje.split(maxsplit=1)
            fecha += " " + partes[0]
            mensaje = partes[1] if len(partes) == 2 else ""

    if not fecha:
        motivos.append("fecha ausente")
    elif not validar_fecha(fecha):
        motivos.append("fecha inválida: formato incorrecto o fecha/hora inexistente")
    if not mensaje:
        motivos.append("mensaje ausente o vacío")
    return nivel, motivos


def analizar_archivo(ruta):
    # Lee línea por línea; propaga errores de lectura para tratarlos en main.
    resultado = {
        "lineas": 0,
        "eventos": 0,
        "severidades": dict.fromkeys(NIVELES, 0),
        "malformadas": [],
    }
    # utf-8-sig también admite UTF-8 sin BOM; no oculta bytes ilegibles.
    with open(ruta, encoding="utf-8-sig") as archivo:
        for numero, linea in enumerate(archivo, start=1):
            resultado["lineas"] += 1
            if linea.strip():
                resultado["eventos"] += 1
            nivel, motivos = analizar_linea(linea)
            # La severidad se conserva aunque la fecha o el mensaje fallen.
            if nivel is not None:
                resultado["severidades"][nivel] += 1
            if motivos:
                resultado["malformadas"].append((numero, motivos))
    return resultado


def mostrar_resumen(resultado, ruta):
    # Presenta los resultados sin modificar los contadores del análisis.
    separador = "-" * 64
    print("=" * 64)
    print("ANALIZADOR DE LOGS".center(64))
    print("=" * 64)
    print(f"Archivo: {Path(ruta).name}")
    print(separador)
    print("RESUMEN GENERAL")
    print(separador)
    print(f"{'Líneas leídas':<28} {resultado['lineas']:>10}")
    print(f"{'Total de eventos':<28} {resultado['eventos']:>10}")
    print(f"{'Líneas malformadas':<28} {len(resultado['malformadas']):>10}")
    if resultado["lineas"] == 0:
        print("El archivo está vacío.")
    print(separador)
    print("CLASIFICACIÓN POR SEVERIDAD")
    print(separador)
    print(f"{'Nivel':<28} {'Cantidad':>10}")
    for nivel, cantidad in resultado["severidades"].items():
        print(f"{nivel:<28} {cantidad:>10}")
    print(separador)
    print("DETALLES DE LÍNEAS MALFORMADAS")
    print(separador)
    if resultado["malformadas"]:
        print(f"{'Línea':>6}  Motivo(s)")
        for numero, motivos in resultado["malformadas"]:
            print(f"{numero:>6}  {'; '.join(motivos)}")
    else:
        print("Sin inconsistencias: no se encontraron líneas malformadas.")
    print("=" * 64)


def seleccionar_archivo():
    # Devuelve una ruta, "" al cancelar o None para usar la consola.
    # La importación local evita cargar tkinter al ejecutar con argumentos.
    try:
        import tkinter as tk
        from tkinter import filedialog
    except ImportError:
        print("El selector no está disponible. Ingresa la ruta en consola.")
        return None

    ventana = None
    try:
        ventana = tk.Tk()
        ventana.withdraw()
        return filedialog.askopenfilename(
            parent=ventana,
            title="Seleccionar archivo de logs",
            filetypes=(
                ("Archivos de logs (.txt y .log)", ("*.txt", "*.log")),
                ("Todos los archivos", "*"),
            ),
        )
    except tk.TclError:
        print("No se pudo abrir el selector. Ingresa la ruta en consola.")
        return None
    finally:
        # Se destruye la ventana oculta incluso si el diálogo falla.
        if ventana is not None:
            try:
                ventana.destroy()
            except tk.TclError:
                pass  # La ventana ya no está disponible.


def main(argumentos=None):
    # Obtiene la ruta, maneja fallos de lectura y devuelve el código de salida.
    parser = argparse.ArgumentParser(description="Analizador de archivos de logs UTF-8")
    parser.add_argument("ruta", nargs="?", help="Ruta relativa o absoluta del log UTF-8")
    opciones = parser.parse_args(argumentos)
    ruta = opciones.ruta
    if ruta is None:
        ruta = seleccionar_archivo()
        if ruta == "":
            print("Selección cancelada. No se analizó ningún archivo.")
            return 0
    if ruta is None:
        try:
            ruta = input("Ruta del archivo de logs: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nNo se recibió una ruta.", file=sys.stderr)
            return 1
    if not ruta:
        print("Error: la ruta está vacía.", file=sys.stderr)
        return 1
    try:
        resultado = analizar_archivo(ruta)
    except FileNotFoundError:
        print(f"Error: el archivo no existe: {ruta}", file=sys.stderr)
        return 1
    except PermissionError:
        print(f"Error: no hay permiso para leer: {ruta}", file=sys.stderr)
        return 1
    except UnicodeError:
        print("Error: el archivo no contiene texto UTF-8 válido.", file=sys.stderr)
        return 1
    except OSError as error:
        print(f"Error al leer el archivo: {error}", file=sys.stderr)
        return 1
    mostrar_resumen(resultado, ruta)
    return 0


if __name__ == "__main__":
    sys.exit(main())
