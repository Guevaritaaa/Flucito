from contextlib import asynccontextmanager
import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.routes.auth import router as auth_router
from app.api.v1.routes.chat import router as chat_router
from app.api.v1.routes.almacen import router as almacen_router
from app.core.seed import inicializar_base_de_datos

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] [%(name)s]: %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_: FastAPI):
    try:
        resumen_seed = inicializar_base_de_datos(cargar_articulos_sae=True)
        logger.info("Base de datos inicializada correctamente: %s", resumen_seed)
    except Exception as exc:
        logger.warning("No se pudo ejecutar seed inicial al arrancar: %s", exc)
    yield


app = FastAPI(title="Flucito API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://flucito.com", "https://www.flucito.com", "https://api.flucito.com", "http://localhost:8080", "http://127.0.0.1:8080", "http://localhost:3000", "*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router, prefix="/api/v1")
app.include_router(chat_router, prefix="/api/v1")
app.include_router(almacen_router, prefix="/api/v1")


@app.get("/")
def root():
    return {"mensaje": "Flucito API corriendo"}


@app.get("/health", include_in_schema=False)
def health():
    """Endpoint liviano para monitoreo externo y health checks."""
    return {"status": "ok"}
