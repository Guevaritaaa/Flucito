"""Inicialización de tablas, usuarios base, factores comerciales y Catálogo Maestro de SAE."""

from __future__ import annotations

import json
import logging
from typing import Any

from sqlalchemy import func, insert, select
from sqlalchemy.orm import Session

import app.models  # noqa: F401 - Registra todos los modelos en Base.metadata
from app.core.config import settings
from app.core.database import Base, SessionLocal, engine
from app.core.security import hashear_password
from app.models.almacen import FactorLinea
from app.models.catalogo_sae import (
    SaeArticulo,
    SaeClaveAlterna,
    SaeHistorialCompra,
    SaeLinea,
    SaeProveedor,
)
from app.models.usuario import Usuario
from app.services.almacen.catalogo_sae import obtener_ruta_catalogo_sae
from app.services.almacen.factores import (
    CATALOGO_LINEAS_BASE,
    RUTA_FACTORES_PERSONALIZADOS,
)

logger = logging.getLogger(__name__)

_BATCH_SIZE = 2500


def _sembrar_usuarios_iniciales(db: Session) -> int:
    """Crea las cuentas iniciales de administrador y operador si no existen."""
    creados = 0
    usuarios_semilla = (
        {
            "username": settings.admin_initial_username.strip().lower(),
            "nombre_completo": settings.admin_initial_name.strip(),
            "password": settings.admin_initial_password,
            "rol": "admin",
        },
        {
            "username": settings.operador_initial_username.strip().lower(),
            "nombre_completo": settings.operador_initial_name.strip(),
            "password": settings.operador_initial_password,
            "rol": "operador",
        },
    )

    for info in usuarios_semilla:
        username = info["username"]
        if not username:
            continue
        existente = db.scalar(select(Usuario).where(Usuario.username == username))
        if existente is not None:
            continue
        db.add(
            Usuario(
                username=username,
                nombre_completo=info["nombre_completo"],
                password_hash=hashear_password(info["password"]),
                rol=info["rol"],
                activo=True,
            )
        )
        creados += 1

    if creados:
        db.commit()
    return creados


def _sembrar_catalogo_sae(db: Session, *, cargar_articulos: bool = True) -> dict[str, int]:
    """Carga el catálogo maestro de SAE desde `catalogo_sae.json` si las tablas están vacías."""
    resumen = {
        "lineas": 0,
        "proveedores": 0,
        "articulos": 0,
        "claves_alternas": 0,
        "historial_compras": 0,
    }

    total_lineas = db.scalar(select(func.count()).select_from(SaeLinea)) or 0
    total_articulos = db.scalar(select(func.count()).select_from(SaeArticulo)) or 0
    if total_lineas > 0 and (not cargar_articulos or total_articulos > 0):
        return resumen

    ruta_json = obtener_ruta_catalogo_sae()
    if ruta_json is None or not ruta_json.is_file():
        logger.warning("No se encontró catalogo_sae.json para inicializar las tablas SAE.")
        return resumen

    try:
        raw: dict[str, Any] = json.loads(ruta_json.read_text(encoding="utf-8"))
    except Exception as exc:
        logger.error("Error leyendo catalogo_sae.json en seed: %s", exc)
        return resumen

    if total_lineas == 0:
        lineas_raw: dict[str, str] = dict(raw.get("lineas") or {})
        for cod_base, info_base in CATALOGO_LINEAS_BASE.items():
            cod_limpio = str(cod_base).strip().upper()[:32]
            if cod_limpio and cod_limpio not in lineas_raw:
                lineas_raw[cod_limpio] = str(info_base.get("descripcion") or "")
        filas_lineas = [
            {
                "clave_linea": str(k).strip().upper()[:32],
                "descripcion": str(v or "").strip()[:255],
                "estatus": "A",
            }
            for k, v in lineas_raw.items()
            if str(k).strip()
        ]
        if filas_lineas:
            db.execute(insert(SaeLinea), filas_lineas)
            resumen["lineas"] = len(filas_lineas)

    total_proveedores = db.scalar(select(func.count()).select_from(SaeProveedor)) or 0
    if total_proveedores == 0:
        proveedores_raw: dict[str, dict[str, Any]] = raw.get("proveedores") or {}
        filas_proveedores = [
            {
                "clave_proveedor": str(v.get("clave") or k).strip()[:32],
                "nombre": str(v.get("nombre") or "").strip()[:255],
                "rfc": str(v.get("rfc") or "").strip().upper()[:32],
                "estatus": "A",
            }
            for k, v in proveedores_raw.items()
            if str(v.get("clave") or k).strip()
        ]
        if filas_proveedores:
            db.execute(insert(SaeProveedor), filas_proveedores)
            resumen["proveedores"] = len(filas_proveedores)

    if cargar_articulos and total_articulos == 0:
        articulos_raw: dict[str, dict[str, Any]] = raw.get("articulos") or {}
        vistos: set[str] = set()
        lote: list[dict[str, Any]] = []
        insertados = 0
        for cve_key, datos in articulos_raw.items():
            cve_oficial = str(datos.get("cve_art") or cve_key).strip().upper()[:64]
            if not cve_oficial or cve_oficial in vistos:
                continue
            vistos.add(cve_oficial)
            lote.append(
                {
                    "clave_articulo": cve_oficial,
                    "descripcion": str(datos.get("descr") or "").strip()[:500],
                    "clave_linea": str(datos.get("linea") or "").strip().upper()[:32] or None,
                    "unidad_entrada": str(datos.get("uni_med") or "PZ").strip()[:32] or "PZ",
                    "cve_sat": str(datos.get("cve_sat") or "").strip()[:32],
                    "cve_unidad": str(datos.get("cve_unidad") or "").strip()[:32],
                    "ultimo_costo": float(datos.get("ult_costo") or 0.0),
                    "estatus": "A",
                }
            )
            if len(lote) >= _BATCH_SIZE:
                db.execute(insert(SaeArticulo), lote)
                insertados += len(lote)
                lote.clear()
        if lote:
            db.execute(insert(SaeArticulo), lote)
            insertados += len(lote)
        resumen["articulos"] = insertados

    total_claves_alt = db.scalar(select(func.count()).select_from(SaeClaveAlterna)) or 0
    if cargar_articulos and total_claves_alt == 0:
        claves_alt_raw: dict[str, Any] = raw.get("claves_alternas") or {}
        filas_alt = []
        for cve_alt, info_alt in claves_alt_raw.items():
            alt_upper = str(cve_alt).strip().upper()[:64]
            if not alt_upper:
                continue
            if isinstance(info_alt, dict):
                cve_art_dest = str(info_alt.get("cve_art") or "").strip().upper()[:64]
                prov_alt = str(info_alt.get("proveedor") or "").strip()[:32] or None
            else:
                cve_art_dest = str(info_alt or "").strip().upper()[:64]
                prov_alt = None
            if cve_art_dest:
                filas_alt.append(
                    {
                        "clave_alterna": alt_upper,
                        "clave_articulo": cve_art_dest,
                        "clave_proveedor": prov_alt,
                    }
                )
        if filas_alt:
            db.execute(insert(SaeClaveAlterna), filas_alt)
            resumen["claves_alternas"] = len(filas_alt)

    total_historial = db.scalar(select(func.count()).select_from(SaeHistorialCompra)) or 0
    if total_historial == 0:
        compras_raw: dict[str, dict[str, Any]] = raw.get("compras_por_proveedor") or {}
        filas_hist = []
        for cve_prov, datos_comp in compras_raw.items():
            prov_key = str(cve_prov).strip()[:32]
            if not prov_key or not isinstance(datos_comp, dict):
                continue
            filas_hist.append(
                {
                    "clave_proveedor": prov_key,
                    "lineas_compradas_json": json.dumps(
                        datos_comp.get("lineas_compradas") or {},
                        ensure_ascii=False,
                    ),
                    "articulos_comprados_json": json.dumps(
                        datos_comp.get("articulos_comprados") or [],
                        ensure_ascii=False,
                    ),
                }
            )
        if filas_hist:
            db.execute(insert(SaeHistorialCompra), filas_hist)
            resumen["historial_compras"] = len(filas_hist)

    db.commit()
    return resumen


