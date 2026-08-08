
import json

from fastapi import APIRouter, HTTPException, status

from app.agents.graph import grafo
from app.schemas.chat import ChatRequest, ChatResponse
from app.services.cfdi.jobs import obtener_job
from langchain_core.messages import HumanMessage

router = APIRouter()


@router.post("/chat", response_model=ChatResponse)
def chat(request: ChatRequest) -> ChatResponse:
    if request.cfdi_job_id and obtener_job(request.cfdi_job_id) is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Job CFDI no encontrado",
        )

    estado = {"messages": [HumanMessage(content=request.mensaje)]}
    if request.cfdi_job_id:
        estado["cfdi_job_id"] = request.cfdi_job_id
    config = {"configurable": {"thread_id": request.session_id}}
    resultado = grafo.invoke(estado, config=config)
    respuesta = resultado["messages"][-1].content

    archivo_excel_url = None
    archivo_almacen_url = None
    for mensaje in reversed(resultado["messages"]):
        if getattr(mensaje, "type", None) != "tool":
            continue
        try:
            datos = json.loads(mensaje.content)
        except (TypeError, json.JSONDecodeError):
            continue
        job_id = datos.get("job_id") or request.cfdi_job_id
        if datos.get("ok") and datos.get("reporte_generado") and job_id:
            archivo_excel_url = f"/api/v1/cfdi/jobs/{job_id}/download"
            break
        if datos.get("ok") and datos.get("reporte_generado") and datos.get("resumen"):
            archivo_almacen_url = "/api/v1/almacen/download"
            break

    return ChatResponse(
        respuesta=respuesta,
        archivo_excel_url=archivo_excel_url,
        archivo_almacen_url=archivo_almacen_url,
    )
