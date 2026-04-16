import os
import httpx
import json
import asyncio
import logging
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent"

MAX_RETRIES = 3
RETRY_BASE_DELAY = 5  # dobra a cada tentativa: 5s, 10s, 20s


class RateLimitError(Exception):
    """Erro específico para rate limit da API."""
    pass


async def chamar_gemini(prompt: str) -> str:
    headers = {"Content-Type": "application/json"}
    params = {"key": GEMINI_API_KEY}
    body = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0.1, "maxOutputTokens": 1000}
    }

    for tentativa in range(1, MAX_RETRIES + 1):
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.post(GEMINI_URL, json=body, params=params, headers=headers)

                if resp.status_code == 429:
                    if tentativa < MAX_RETRIES:
                        delay = RETRY_BASE_DELAY * (2 ** (tentativa - 1))
                        logger.warning(f"Rate limit (tentativa {tentativa}/{MAX_RETRIES}). Aguardando {delay}s...")
                        await asyncio.sleep(delay)
                        continue
                    raise RateLimitError(
                        "A API do Gemini está com rate limit. Aguarde alguns minutos e tente novamente."
                    )

                resp.raise_for_status()
                data = resp.json()
                return data["candidates"][0]["content"]["parts"][0]["text"]

        except RateLimitError:
            raise
        except httpx.HTTPStatusError as e:
            logger.error(f"Erro HTTP da API Gemini: {e.response.status_code}")
            raise
        except httpx.TimeoutException:
            if tentativa < MAX_RETRIES:
                logger.warning(f"Timeout na tentativa {tentativa}. Tentando novamente...")
                await asyncio.sleep(2)
                continue
            raise

    raise RuntimeError("Falha inesperada após todas as tentativas.")


async def inferir_tese(referencia: str, contexto: str) -> dict:
    prompt = f"""Você é um especialista em direito processual brasileiro.

Analise o trecho de petição abaixo, onde a referência "{referencia}" é citada:

"{contexto}"

Responda em JSON com exatamente este formato:
{{
  "tese_inferida": "descrição objetiva da tese jurídica que a citação pretende sustentar",
  "tribunal_adequado": "qual tribunal seria hierarquicamente adequado para sustentar essa tese"
}}

Responda APENAS com o JSON, sem texto adicional."""

    texto = await chamar_gemini(prompt)
    texto = texto.strip().replace("```json", "").replace("```", "").strip()
    try:
        return json.loads(texto)
    except Exception:
        return {"tese_inferida": texto, "tribunal_adequado": "indeterminado"}


async def avaliar_adequacao(
    tese_inferida: str,
    assunto_real: str,
    dispositivo: str,
    grau: str,
    flags: list
) -> Dict[str, Any]:
    flags_str = ", ".join(flags) if flags else "nenhuma"

    prompt = f"""Você é um especialista em direito processual brasileiro.

A petição usa uma referência jurídica para sustentar a seguinte tese:
"{tese_inferida}"

O julgado real tem estas características:
- Assunto: {assunto_real}
- Dispositivo: {dispositivo}
- Grau: {grau}
- Flags identificadas: {flags_str}

Avalie a adequação desta citação e responda em JSON com exatamente este formato:
{{
  "adequacao_tematica": "ADEQUADO" ou "PARCIALMENTE_ADEQUADO" ou "INADEQUADO",
  "adequacao_dispositivo": "UTIL" ou "PARCIALMENTE_UTIL" ou "INUTIL",
  "peso_precedencial": "ALTO" ou "MEDIO" ou "BAIXO" ou "NULO",
  "justificativa": "explicação objetiva em 2-3 frases",
  "recomendacao": "MANTER" ou "CORRIGIR" ou "REVISAR" ou "SUBSTITUIR" ou "REMOVER",
  "nivel_urgencia": "OK" ou "ATENCAO" ou "CRITICO"
}}

Responda APENAS com o JSON, sem texto adicional."""

    texto = await chamar_gemini(prompt)
    texto = texto.strip().replace("```json", "").replace("```", "").strip()
    try:
        return json.loads(texto)
    except Exception:
        return {
            "adequacao_tematica": "INDETERMINADO",
            "adequacao_dispositivo": "INDETERMINADO",
            "peso_precedencial": "INDETERMINADO",
            "justificativa": texto,
            "recomendacao": "REVISAR",
            "nivel_urgencia": "ATENCAO"
        }


async def analisar_adequacao(
    referencia: str,
    contexto: str,
    assunto_real: Optional[str],
    dispositivo: Optional[str],
    grau: Optional[str],
    flags: list
) -> Dict[str, Any]:
    if not GEMINI_API_KEY:
        return {
            "tese_inferida_na_peticao": "API Gemini não configurada",
            "adequacao_tematica": "INDETERMINADO",
            "adequacao_dispositivo": "INDETERMINADO",
            "peso_precedencial": "INDETERMINADO",
            "justificativa": "Configure GEMINI_API_KEY para habilitar esta análise.",
            "recomendacao": "REVISAR",
            "nivel_urgencia": "ATENCAO"
        }

    try:
        resultado_tese = await inferir_tese(referencia, contexto)
        tese = resultado_tese.get("tese_inferida", "não identificada")

        await asyncio.sleep(1)  # pausa entre chamadas para evitar rate limit

        resultado_adequacao = await avaliar_adequacao(
            tese_inferida=tese,
            assunto_real=assunto_real or "não identificado",
            dispositivo=dispositivo or "não identificado",
            grau=grau or "não identificado",
            flags=flags
        )

        return {
            "tese_inferida_na_peticao": tese,
            **resultado_adequacao
        }

    except RateLimitError as e:
        return {
            "tese_inferida_na_peticao": "Análise indisponível (rate limit)",
            "adequacao_tematica": "INDETERMINADO",
            "adequacao_dispositivo": "INDETERMINADO",
            "peso_precedencial": "INDETERMINADO",
            "justificativa": str(e),
            "recomendacao": "REVISAR",
            "nivel_urgencia": "ATENCAO",
            "erro": "rate_limit"
        }