def _sembrar_factores_linea(db: Session) -> int:
    """Inicializa la tabla `factores_linea` con el catálogo base y los personalizados."""
    total_actual = db.scalar(select(func.count()).select_from(FactorLinea)) or 0
    if total_actual > 0:
        return 0

    personalizados: dict[str, str] = {}
    if RUTA_FACTORES_PERSONALIZADOS.is_file():
        try:
            datos = json.loads(RUTA_FACTORES_PERSONALIZADOS.read_text(encoding="utf-8"))
            if isinstance(datos, dict):
                personalizados = {
                    str(k).strip().upper(): str(v).strip().upper()
                    for k, v in datos.items()
                    if k and v
                }
        except Exception as exc:
            logger.warning("No se pudo leer FACTORES_PERSONALIZADOS.json en seed: %s", exc)

    filas: dict[str, dict[str, Any]] = {}
    for linea, info in CATALOGO_LINEAS_BASE.items():
        factor = info.get("factor")
        if factor:
            clave = linea.strip().upper()[:64]
            filas[clave] = {
                "clave_linea": clave,
                "nombre_factor": str(factor).strip().upper()[:64],
                "es_personalizado": False,
                "actualizado_por_id": None,
            }

    for linea, factor in personalizados.items():
        clave = linea.strip().upper()[:64]
        filas[clave] = {
            "clave_linea": clave,
            "nombre_factor": factor[:64],
            "es_personalizado": True,
            "actualizado_por_id": None,
        }

    if filas:
        db.execute(insert(FactorLinea), list(filas.values()))
        db.commit()
    return len(filas)


def inicializar_base_de_datos(
    db: Session | None = None,
    *,
    cargar_articulos_sae: bool = True,
) -> dict[str, Any]:
    """Crea tablas si no existen y carga usuarios iniciales, catálogo SAE y factores."""
    cerrar_al_final = False
    if db is None:
        Base.metadata.create_all(bind=engine)
        db = SessionLocal()
        cerrar_al_final = True
    else:
        bind = db.get_bind()
        Base.metadata.create_all(bind=bind)

    try:
        usuarios_creados = _sembrar_usuarios_iniciales(db)
        sae_resumen = _sembrar_catalogo_sae(db, cargar_articulos=cargar_articulos_sae)
        factores_creados = _sembrar_factores_linea(db)
        return {
            "usuarios_creados": usuarios_creados,
            "factores_creados": factores_creados,
            "sae": sae_resumen,
        }
    finally:
        if cerrar_al_final:
            db.close()
