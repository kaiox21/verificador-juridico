import pytest
from unittest.mock import AsyncMock, patch

from app.parser import parse_referencia
from app.pipeline import executar_pipeline


# -----------------------------
# Grupo 1 - Parser local
# -----------------------------

def test_parser_cnj_valido():
    ref = parse_referencia("0815641-45.2025.8.10.0040")
    assert ref.tipo == "CNJ"
    assert ref.tribunal_inferido == "TJMA"
    assert "DIGITO_INVALIDO" not in ref.flags
    assert "VARA_NAO_ZERO_PRIMEIRO_GRAU" in ref.flags
    assert ref.vara == "0040"


def test_parser_cnj_digito_invalido():
    ref = parse_referencia("1234567-89.2030.8.26.0001")
    assert ref.tipo == "CNJ"
    assert "DIGITO_INVALIDO" in ref.flags
    assert "ANO_FUTURO" in ref.flags


def test_parser_superior_stj():
    ref = parse_referencia("REsp 1.810.170/RS")
    assert ref.tipo == "SUPERIOR"
    assert ref.tribunal_inferido == "STJ"
    assert ref.classe == "RESP"
    assert ref.numero_tribunal == "1810170"
    assert ref.uf == "RS"


def test_parser_formato_invalido():
    ref = parse_referencia("processo abc123 sem formato")
    assert ref.tipo == "DESCONHECIDO"
    assert "FORMATO_INVALIDO" in ref.flags


def test_parser_entrada_none():
    ref = parse_referencia(None)
    assert ref.tipo == "DESCONHECIDO"
    assert "FORMATO_INVALIDO" in ref.flags


def test_parser_entrada_string_vazia():
    ref = parse_referencia("")
    assert ref.tipo == "DESCONHECIDO"
    assert "FORMATO_INVALIDO" in ref.flags


# -----------------------------
# Grupo 2 - Pipeline com mocks
# -----------------------------

@pytest.mark.asyncio
async def test_pipeline_caso1_resp_inadequado():
    referencia = "REsp 1.810.170/RS"
    contexto = (
        "Conforme entendimento pacificado no STJ, a cobranca de taxa de "
        "conveniencia e abusiva ao consumidor, como decidido no REsp 1.810.170/RS."
    )

    mock_existencia = {
        "encontrado": True,
        "numero_real": "RESP 1810170/SP",
        "uf_real": "SP",
        "assunto": "Previdencia privada",
        "dispositivo": "NAO_CONHECIDO",
        "flags": ["NAO_CONHECIDO"],
        "url_fonte": "https://scon.stj.jus.br/...",
        "fonte": "STJ SCON",
    }

    mock_adequacao = {
        "tese_inferida_na_peticao": "Ilegalidade da cobranca de taxa de conveniencia",
        "adequacao_tematica": "INADEQUADO",
        "adequacao_dispositivo": "INUTIL",
        "peso_precedencial": "NULO",
        "justificativa": "Julgado trata de previdencia privada, nao de taxa de conveniencia.",
        "recomendacao": "REMOVER",
        "nivel_urgencia": "CRITICO",
    }

    with patch("app.pipeline.verificar_existencia", new=AsyncMock(return_value=mock_existencia)), \
         patch("app.pipeline.analisar_adequacao", new=AsyncMock(return_value=mock_adequacao)), \
         patch("app.pipeline.sugerir_substituicao", new=AsyncMock(return_value=None)), \
         patch("app.pipeline.registrar_auditoria"):
        resultado = await executar_pipeline(referencia, contexto)

    assert resultado.recomendacao == "REMOVER"
    assert resultado.nivel_urgencia == "CRITICO"
    assert resultado.existencia.status == "EXISTE_COM_DIVERGENCIA"
    assert resultado.adequacao.adequacao_tematica == "INADEQUADO"
    assert resultado.adequacao.peso_precedencial == "NULO"


@pytest.mark.asyncio
async def test_pipeline_caso2_cnj_extinto():
    referencia = "0815641-45.2025.8.10.0040"
    contexto = (
        "No ambito deste Egregio Tribunal de Justica do Estado do Maranhao, "
        "cumpre citar o precedente firmado nos autos do processo n 0815641-45.2025.8.10.0040."
    )

    mock_existencia = {
        "encontrado": True,
        "numero_real": "08156414520258100040",
        "assunto": "Nao informado",
        "grau": "primeiro grau",
        "dispositivo": "EXTINTO_SEM_MERITO",
        "flags": ["EXTINTO_SEM_MERITO"],
        "url_fonte": "https://datajud-wiki.cnj.jus.br",
        "fonte": "Datajud",
    }

    mock_adequacao = {
        "tese_inferida_na_peticao": "Precedente consolidado no TJMA",
        "adequacao_tematica": "INDETERMINADO",
        "adequacao_dispositivo": "INUTIL",
        "peso_precedencial": "NULO",
        "justificativa": "Processo extinto sem merito nao constitui precedente.",
        "recomendacao": "REMOVER",
        "nivel_urgencia": "CRITICO",
    }

    with patch("app.pipeline.verificar_existencia", new=AsyncMock(return_value=mock_existencia)), \
         patch("app.pipeline.analisar_adequacao", new=AsyncMock(return_value=mock_adequacao)), \
         patch("app.pipeline.sugerir_substituicao", new=AsyncMock(return_value=None)), \
         patch("app.pipeline.registrar_auditoria"):
        resultado = await executar_pipeline(referencia, contexto)

    assert resultado.recomendacao == "REMOVER"
    assert resultado.nivel_urgencia == "CRITICO"
    assert resultado.existencia.status == "EXISTE_COM_DIVERGENCIA"
    assert "VARA_NAO_ZERO_PRIMEIRO_GRAU" in resultado.existencia.flags
    assert resultado.conteudo.dispositivo == "EXTINTO_SEM_MERITO"
    assert "EXTINTO_SEM_MERITO" in resultado.conteudo.flags


