from app.parser import parse_referencia
from app.verificador import verificar_existencia
from app.llm import analisar_adequacao
from app.models import VerificacaoResponse, Existencia, Conteudo, Adequacao


async def executar_pipeline(referencia: str, contexto: str) -> VerificacaoResponse:
    """Orquestra as 4 camadas do pipeline de verificação."""

    # Camada 0 — Parse e validação local
    ref = parse_referencia(referencia)

    # Resposta antecipada se formato inválido
    if ref.tipo == "DESCONHECIDO":
        return VerificacaoResponse(
            referencia_normalizada=referencia,
            tribunal_inferido="DESCONHECIDO",
            existencia=Existencia(
                status="FORMATO_INVALIDO",
                flags=ref.flags
            ),
            conteudo=Conteudo(),
            adequacao=Adequacao(
                justificativa="Não foi possível identificar o formato da referência."
            ),
            recomendacao="REMOVER",
            nivel_urgencia="CRITICO"
        )

    # Camada 1 — Verificação de existência
    resultado_existencia = await verificar_existencia(ref)

    flags_existencia = list(ref.flags)  # começa com flags locais
    flags_existencia += resultado_existencia.get("flags", [])

    if not resultado_existencia.get("encontrado"):
        status = "NAO_ENCONTRADO"
        existencia = Existencia(
            status=status,
            flags=flags_existencia
        )
        # Sem dados reais, adequação não pode ser feita
        adequacao_result = await analisar_adequacao(
            referencia=referencia,
            contexto=contexto,
            assunto_real=None,
            dispositivo=None,
            grau=None,
            flags=flags_existencia
        )
        return VerificacaoResponse(
            referencia_normalizada=ref.numero_limpo,
            tribunal_inferido=ref.tribunal_inferido,
            existencia=existencia,
            conteudo=Conteudo(flags=["PROCESSO_NAO_LOCALIZADO"]),
            adequacao=Adequacao(**{
                k: v for k, v in adequacao_result.items()
                if k in Adequacao.model_fields
            }),
            recomendacao=adequacao_result.get("recomendacao", "REMOVER"),
            nivel_urgencia=adequacao_result.get("nivel_urgencia", "CRITICO")
        )

    # Processo encontrado — verificar divergências
    numero_real = resultado_existencia.get("numero_real", ref.numero_limpo)
    uf_real = resultado_existencia.get("uf_real")

    # Checar divergência de UF
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
        flags=flags_existencia
    )

    # Camada 2 — Conteúdo e metadados
    assunto = resultado_existencia.get("assunto") or resultado_existencia.get("ementa_parcial")
    grau = resultado_existencia.get("grau")
    flags_conteudo = list(resultado_existencia.get("flags", []))

    # Inferir dispositivo a partir das flags
    dispositivo = "NAO_IDENTIFICADO"
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
        flags=flags_conteudo
    )

    # Camada 3 — Adequação via LLM
    todas_flags = flags_existencia + flags_conteudo
    adequacao_result = await analisar_adequacao(
        referencia=referencia,
        contexto=contexto,
        assunto_real=assunto,
        dispositivo=dispositivo,
        grau=grau,
        flags=todas_flags
    )

    adequacao = Adequacao(**{
        k: v for k, v in adequacao_result.items()
        if k in Adequacao.model_fields
    })

    return VerificacaoResponse(
        referencia_normalizada=ref.numero_limpo,
        tribunal_inferido=ref.tribunal_inferido,
        existencia=existencia,
        conteudo=conteudo,
        adequacao=adequacao,
        recomendacao=adequacao_result.get("recomendacao", "REVISAR"),
        nivel_urgencia=adequacao_result.get("nivel_urgencia", "ATENCAO")
    )
