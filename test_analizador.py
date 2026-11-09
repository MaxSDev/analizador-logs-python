"""Pruebas independientes de los archivos de ejemplo del usuario."""

import builtins
import contextlib
import io
from pathlib import Path
import tempfile
import unittest
from unittest.mock import MagicMock, patch

import analizador


class PruebasAnalizador(unittest.TestCase):
    def test_etiquetas_en_mensaje_no_son_severidad(self):
        for etiqueta in ("INFO", "WARNING", "ERROR", "DEBUG"):
            linea = f"2025-06-10 El usuario escribió [{etiqueta}] en un comentario"
            with self.subTest(etiqueta=etiqueta):
                nivel, motivos = analizador.analizar_linea(linea)
                self.assertIsNone(nivel)
                self.assertEqual(motivos, ["severidad ausente o sin corchetes válidos"])

    def test_archivos_adicionales(self):
        for nombre, lineas, eventos, niveles, malformadas in (
            ("logs_correctos2.log", 10, 10, {"INFO": 4, "WARNING": 3, "ERROR": 3}, 0),
            ("logs_errores2.log", 16, 15, {"INFO": 5, "WARNING": 3, "ERROR": 4}, 12),
        ):
            with self.subTest(archivo=nombre):
                resultado = analizador.analizar_archivo(Path(__file__).parent / nombre)
                self.assertEqual(resultado["lineas"], lineas)
                self.assertEqual(resultado["eventos"], eventos)
                self.assertEqual(resultado["severidades"], niveles)
                self.assertEqual(len(resultado["malformadas"]), malformadas)

    def test_archivos_del_usuario(self):
        carpeta = Path(__file__).parent
        for nombre, lineas, eventos, niveles, malformadas in (
            ("logs_correctos.txt", 5, 5, {"INFO": 3, "WARNING": 1, "ERROR": 1}, []),
            ("logs_errores.txt", 10, 9, {"INFO": 3, "WARNING": 2, "ERROR": 2}, [2, 3, 4, 5, 6, 8, 9]),
        ):
            with self.subTest(archivo=nombre):
                resultado = analizador.analizar_archivo(carpeta / nombre)
                self.assertEqual(resultado["lineas"], lineas)
                self.assertEqual(resultado["eventos"], eventos)
                self.assertEqual(resultado["severidades"], niveles)
                self.assertEqual([n for n, _ in resultado["malformadas"]], malformadas)

    def test_severidad_antes_de_fecha(self):
        for linea, nivel, motivo in (
            ("[INFO] 2024-02-29 Inicio", "INFO", None),
            ("  [WARNING] 2026-11-08 23:59:59 Aviso  ", "WARNING", None),
            ("[ERROR] 2025-02-30 Fallo", "ERROR", "fecha"),
            ("[INFO] 2026-11-08", "INFO", "mensaje"),
            ("[INFO] 2026-11-08 12:30:00", "INFO", "mensaje"),
            ("[ERROR] 2026-11-08 25:00:00 Fallo", "ERROR", "fecha"),
            ("[WARNING] Sin fecha", "WARNING", "fecha"),
            ("[DEBUG] 2026-11-08 Detalle", None, "severidad"),
        ):
            with self.subTest(linea=linea):
                obtenido, motivos = analizador.analizar_linea(linea)
                self.assertEqual(obtenido, nivel)
                if motivo is None:
                    self.assertEqual(motivos, [])
                else:
                    self.assertIn(motivo, " ".join(motivos))

    def test_lineas_validas(self):
        for linea in (
            "[INFO] 2024-02-29 Inicio",
            "[WARNING] 2026-11-08 23:59:59 Servicio lento",
            "  [ERROR] 2026-11-08 Fallo  ",
        ):
            with self.subTest(linea=linea):
                nivel, motivos = analizador.analizar_linea(linea)
                self.assertIn(nivel, ("INFO", "WARNING", "ERROR"))
                self.assertEqual(motivos, [])

    def test_lineas_invalidas(self):
        casos = (
            ("[INFO] 2025-02-30 Inicio", "INFO", "fecha"),
            ("[INFO] 2025-2-03 Inicio", "INFO", "fecha"),
            ("[ERROR] 2026-11-08 25:00:00 Fallo", "ERROR", "fecha"),
            ("[WARNING] Sin fecha", "WARNING", "fecha"),
            ("[DEBUG] 2026-11-08 Detalle", None, "severidad"),
            ("2026-11-08 Inicio", None, "severidad"),
            ("[INFO] 2026-11-08   ", "INFO", "mensaje"),
            ("", None, "vacía"),
            ("   ", None, "vacía"),
        )
        for linea, esperado, motivo in casos:
            with self.subTest(linea=linea):
                nivel, motivos = analizador.analizar_linea(linea)
                self.assertEqual(nivel, esperado)
                self.assertIn(motivo, " ".join(motivos))

    def test_contadores_y_numeros_de_linea(self):
        with tempfile.TemporaryDirectory() as carpeta:
            ruta = Path(carpeta) / "prueba.txt"
            ruta.write_text(
                "[INFO] 2024-02-29 Inicio\n"
                "\n"
                "[ERROR]\n"
                "[DEBUG] 2026-11-08 Detalle\n"
                "[WARNING] 2026-11-08 Aviso\n", encoding="utf-8"
            )
            resultado = analizador.analizar_archivo(ruta)
        self.assertEqual(resultado["lineas"], 5)
        self.assertEqual(resultado["eventos"], 4)
        self.assertEqual(resultado["severidades"], {"INFO": 1, "WARNING": 1, "ERROR": 1})
        self.assertEqual([numero for numero, _ in resultado["malformadas"]], [2, 3, 4])
        self.assertGreaterEqual(len(resultado["malformadas"][1][1]), 2)

    def test_archivo_vacio(self):
        with tempfile.TemporaryDirectory() as carpeta:
            ruta = Path(carpeta) / "vacio.txt"
            ruta.touch()
            resultado = analizador.analizar_archivo(ruta)
        self.assertEqual(resultado["lineas"], 0)
        self.assertEqual(resultado["eventos"], 0)
        self.assertEqual(resultado["malformadas"], [])

    def test_archivo_inexistente(self):
        with tempfile.TemporaryDirectory() as carpeta:
            with contextlib.redirect_stderr(io.StringIO()) as salida:
                codigo = analizador.main([str(Path(carpeta) / "no_existe.txt")])
        self.assertEqual(codigo, 1)
        self.assertIn("no existe", salida.getvalue())

    def test_codificacion_invalida(self):
        with tempfile.TemporaryDirectory() as carpeta:
            ruta = Path(carpeta) / "ilegible.txt"
            ruta.write_bytes(b"\xff\xfe\xfa")
            with contextlib.redirect_stderr(io.StringIO()) as salida:
                codigo = analizador.main([str(ruta)])
        self.assertEqual(codigo, 1)
        self.assertIn("UTF-8", salida.getvalue())

    def test_permiso_denegado_simulado(self):
        with patch("analizador.analizar_archivo", side_effect=PermissionError):
            with contextlib.redirect_stderr(io.StringIO()) as salida:
                codigo = analizador.main(["protegido.txt"])
        self.assertEqual(codigo, 1)
        self.assertIn("permiso", salida.getvalue())

    def test_ruta_interactiva(self):
        with tempfile.TemporaryDirectory() as carpeta:
            ruta = Path(carpeta) / "con espacios.txt"
            ruta.write_text("[INFO] 2026-11-08 Inicio\n", encoding="utf-8-sig")
            with patch("analizador.seleccionar_archivo", return_value=None), patch("builtins.input", return_value=str(ruta)):
                with contextlib.redirect_stdout(io.StringIO()) as salida:
                    codigo = analizador.main([])
        self.assertEqual(codigo, 0)
        self.assertRegex(salida.getvalue(), r"INFO\s+1")

    def test_fin_de_entrada(self):
        with patch("analizador.seleccionar_archivo", return_value=None), patch("builtins.input", side_effect=EOFError):
            with contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(analizador.main([]), 1)

    def test_argumento_no_abre_selector_ni_pide_entrada(self):
        with patch("analizador.seleccionar_archivo", side_effect=AssertionError("Abrió selector")):
            with patch("builtins.input", side_effect=AssertionError("Pidió entrada")):
                with contextlib.redirect_stdout(io.StringIO()) as salida:
                    self.assertEqual(analizador.main([str(Path(__file__).parent / "logs_correctos.txt")]), 0)
        self.assertIn("logs_correctos.txt", salida.getvalue())
        self.assertIn("Sin inconsistencias", salida.getvalue())

    def test_seleccion_txt_y_log(self):
        with tempfile.TemporaryDirectory() as carpeta:
            for extension in (".txt", ".log"):
                ruta = Path(carpeta) / ("prueba" + extension)
                ruta.write_text("[INFO] 2024-02-29 Inicio\n", encoding="utf-8")
                with patch("analizador.seleccionar_archivo", return_value=str(ruta)):
                    with patch("builtins.input", side_effect=AssertionError("Pidió entrada")):
                        with contextlib.redirect_stdout(io.StringIO()) as salida:
                            self.assertEqual(analizador.main([]), 0)
                self.assertIn(ruta.name, salida.getvalue())
                self.assertRegex(salida.getvalue(), r"INFO\s+1")

    def test_cancelacion(self):
        with patch("analizador.seleccionar_archivo", return_value=""):
            with patch("builtins.input", side_effect=AssertionError("Pidió entrada")):
                with contextlib.redirect_stdout(io.StringIO()) as salida:
                    self.assertEqual(analizador.main([]), 0)
        self.assertIn("Selección cancelada", salida.getvalue())

    def test_dialogo_y_cierre_auxiliar_simulados(self):
        for seleccion in ("prueba.log", ""):
            tkinter = MagicMock()
            tkinter.TclError = RuntimeError
            tkinter.filedialog.askopenfilename.return_value = seleccion
            with patch.dict("sys.modules", {"tkinter": tkinter}):
                self.assertEqual(analizador.seleccionar_archivo(), seleccion)
            tkinter.Tk.return_value.withdraw.assert_called_once()
            tkinter.Tk.return_value.destroy.assert_called_once()
            filtros = tkinter.filedialog.askopenfilename.call_args.kwargs["filetypes"]
            self.assertEqual(filtros[0], ("Archivos de logs (.txt y .log)", ("*.txt", "*.log")))
            self.assertIn(("Todos los archivos", "*"), filtros)

    def test_tkinter_no_disponible_simulado(self):
        with patch.dict("sys.modules", {"tkinter": None}):
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertIsNone(analizador.seleccionar_archivo())

    def test_argumento_no_importa_tkinter(self):
        importar = builtins.__import__

        def importar_sin_tkinter(nombre, *args, **kwargs):
            if nombre == "tkinter" or nombre.startswith("tkinter."):
                raise AssertionError("No debe intentar importar tkinter")
            return importar(nombre, *args, **kwargs)

        with patch("builtins.__import__", side_effect=importar_sin_tkinter):
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(analizador.main([str(Path(__file__).parent / "logs_correctos2.log")]), 0)

    def test_consola_sin_tkinter(self):
        ruta = str(Path(__file__).parent / "logs_correctos.txt")
        with patch.dict("sys.modules", {"tkinter": None}):
            with patch("builtins.input", return_value=ruta):
                with contextlib.redirect_stdout(io.StringIO()) as salida:
                    self.assertEqual(analizador.main([]), 0)
        self.assertIn("selector no está disponible", salida.getvalue())
        self.assertIn("logs_correctos.txt", salida.getvalue())

    def test_consola_sin_entorno_grafico_simulado(self):
        tkinter = MagicMock()
        tkinter.TclError = RuntimeError
        tkinter.Tk.side_effect = RuntimeError("Sin pantalla")
        ruta = str(Path(__file__).parent / "logs_correctos2.log")
        with patch.dict("sys.modules", {"tkinter": tkinter}):
            with patch("builtins.input", return_value=ruta):
                with contextlib.redirect_stdout(io.StringIO()) as salida:
                    self.assertEqual(analizador.main([]), 0)
        self.assertIn("No se pudo abrir el selector", salida.getvalue())
        self.assertIn("logs_correctos2.log", salida.getvalue())

    def test_fallo_ventana_simulado(self):
        for falla_en in ("inicio", "dialogo"):
            tkinter = MagicMock()
            tkinter.TclError = RuntimeError
            if falla_en == "inicio":
                tkinter.Tk.side_effect = RuntimeError("Sin pantalla")
            else:
                tkinter.filedialog.askopenfilename.side_effect = RuntimeError("No abre")
            with patch.dict("sys.modules", {"tkinter": tkinter}):
                with contextlib.redirect_stdout(io.StringIO()):
                    self.assertIsNone(analizador.seleccionar_archivo())
            if falla_en == "dialogo":
                tkinter.Tk.return_value.destroy.assert_called_once()

    def test_presentacion_no_modifica_resultados(self):
        resultado = analizador.analizar_archivo(Path(__file__).parent / "logs_errores.txt")
        import copy
        anterior = copy.deepcopy(resultado)
        with contextlib.redirect_stdout(io.StringIO()) as salida:
            analizador.mostrar_resumen(resultado, "logs_errores.txt")
        self.assertEqual(resultado, anterior)
        for texto in ("ANALIZADOR DE LOGS", "RESUMEN GENERAL", "CLASIFICACIÓN", "LÍNEAS MALFORMADAS", "logs_errores.txt"):
            self.assertIn(texto, salida.getvalue())


if __name__ == "__main__":
    unittest.main()
