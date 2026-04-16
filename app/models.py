from pydantic import BaseModel, Field
from typing import Optional, List


class VerificacaoRequest(BaseModel):
    referencia: str
    contexto: str


class VerificacaoLoteRequest(BaseModel):
    referencias: List[str]
    contexto: str


class Existencia(BaseModel):
    status: str  # EXISTE, EXISTE_COM_DIVERGENCIA, NAO_ENCONTRADO, FORMATO_INVALIDO
    numero_real: Optional[str] = None
    fonte: Optional[str] = None
    url_fonte: Optional[str] = None
    flags: List[str] = Field(default_factory=list)


class Conteudo(BaseModel):
    assunto_real: Optional[str] = None
    dispositivo: Optional[str] = None
    grau: Optional[str] = None
    tema_repetitivo: Optional[str] = None
    flags: List[str] = Field(default_factory=list)


class Adequacao(BaseModel):
    tese_inferida_na_peticao: Optional[str] = None
    adequacao_tematica: Optional[str] = None  # ADEQUADO, PARCIALMENTE_ADEQUADO, INADEQUADO
    adequacao_dispositivo: Optional[str] = None  # UTIL, PARCIALMENTE_UTIL, INUTIL
    peso_precedencial: Optional[str] = None  # ALTO, MEDIO, BAIXO, NULO
    justificativa: Optional[str] = None


class SugestaoItem(BaseModel):
    fonte: str
    titulo: str
    url: str
    observacao: Optional[str] = None


class SugestaoSubstituicao(BaseModel):
    tema_inferido: Optional[str] = None
    estrategia: Optional[str] = None
    sugestoes: List[SugestaoItem] = Field(default_factory=list)


class VerificacaoResponse(BaseModel):
    referencia_normalizada: str
    tribunal_inferido: str

    existencia: Existencia
    conteudo: Conteudo
    adequacao: Adequacao

    recomendacao: str  # MANTER, CORRIGIR, REVISAR, SUBSTITUIR, REMOVER
    nivel_urgencia: str  # OK, ATENCAO, CRITICO
    sugestao_substituicao: Optional[SugestaoSubstituicao] = None


class VerificacaoLoteResponse(BaseModel):
    total: int
    resultados: List[VerificacaoResponse]
