"""Acceso e intención de las conversaciones dedicadas a Aspel SAE."""

import re

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.core import database
from app.models.conversacion import Conversacion
from app.models.usuario import Usuario

CHAT_SAE_BLOQUEADO = "Ya no cuentas con acceso a este chat. Pide acceso a administración para volver a usar Aspel SAE."
ABRIR_CHAT_SAE = "Para consultar Aspel SAE, abre una conversación de SAE."
PREFIJO_CHAT_SAE = "sae-"
TITULO_CHAT_SAE = "Chat de Aspel SAE"


def autorizar_chat_sae(db: Session, conversacion: Conversacion | None, usuario_id: int | None) -> None:
    if conversacion is None or conversacion.tipo != "sae" or usuario_id is None or conversacion.usuario_id != usuario_id:
        raise HTTPException(403, "No tienes acceso a esta conversación de Aspel SAE.")
    usuario = db.get(Usuario, usuario_id, populate_existing=True)
    if usuario is None or not usuario.activo or not usuario.acceso_sae:
        raise HTTPException(403, CHAT_SAE_BLOQUEADO)


def verificar_permiso_chat_sae(session_id: str, usuario_id: int | None) -> None:
    with database.SessionLocal() as db:
        autorizar_chat_sae(db, db.get(Conversacion, session_id), usuario_id)


def solicita_consulta_sae(mensaje: str) -> bool:
    # El catálogo de artículos y los documentos de Drive siguen siendo fuentes del chat cotidiano.
    consulta = mensaje.casefold()
    if re.search(r"(?:\bcat[aá]logo\b.*\bsae\b|\bdrive\b|\bentradas? (?:de|al) (?:almac[eé]n|inventario)\b)", consulta):
        return False
    if re.search(r"\baspel sae\b|\b(?:respaldo|base de datos) (?:de[l]? )?(?:aspel |del sistema )?sae\b|\b(?:en|desde|seg[uú]n|del|de) sae\b", consulta):
        return True
    return bool(re.search(r"\b(?:compras?|proveedores|gastamos|facturaci[oó]n|facturamos|facturas? emitidas?|ventas|devoluciones|existencias?|bajo m[ií]nimo)\b", consulta) and re.search(
        r"\b(?:cu[aá]nt[oa]s?|cu[aá]l(?:es)?|totales?|importes?|resumen|ranking|principales|gastamos|tendencia|m[aá]s|muestra|consulta|lista)\b", consulta
    ))
