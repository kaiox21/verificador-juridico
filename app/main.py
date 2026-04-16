from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.models import VerificacaoRequest, VerificacaoResponse
from app.pipeline import executar_pipeline

app = FastAPI(
    title="Verificador de Referências Jurídicas",
    description="Verifica automaticamente referências jurídicas geradas por IA",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
def root():
    return {"status": "ok", "message": "Verificador de Referências Jurídicas — NIA/TCU"}


@app.post("/verificar", response_model=VerificacaoResponse)
async def verificar(body: VerificacaoRequest):
    return await executar_pipeline(body.referencia, body.contexto)
