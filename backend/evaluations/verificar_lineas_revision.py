"""Reprocesa copias locales y compara la extracción con un commit anterior.

No conecta Drive, no llama modelos y no escribe en las carpetas fuente.
Ejemplo (desde la raíz):
FlucitoEnv/Scripts/python backend/evaluations/verificar_lineas_revision.py --fuente RUTA --salida backend/datos/laboratorio_sae/revision_lineas.json
"""
from __future__ import annotations
import argparse
from collections import Counter
import hashlib
import io
import json
import logging
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import zipfile


def huellas(carpeta):
    return {str(p.relative_to(carpeta)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in carpeta.rglob("*") if p.is_file() and p.suffix.lower() in {".xml", ".txt", ".pdf"}}


def worker(args):
    sys.path.insert(0, str(args.backend))
    os.environ["DATABASE_URL"] = "sqlite:///:memory:"
    os.environ["ALMACEN_CARPETA_DATOS"] = str(args.salida.parent / "reportes")
    os.environ["CATALOGO_SAE_PATH"] = str(Path(__file__).resolve().parents[1] / "datos/catalogo_sae.json")
    import pandas as pd
    from app.services.almacen import excel, resumen
    from app.services.almacen.fuentes.sincronizador import inspeccionar_pendientes_carpeta
    from app.services.contexto_decisiones import contexto
    resumen.registrar_reporte_en_bd = lambda *a, **kw: None
    logging.disable(logging.CRITICAL)
    salida = {"carpetas": [], "archivos": {}, "errores": []}
    excel.CARPETA_DATOS = args.salida.parent / "reportes"
    excel.CARPETA_DATOS.mkdir(parents=True, exist_ok=True)
    for numero, carpeta in enumerate(sorted({p.parent for p in args.fuente.rglob("*.xml")})):
        destino = excel.CARPETA_DATOS / str(numero)
        destino.mkdir()
        for archivo in carpeta.iterdir():
            if archivo.suffix.lower() in {".xml", ".pdf", ".txt"} and not archivo.name.upper().startswith(("ENTRADAS_ALMACEN", "BASE_ENTRADAS_ALMACEN")):
                shutil.copy2(archivo, destino / archivo.name)
        token = contexto.set({"session_id": "evaluacion-" + str(numero), "usuario_id": None})
        try:
            pendientes = inspeccionar_pendientes_carpeta(sorted(destino.glob("*.xml")), destino)
            dfs, metas = [], {}
            for xml in sorted(destino.glob("*.xml")):
                try:
                    df = excel.procesar_xml(str(xml), str(destino))
                    valores = df[["Clave Artículo", "Línea", "PRECIO COMPRA", "PUBLICO", "MINIMO", "MOSTRADOR", "MAYOREO", "DISTRIBUIDOR"]]
                    filas = json.loads(valores.to_json(orient="records", force_ascii=False))
                    salida["archivos"][str((carpeta / xml.name).relative_to(args.fuente))] = filas
                    dfs.append(df)
                    metas.update(df.attrs.get("meta_por_clave", {}))
                    objetivo = next((p for p in pendientes.get("productos_sin_linea", []) if p["clave_articulo"] == "BW-SAF4000DME"), None)
                    if objetivo and "BW-SAF4000DME" in set(df["Clave Artículo"]):
                        # Confirmación simulada y explícita solo en esta copia de prueba.
                        grupo = objetivo["sugerencias"][0]
                        ref = grupo["referencias"][0]
                        ensayo = excel.procesar_xml(str(xml), str(destino), factores_elegidos={"MYPC": "YPC"},
                            decisiones_lineas={"BW-SAF4000DME": {"linea": grupo["linea"], "referencia": ref["cve_art"], "confirmada": True}})
                        item = ensayo[ensayo["Clave Artículo"] == "BW-SAF4000DME"].iloc[0]
                        assert item["Línea"] == "YPC" and item["PRECIO COMPRA"] == 443.716 and item["PUBLICO"] > 0
                        excel.guardar_en_base_acumulada(ensayo, str(destino), limpiar_previos=True, prefijo="CASO_YPC_REFERENCIA")
                        salida["caso_ypc"] = {"clave": item["Clave Artículo"], "linea": item["Línea"],
                            "precio_compra": item["PRECIO COMPRA"], "publico": item["PUBLICO"],
                            "trazabilidad": ensayo.attrs["meta_por_clave"]["BW-SAF4000DME"]}
                except Exception as exc:
                    salida["errores"].append({"archivo": xml.name, "error": str(exc)})
            combinado = pd.concat(dfs, ignore_index=True)
            combinado.attrs["meta_por_clave"] = metas
            ruta = excel.guardar_en_base_acumulada(combinado, str(destino), limpiar_previos=True)
            from app.services.revision_reportes import revision_actual
            revision = revision_actual(ruta, "evaluacion-" + str(numero), None)
            salida["carpetas"].append({"carpeta": str(carpeta.relative_to(args.fuente)),
                "xml": len(dfs), "filas": len(combinado),
                "lineas_pendientes": pendientes.get("productos_sin_linea", []),
                "factores_pendientes": pendientes["lineas_sin_factor"], "rollos_pendientes": pendientes["rollos_pendientes"],
                "revision": revision,
                "txt": (destino / "BASE_ENTRADAS_ALMACEN_COMAS.txt").exists()})
        finally:
            contexto.reset(token)
    args.salida.write_text(json.dumps(salida, ensure_ascii=False, indent=2), encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fuente", type=Path, required=True)
    parser.add_argument("--salida", type=Path, required=True)
    parser.add_argument("--base", default="dd87b2b")
    parser.add_argument("--worker", action="store_true")
    parser.add_argument("--backend", type=Path)
    args = parser.parse_args()
    args.fuente = args.fuente.resolve()
    args.salida = args.salida.resolve()
    if args.worker:
        return worker(args)
    repo = Path(__file__).resolve().parents[2]
    antes = huellas(args.fuente)
    args.salida.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="flucito-lineas-") as temporal:
        raiz = Path(temporal)
        archivo = subprocess.run(["git", "archive", "--format=zip", args.base, "backend/app"], cwd=repo, check=True, capture_output=True).stdout
        with zipfile.ZipFile(io.BytesIO(archivo)) as z:
            z.extractall(raiz / "base")
        resultados = []
        for nombre, backend in (("base", raiz / "base/backend"), ("actual", repo / "backend")):
            carpeta = raiz / nombre / "evaluacion"
            carpeta.mkdir(parents=True, exist_ok=True)
            destino = carpeta / "resultado.json"
            subprocess.run([sys.executable, str(Path(__file__).resolve()), "--worker", "--fuente", str(args.fuente),
                "--salida", str(destino), "--backend", str(backend)], check=True, cwd=repo, capture_output=True)
            resultados.append(json.loads(destino.read_text(encoding="utf-8")))
        base, actual = resultados
        diferencias, regresiones = [], []
        for archivo, filas in actual["archivos"].items():
            anterior = {f["Clave Artículo"]: f for f in base["archivos"].get(archivo, [])}
            if set(anterior) != {f["Clave Artículo"] for f in filas}:
                regresiones.append({"archivo": archivo, "motivo": "Claves distintas"})
            for fila in filas:
                previa = anterior.get(fila["Clave Artículo"])
                if previa != fila:
                    diferencias.append({"archivo": archivo, "antes": previa, "despues": fila})
                    if previa and any(previa[c] != fila[c] for c in ("Clave Artículo", "Línea", "PRECIO COMPRA")):
                        regresiones.append(diferencias[-1])
                    elif previa and not (not fila["Línea"] and all(fila[p] is None and previa[p] in (None, 0) for p in ("PUBLICO", "MINIMO", "MOSTRADOR", "MAYOREO", "DISTRIBUIDOR"))):
                        regresiones.append(diferencias[-1])
        pendientes = [p for c in actual["carpetas"] for p in c["lineas_pendientes"]]
        resumen = {"commit_base": args.base, "carpetas": len(actual["carpetas"]), "xml": len(actual["archivos"]),
            "filas_xml": sum(len(f) for f in actual["archivos"].values()), "errores": actual["errores"],
            "regresiones_clave_linea_compra": regresiones, "filas_con_cambios": len(diferencias),
            "productos_pendientes_por_carpeta": len(pendientes),
            "carpetas_con_linea_pendiente": sum(bool(c["lineas_pendientes"]) for c in actual["carpetas"]),
            "productos_con_referencias": sum(bool(p["sugerencias"]) for p in pendientes),
            "estados_apoyo_pendientes": dict(Counter("fallo" if "No se pudo leer" in p.get("explicacion", "") else "ausente" if "No se encontró un documento" in p.get("explicacion", "") else "leido" for p in pendientes)),
            "fuentes_sin_cambios": antes == huellas(args.fuente)}
        resumen["caso_ypc_confirmado"] = actual.get("caso_ypc", {})
        final = {"resumen": resumen, "diferencias": diferencias, "actual": actual}
        args.salida.write_text(json.dumps(final, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps(resumen, ensure_ascii=False, indent=2))
        if regresiones or actual["errores"] or not resumen["fuentes_sin_cambios"]:
            raise SystemExit(1)


if __name__ == "__main__":
    main()