@pytest.mark.asyncio
async def test_pipeline_digito_invalido_rejeita_sem_rede():
    referencia = "1234567-89.2030.8.26.0001"
    contexto = "qualquer contexto"

    with patch("app.pipeline.verificar_existencia", new=AsyncMock()) as mock_existencia, \
         patch("app.pipeline.analisar_adequacao", new=AsyncMock()) as mock_adequacao, \
         patch("app.pipeline.registrar_auditoria"):
        resultado = await executar_pipeline(referencia, contexto)

    assert resultado.recomendacao == "REMOVER"
    assert resultado.nivel_urgencia == "CRITICO"
    assert resultado.existencia.status == "FORMATO_INVALIDO"
    mock_existencia.assert_not_called()
    mock_adequacao.assert_not_called()


# -----------------------------
# Grupo 3 - Nao encontrado
# -----------------------------

@pytest.mark.asyncio
async def test_pipeline_nao_encontrado():
    referencia = "0001234-17.2023.8.26.0000"
    contexto = "qualquer contexto"

    mock_existencia = {"encontrado": False}
    mock_adequacao = {
        "tese_inferida_na_peticao": "qualquer",
        "adequacao_tematica": "INDETERMINADO",
        "adequacao_dispositivo": "INDETERMINADO",
        "peso_precedencial": "NULO",
        "justificativa": "Processo nao localizado.",
        "recomendacao": "REMOVER",
        "nivel_urgencia": "CRITICO",
    }

    with patch("app.pipeline.verificar_existencia", new=AsyncMock(return_value=mock_existencia)), \
         patch("app.pipeline.analisar_adequacao", new=AsyncMock(return_value=mock_adequacao)), \
         patch("app.pipeline.sugerir_substituicao", new=AsyncMock(return_value=None)), \
         patch("app.pipeline.registrar_auditoria"):
        resultado = await executar_pipeline(referencia, contexto)

    assert resultado.existencia.status == "NAO_ENCONTRADO"
    assert resultado.recomendacao == "REMOVER"


@pytest.mark.asyncio
async def test_guardrail_remover_com_urgencia_ok_vira_critico():
    referencia = "RE 999999/DF"
    contexto = "qualquer contexto"

    mock_existencia = {
        "encontrado": True,
        "numero_real": "0001234-17.2023.8.26.0000",
        "assunto": "Qualquer",
        "grau": "segundo grau",
        "dispositivo": "NAO_IDENTIFICADO",
        "flags": [],
        "fonte": "Datajud",
    }
    mock_adequacao = {
        "tese_inferida_na_peticao": "qualquer",
        "adequacao_tematica": "INADEQUADO",
        "adequacao_dispositivo": "INUTIL",
        "peso_precedencial": "NULO",
        "justificativa": "Julgado inadequado.",
        "recomendacao": "REMOVER",
        "nivel_urgencia": "OK",
    }

    with patch("app.pipeline.verificar_existencia", new=AsyncMock(return_value=mock_existencia)), \
         patch("app.pipeline.analisar_adequacao", new=AsyncMock(return_value=mock_adequacao)), \
         patch("app.pipeline.sugerir_substituicao", new=AsyncMock(return_value=None)), \
         patch("app.pipeline.registrar_auditoria"):
        resultado = await executar_pipeline(referencia, contexto)

    assert resultado.nivel_urgencia == "CRITICO"
    assert resultado.recomendacao == "REMOVER"


@pytest.mark.asyncio
async def test_guardrail_inadequado_e_inutil_vira_peso_nulo():
    referencia = "RE 999998/DF"
    contexto = "qualquer contexto"

    mock_existencia = {
        "encontrado": True,
        "numero_real": "0001234-17.2023.8.26.0000",
        "assunto": "Qualquer",
        "grau": "segundo grau",
        "dispositivo": "NAO_IDENTIFICADO",
        "flags": [],
        "fonte": "Datajud",
    }
    mock_adequacao = {
        "tese_inferida_na_peticao": "qualquer",
        "adequacao_tematica": "INADEQUADO",
        "adequacao_dispositivo": "INUTIL",
        "peso_precedencial": "MEDIO",
        "justificativa": "Julgado inadequado.",
        "recomendacao": "MANTER",
        "nivel_urgencia": "OK",
    }

    with patch("app.pipeline.verificar_existencia", new=AsyncMock(return_value=mock_existencia)), \
         patch("app.pipeline.analisar_adequacao", new=AsyncMock(return_value=mock_adequacao)), \
         patch("app.pipeline.sugerir_substituicao", new=AsyncMock(return_value=None)), \
         patch("app.pipeline.registrar_auditoria"):
        resultado = await executar_pipeline(referencia, contexto)

    assert resultado.adequacao.peso_precedencial == "NULO"
    assert resultado.recomendacao == "REMOVER"
    assert resultado.nivel_urgencia == "CRITICO"
