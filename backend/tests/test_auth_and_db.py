"""Pruebas de autenticación JWT, roles de usuario, historial de conversaciones por usuario y base de datos."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
import json

from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage
import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.v1.routes import auth as auth_route
from app.api.v1.routes import chat as chat_route
from app.core import database as db_module
from app.core.config import settings
from app.core.seed import inicializar_base_de_datos
from app.main import app
from app.models.almacen import DetalleEntradaAlmacen, FactorLinea, ReporteAlmacen
from app.models.catalogo_sae import SaeArticulo, SaeLinea
from app.services.almacen.catalogo_sae import buscar_articulo_sae, cargar_catalogo_sae, limpiar_cache_catalogo_sae
from app.services.almacen.factores import cargar_factores_personalizados, guardar_factor_personalizado
from app.services.almacen.resumen import registrar_reporte_en_bd


@pytest.fixture()
def entorno_bd(monkeypatch):
    """Crea una base de datos SQLAlchemy aislada en memoria para pruebas rápidas y deterministas."""
    test_engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestSessionLocal = sessionmaker(
        autocommit=False,
        autoflush=False,
        bind=test_engine,
        expire_on_commit=False,
    )

    monkeypatch.setattr(db_module, "engine", test_engine)
    monkeypatch.setattr(db_module, "SessionLocal", TestSessionLocal)
    monkeypatch.setattr(chat_route, "engine", test_engine)
    monkeypatch.setattr(chat_route, "SessionLocal", TestSessionLocal)

    def _override_get_db():
        with TestSessionLocal() as session:
            yield session

    app.dependency_overrides[db_module.get_db] = _override_get_db
    auth_route.limpiar_intentos_login()
    with TestSessionLocal() as session:
        inicializar_base_de_datos(session, cargar_articulos_sae=False)

    client = TestClient(app)
    try:
        yield client, TestSessionLocal
    finally:
        app.dependency_overrides.clear()
        auth_route.limpiar_intentos_login()
        limpiar_cache_catalogo_sae()


def test_login_json_y_form_oauth2_exitosos(entorno_bd) -> None:
    client, _ = entorno_bd

    # 1. Login vía JSON (para frontend moderno)
    resp_json = client.post(
        "/api/v1/auth/login",
        json={
            "username": settings.admin_initial_username,
            "password": settings.admin_initial_password,
        },
    )
    assert resp_json.status_code == 200
    datos_json = resp_json.json()
    assert datos_json["token_type"] == "bearer"
    assert datos_json["access_token"]
    assert datos_json["usuario"]["username"] == settings.admin_initial_username
    assert datos_json["usuario"]["rol"] == "admin"

    # 2. Login vía x-www-form-urlencoded (botón Authorize de /docs)
    resp_form = client.post(
        "/api/v1/auth/login",
        data={
            "username": settings.operador_initial_username,
            "password": settings.operador_initial_password,
        },
    )
    assert resp_form.status_code == 200
    datos_form = resp_form.json()
    assert datos_form["usuario"]["username"] == settings.operador_initial_username
    assert datos_form["usuario"]["rol"] == "operador"

    # 3. Verificación de /api/v1/auth/me con el token
    token_admin = datos_json["access_token"]
    resp_me = client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {token_admin}"},
    )
    assert resp_me.status_code == 200
    assert resp_me.json()["username"] == settings.admin_initial_username


def test_login_credenciales_invalidas_y_acceso_sin_token(entorno_bd) -> None:
    client, _ = entorno_bd

    resp_bad = client.post(
        "/api/v1/auth/login",
        json={"username": settings.admin_initial_username, "password": "PasswordIncorrecta123"},
    )
    assert resp_bad.status_code == 401

    resp_no_token = client.get("/api/v1/auth/me")
    assert resp_no_token.status_code == 401

    resp_bad_token = client.get(
        "/api/v1/auth/me",
        headers={"Authorization": "Bearer token.falso.invalido"},
    )
    assert resp_bad_token.status_code == 401

    # Tras alcanzar 5 intentos fallidos seguidos, el 6to devuelve 429 Too Many Requests
    for _ in range(4):
        r_fail = client.post(
            "/api/v1/auth/login",
            json={"username": settings.admin_initial_username, "password": "PasswordIncorrecta123"},
        )
        assert r_fail.status_code == 401

    resp_rate_limit = client.post(
        "/api/v1/auth/login",
        json={"username": settings.admin_initial_username, "password": "PasswordIncorrecta123"},
    )
    assert resp_rate_limit.status_code == 429


def test_roles_admin_vs_operador_y_desactivacion_inmediata(entorno_bd) -> None:
    client, _ = entorno_bd

    token_admin = client.post(
        "/api/v1/auth/login",
        json={
            "username": settings.admin_initial_username,
            "password": settings.admin_initial_password,
        },
    ).json()["access_token"]

    token_operador = client.post(
        "/api/v1/auth/login",
        json={
            "username": settings.operador_initial_username,
            "password": settings.operador_initial_password,
        },
    ).json()["access_token"]

    # Operador no puede listar ni crear usuarios
    resp_op_list = client.get(
        "/api/v1/auth/usuarios",
        headers={"Authorization": f"Bearer {token_operador}"},
    )
    assert resp_op_list.status_code == 403

    # Admin puede crear un nuevo operador
    resp_crear = client.post(
        "/api/v1/auth/usuarios",
        headers={"Authorization": f"Bearer {token_admin}"},
        json={
            "username": "asesor2",
            "nombre_completo": "Segundo Asesor Almacén",
            "password": "AsesorPassword2026!",
            "rol": "operador",
        },
    )
    assert resp_crear.status_code == 201
    nuevo_id = resp_crear.json()["id"]

    # El nuevo operador inicia sesión y obtiene su token
    token_asesor2 = client.post(
        "/api/v1/auth/login",
        json={"username": "asesor2", "password": "AsesorPassword2026!"},
    ).json()["access_token"]

    assert (
        client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token_asesor2}"}).status_code
        == 200
    )

    # Admin desactiva la cuenta de asesor2
    resp_desactivar = client.patch(
        f"/api/v1/auth/usuarios/{nuevo_id}",
        headers={"Authorization": f"Bearer {token_admin}"},
        json={"activo": False},
    )
    assert resp_desactivar.status_code == 200
    assert resp_desactivar.json()["activo"] is False

    # El token ya emitido de asesor2 queda bloqueado al instante (403)
    resp_bloqueado = client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {token_asesor2}"},
    )
    assert resp_bloqueado.status_code == 403


def test_conversaciones_se_guardan_por_usuario_y_estan_aisladas(entorno_bd, monkeypatch) -> None:
    client, _ = entorno_bd

    monkeypatch.setattr(
        chat_route.grafo,
        "invoke",
        lambda estado, config=None: {
            "messages": [
                *estado["messages"],
                AIMessage(content=f"Respuesta guardada para: {estado['messages'][-1].content}"),
            ]
        },
    )

    token_admin = client.post(
        "/api/v1/auth/login",
        json={
            "username": settings.admin_initial_username,
            "password": settings.admin_initial_password,
        },
    ).json()["access_token"]

    token_operador = client.post(
        "/api/v1/auth/login",
        json={
            "username": settings.operador_initial_username,
            "password": settings.operador_initial_password,
        },
    ).json()["access_token"]

    # Usuario Admin envía 2 mensajes en su conversación 'conv-robert-1'
    r1 = client.post(
        "/api/v1/chat",
        headers={"Authorization": f"Bearer {token_admin}"},
        json={"mensaje": "Procesar entradas del 06-11-2026", "session_id": "conv-robert-1"},
    )
    assert r1.status_code == 200
    assert "Procesar entradas del 06-11-2026" in r1.json()["respuesta"]

    r2 = client.post(
        "/api/v1/chat",
        headers={"Authorization": f"Bearer {token_admin}"},
        json={"mensaje": "Dame el TXT separado por comas", "session_id": "conv-robert-1"},
    )
    assert r2.status_code == 200

    # Usuario Operador envía 1 mensaje en su propia conversación 'conv-almacen-1'
    r3 = client.post(
        "/api/v1/chat",
        headers={"Authorization": f"Bearer {token_operador}"},
        json={"mensaje": "Consultar línea CYBER", "session_id": "conv-almacen-1"},
    )
    assert r3.status_code == 200

    # Admin consulta su lista de conversaciones: ve 'conv-robert-1' con 4 mensajes (2 user + 2 assistant)
    lista_admin = client.get(
        "/api/v1/chat/conversaciones",
        headers={"Authorization": f"Bearer {token_admin}"},
    )
    assert lista_admin.status_code == 200
    convs_admin = lista_admin.json()
    assert len(convs_admin) == 1
    assert convs_admin[0]["id"] == "conv-robert-1"
    assert convs_admin[0]["total_mensajes"] == 4

    # Detalle completo de los mensajes de 'conv-robert-1'
    detalle = client.get(
        "/api/v1/chat/conversaciones/conv-robert-1",
        headers={"Authorization": f"Bearer {token_admin}"},
    )
    assert detalle.status_code == 200
    mensajes = detalle.json()["mensajes"]
    assert len(mensajes) == 4
    assert mensajes[0]["rol"] == "user"
    assert mensajes[0]["contenido"] == "Procesar entradas del 06-11-2026"
    assert mensajes[1]["rol"] == "assistant"

    # Operador no puede ver ni escribir en la conversación de Admin (403 Forbidden)
    intento_lectura = client.get(
        "/api/v1/chat/conversaciones/conv-robert-1",
        headers={"Authorization": f"Bearer {token_operador}"},
    )
    assert intento_lectura.status_code == 403

    intento_escritura = client.post(
        "/api/v1/chat",
        headers={"Authorization": f"Bearer {token_operador}"},
        json={"mensaje": "Intento intruso", "session_id": "conv-robert-1"},
    )
    assert intento_escritura.status_code == 403

    # Operador elimina su propia conversación
    borrado = client.delete(
        "/api/v1/chat/conversaciones/conv-almacen-1",
        headers={"Authorization": f"Bearer {token_operador}"},
    )
    assert borrado.status_code == 204
    lista_op_despues = client.get(
        "/api/v1/chat/conversaciones",
        headers={"Authorization": f"Bearer {token_operador}"},
    ).json()
    assert lista_op_despues == []


def test_catalogo_sae_factores_y_reportes_desde_base_de_datos(entorno_bd, tmp_path, monkeypatch) -> None:
    _, TestSessionLocal = entorno_bd
    monkeypatch.delenv("CATALOGO_SAE_PATH", raising=False)

    with TestSessionLocal() as db:
        db.merge(SaeLinea(clave_linea="CYBER", descripcion="CYBERMATIC", estatus="A"))
        db.merge(
            SaeArticulo(
                clave_articulo="PU14TRANSBLUE",
                descripcion="MANGUERA POLIURETANO 1/4 AZUL",
                clave_linea="CYBER",
                unidad_entrada="M",
                cve_sat="40142000",
                cve_unidad="MTR",
                ultimo_costo=14.5,
                estatus="A",
            )
        )
        db.commit()

    limpiar_cache_catalogo_sae()
    catalogo = cargar_catalogo_sae()
    assert catalogo["disponible"] is True
    assert catalogo["ruta"] == "database:sae_articulos"

    encontrado = buscar_articulo_sae("PU14TRANSBLUE")
    assert encontrado is not None
    assert encontrado["cve_art"] == "PU14TRANSBLUE"
    assert encontrado["linea"] == "CYBER"

    # Prueba de guardado de factor personalizado y reporte en BD
    ruta_json_temp = tmp_path / "FACTORES_PERSONALIZADOS.json"
    guardar_factor_personalizado(
        "DAYCO",
        "COMPRAS GENERALES FORANEAS",
        ruta=ruta_json_temp,
        usuario_id=1,
        sincronizar_bd=True,
    )

    with TestSessionLocal() as db:
        fila_factor = db.scalar(select(FactorLinea).where(FactorLinea.clave_linea == "DAYCO"))
        assert fila_factor is not None
        assert fila_factor.nombre_factor == "COMPRAS GENERALES FORANEAS"
        assert fila_factor.es_personalizado is True

    factores_leidos = cargar_factores_personalizados(ruta=ruta_json_temp, incluir_bd=True)
    assert factores_leidos["DAYCO"]["factor"] == "COMPRAS GENERALES FORANEAS"

    reporte_id = registrar_reporte_en_bd(
        {
            "fecha_carpeta": "06-11-2026",
            "productos_acumulados": 1,
            "productos_detalle": [
                {
                    "clave_articulo": "PU14TRANSBLUE",
                    "codigo_xml_original": "PU1/4-TRANSBLUE-100M",
                    "descripcion": "MANGUERA POLIURETANO 1/4 AZUL",
                    "linea": "CYBER",
                    "proveedor": "491",
                    "unidad": "MTR",
                    "cantidad": 100.0,
                    "precio_compra": 14.5,
                    "factor": "CYBERMATIC",
                    "precios_venta": {
                        "PUBLICO": 32.2222,
                        "MINIMO": 25.7778,
                        "MOSTRADOR": 32.2222,
                        "MAYOREO": 29.0,
                        "DISTRIBUIDOR": 25.7778,
                    },
                    "origen_clave": "INVE02_EXACTA",
                    "origen_linea": "INVE02",
                    "origen_proveedor": "PROV02_RFC",
                }
            ],
        },
        usuario_id=1,
    )
    assert reporte_id is not None

    with TestSessionLocal() as db:
        rep = db.scalar(select(ReporteAlmacen).where(ReporteAlmacen.id == reporte_id))
        detalles = db.scalars(
            select(DetalleEntradaAlmacen).where(DetalleEntradaAlmacen.reporte_id == reporte_id)
        ).all()
        assert rep is not None
        assert rep.fecha_carpeta == "06-11-2026"
        assert rep.fecha_reporte == date(2026, 11, 6)
        assert len(detalles) == 1
        assert detalles[0].clave_articulo == "PU14TRANSBLUE"
        assert detalles[0].codigo_xml_original == "PU1/4-TRANSBLUE-100M"
        assert detalles[0].unidad_procesada == "MTR"
        assert detalles[0].cantidad == Decimal("100.000000")
        assert detalles[0].precio_compra == Decimal("14.500000")
        precios_guardados = json.loads(detalles[0].precios_venta_json)
        assert precios_guardados["PUBLICO"] == 32.2222
        assert detalles[0].origen_clave == "INVE02_EXACTA"
