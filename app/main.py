import asyncio

from dotenv import load_dotenv

load_dotenv()

from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from app.models import (
    VerificacaoRequest,
    VerificacaoResponse,
    VerificacaoLoteRequest,
    VerificacaoLoteResponse,
)
from app.pipeline import executar_pipeline

app = FastAPI(
    title="Verificador de Referencias Juridicas",
    description="Verifica automaticamente referencias juridicas geradas por IA",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
def root():
    return {"status": "ok", "message": "Verificador de Referencias Juridicas - NIA/TCU"}


@app.get("/ui")
def ui():
    ui_path = Path(__file__).resolve().parent / "static" / "verificador.html"
    return FileResponse(ui_path)


@app.post("/verificar", response_model=VerificacaoResponse)
async def verificar(body: VerificacaoRequest):
    return await executar_pipeline(body.referencia, body.contexto)


@app.post("/verificar-lote", response_model=VerificacaoLoteResponse)
async def verificar_lote(body: VerificacaoLoteRequest):
    resultados = await asyncio.gather(
        *[executar_pipeline(ref, body.contexto) for ref in body.referencias]
    )
    return VerificacaoLoteResponse(total=len(resultados), resultados=list(resultados))
