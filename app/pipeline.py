from app.parser import parse_referencia
from app.verificador import verificar_existencia, sugerir_substituicao
from app.llm import analisar_adequacao
from app.models import VerificacaoResponse, Existencia, Conteudo, Adequacao
from app.auditoria import registrar_auditoria


def _deve_sugerir_substituicao(recomendacao: str) -> bool:
    return recomendacao in {"CORRIGIR", "SUBSTITUIR", "REMOVER", "REVISAR"}


async def executar_pipeline(referencia: str, contexto: str) -> VerificacaoResponse:
    """Orquestra as 4 camadas do pipeline de verificacao."""

    # Camada 0 - Parse e validacao local
    ref = parse_referencia(referencia)

    # Resposta antecipada se formato invalido
    if ref.tipo == "DESCONHECIDO":
        resposta = VerificacaoResponse(
            referencia_normalizada=referencia,
            tribunal_inferido="DESCONHECIDO",
            existencia=Existencia(
                status="FORMATO_INVALIDO",
                flags=ref.flags,
            ),
            conteudo=Conteudo(),
            adequacao=Adequacao(
                justificativa="Nao foi possivel identificar o formato da referencia.",
            ),
            recomendacao="REMOVER",
            nivel_urgencia="CRITICO",
        )
        registrar_auditoria(
            {
                "entrada": {"referencia": referencia, "contexto": contexto},
                "parse": {
                    "tipo": ref.tipo,
                    "tribunal_inferido": ref.tribunal_inferido,
                    "numero_limpo": ref.numero_limpo,
                    "flags": ref.flags,
                },
                "resultado": resposta.model_dump(),
            }
        )
        return resposta

    # Camada 1 - Verificacao de existencia
    resultado_existencia = await verificar_existencia(ref)

    flags_existencia = list(ref.flags)
    flags_existencia += resultado_existencia.get("flags", [])
    if resultado_existencia.get("erro"):
        flags_existencia.append(f"ERRO_FONTE: {resultado_existencia.get('erro')}")

    if not resultado_existencia.get("encontrado"):
        existencia = Existencia(status="NAO_ENCONTRADO", flags=flags_existencia)

        adequacao_result = await analisar_adequacao(
            referencia=referencia,
            contexto=contexto,
            assunto_real=None,
            dispositivo=None,
            grau=None,
            flags=flags_existencia,
        )

        recomendacao = adequacao_result.get("recomendacao", "REMOVER")
        sugestao = None
        if _deve_sugerir_substituicao(recomendacao):
            sugestao = await sugerir_substituicao(
                adequacao_result.get("tese_inferida_na_peticao") or "",
                ref.tribunal_inferido if ref.tribunal_inferido else "STJ",
            )

        resposta = VerificacaoResponse(
            referencia_normalizada=ref.numero_limpo,
            tribunal_inferido=ref.tribunal_inferido,
            existencia=existencia,
            conteudo=Conteudo(flags=["PROCESSO_NAO_LOCALIZADO"]),
            adequacao=Adequacao(
                **{k: v for k, v in adequacao_result.items() if k in Adequacao.model_fields}
            ),
            recomendacao=recomendacao,
            nivel_urgencia=adequacao_result.get("nivel_urgencia", "CRITICO"),
            sugestao_substituicao=sugestao,
        )

        registrar_auditoria(
            {
                "entrada": {"referencia": referencia, "contexto": contexto},
                "parse": {
                    "tipo": ref.tipo,
                    "tribunal_inferido": ref.tribunal_inferido,
                    "numero_limpo": ref.numero_limpo,
                    "flags": ref.flags,
                },
                "evidencia": resultado_existencia,
                "resultado": resposta.model_dump(),
            }
        )
        return resposta

    # Processo encontrado - verificar divergencias
    numero_real = resultado_existencia.get("numero_real", ref.numero_limpo)
    uf_real = resultado_existencia.get("uf_real")

    if ref.uf and uf_real and ref.uf != uf_real:
        status = "EXISTE_COM_DIVERGENCIA"
    elif flags_existencia:
        status = "EXISTE_COM_DIVERGENCIA"
    else:
        status = "EXISTE"

    existencia = Existencia(
        status=status,
        numero_real=numero_real,
        fonte=resultado_existencia.get("fonte", "Datajud/SCON"),
        url_fonte=resultado_existencia.get("url_fonte"),
        flags=flags_existencia,
    )

    # Camada 2 - Conteudo e metadados
    assunto = resultado_existencia.get("assunto") or resultado_existencia.get("ementa_parcial")
    grau = resultado_existencia.get("grau")
    flags_conteudo = list(resultado_existencia.get("flags", []))

    dispositivo = resultado_existencia.get("dispositivo") or "NAO_IDENTIFICADO"
    if "EXTINTO_SEM_MERITO" in flags_conteudo:
        dispositivo = "EXTINTO_SEM_MERITO"
        if "EXTINTO_SEM_MERITO" not in flags_conteudo:
            flags_conteudo.append("EXTINTO_SEM_MERITO")
    elif "TEM_ACORDAO" in flags_conteudo:
        dispositivo = "COM_ACORDAO"

    conteudo = Conteudo(
        assunto_real=assunto,
        dispositivo=dispositivo,
        grau=grau,
        flags=flags_conteudo,
    )

    # Camada 3 - Adequacao via LLM
    todas_flags = flags_existencia + flags_conteudo
    adequacao_result = await analisar_adequacao(
        referencia=referencia,
        contexto=contexto,
        assunto_real=assunto,
        dispositivo=dispositivo,
        grau=grau,
        flags=todas_flags,
    )

    recomendacao = adequacao_result.get("recomendacao", "REVISAR")
    sugestao = None
    if _deve_sugerir_substituicao(recomendacao):
        sugestao = await sugerir_substituicao(
            adequacao_result.get("tese_inferida_na_peticao") or "",
            ref.tribunal_inferido if ref.tribunal_inferido else "STJ",
        )

    resposta = VerificacaoResponse(
        referencia_normalizada=ref.numero_limpo,
        tribunal_inferido=ref.tribunal_inferido,
        existencia=existencia,
        conteudo=conteudo,
        adequacao=Adequacao(
            **{k: v for k, v in adequacao_result.items() if k in Adequacao.model_fields}
        ),
        recomendacao=recomendacao,
        nivel_urgencia=adequacao_result.get("nivel_urgencia", "ATENCAO"),
        sugestao_substituicao=sugestao,
    )

    registrar_auditoria(
        {
            "entrada": {"referencia": referencia, "contexto": contexto},
            "parse": {
                "tipo": ref.tipo,
                "tribunal_inferido": ref.tribunal_inferido,
                "numero_limpo": ref.numero_limpo,
                "flags": ref.flags,
            },
            "evidencia": resultado_existencia,
            "resultado": resposta.model_dump(),
        }
    )

    return resposta
