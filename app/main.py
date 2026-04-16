from dotenv import load_dotenv

load_dotenv()

from pathlib import Path
import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from app.models import (
    VerificacaoRequest,
    VerificacaoResponse,
    VerificacaoLoteRequest,
    VerificacaoLoteResponse,
    Existencia,
    Conteudo,
    Adequacao,
)
from app.pipeline import executar_pipeline

logger = logging.getLogger(__name__)

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
@app.get("/ui")
def ui():
    ui_path = Path(__file__).resolve().parent / "static" / "verificador.html"
    return FileResponse(ui_path)


@app.get("/health")
def health():
    return {"status": "ok", "message": "Verificador de Referencias Juridicas - NIA/TCU"}


@app.post("/verificar", response_model=VerificacaoResponse)
async def verificar(body: VerificacaoRequest):
    try:
        return await executar_pipeline(body.referencia, body.contexto)
    except Exception as exc:
        logger.exception("Falha inesperada no endpoint /verificar")
        return VerificacaoResponse(
            referencia_normalizada=body.referencia,
            tribunal_inferido="INDETERMINADO",
            existencia=Existencia(
                status="NAO_ENCONTRADO",
                flags=[f"ERRO_INTERNO: {type(exc).__name__}"],
            ),
            conteudo=Conteudo(flags=["ANALISE_INDISPONIVEL"]),
            adequacao=Adequacao(
                tese_inferida_na_peticao="Analise indisponivel",
                adequacao_tematica="INDETERMINADO",
                adequacao_dispositivo="INDETERMINADO",
                peso_precedencial="INDETERMINADO",
                justificativa=f"Erro interno: {type(exc).__name__}: {str(exc)}",
            ),
            recomendacao="REVISAR",
            nivel_urgencia="ATENCAO",
        )


@app.post("/verificar-lote", response_model=VerificacaoLoteResponse)
async def verificar_lote(body: VerificacaoLoteRequest):
    resultados = []
    for referencia in body.referencias:
        resultados.append(await executar_pipeline(referencia, body.contexto))
    return VerificacaoLoteResponse(total=len(resultados), resultados=resultados)
