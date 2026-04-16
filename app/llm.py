import os
import httpx
import json
import asyncio
import logging
import time
import random
from typing import Dict, Any, Optional, List

logger = logging.getLogger(__name__)

_raw_keys = os.getenv("GEMINI_API_KEYS", os.getenv("GEMINI_API_KEY", ""))
GEMINI_KEYS: List[str] = [k.strip() for k in _raw_keys.split(",") if k.strip()]

_key_index = 0
_key_lock = asyncio.Lock()
_key_cooldown_until: Dict[str, float] = {}
_key_rate_limit_hits: Dict[str, int] = {}

GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent"

GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
GROQ_MODEL = os.getenv("GROQ_MODEL", "llama-3.1-8b-instant")

MAX_RETRIES = 3
RETRY_BASE_DELAY = 4
RATE_LIMIT_DEFAULT_COOLDOWN = 30


class RateLimitError(Exception):
    pass


def _parse_retry_after(headers: httpx.Headers) -> Optional[int]:
    retry_after = headers.get("Retry-After")
    if not retry_after:
        return None
    try:
        segundos = int(retry_after)
        return segundos if segundos > 0 else None
    except ValueError:
        return None


def _mascarar_chave(chave: str) -> str:
    if not chave:
        return "vazia"
    return f"...{chave[-6:]}"


def _marcar_cooldown(chave: str, retry_after: Optional[int] = None) -> int:
    hits = _key_rate_limit_hits.get(chave, 0) + 1
    _key_rate_limit_hits[chave] = hits

    if retry_after is None:
        base = RETRY_BASE_DELAY * (2 ** min(hits - 1, 4))
        cooldown = max(RATE_LIMIT_DEFAULT_COOLDOWN, base)
    else:
        cooldown = retry_after

    jitter = random.randint(0, 3)
    cooldown_total = cooldown + jitter
    _key_cooldown_until[chave] = time.monotonic() + cooldown_total
    return cooldown_total


def _tempo_restante_cooldown(chave: str) -> float:
    return max(0.0, _key_cooldown_until.get(chave, 0.0) - time.monotonic())


async def _proxima_chave_disponivel() -> str:
    global _key_index
    if not GEMINI_KEYS:
        return ""

    async with _key_lock:
        total = len(GEMINI_KEYS)
        for offset in range(total):
            idx = (_key_index + offset) % total
            chave = GEMINI_KEYS[idx]
            if _tempo_restante_cooldown(chave) <= 0:
                _key_index = idx + 1
                return chave
    return ""


async def _chamar_gemini_com_chave(prompt: str, chave: str) -> str:
    headers = {"Content-Type": "application/json"}
    params = {"key": chave}
    body = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0.1, "maxOutputTokens": 1000}
    }
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(GEMINI_URL, json=body, params=params, headers=headers)
        resp.raise_for_status()
        data = resp.json()
        return data["candidates"][0]["content"]["parts"][0]["text"]


async def _chamar_groq(prompt: str) -> str:
    if not GROQ_API_KEY:
        raise RateLimitError("Groq nao configurado (GROQ_API_KEY ausente).")

    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type": "application/json"
    }
    body = {
        "model": GROQ_MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.1,
        "max_tokens": 1000
    }
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(GROQ_URL, json=body, headers=headers)
        try:
            resp.raise_for_status()
        except httpx.HTTPStatusError:
            detalhe = resp.text[:500] if resp.text else "sem corpo de resposta"
            logger.error(f"Falha Groq HTTP {resp.status_code}: {detalhe}")
            raise
        data = resp.json()
        return data["choices"][0]["message"]["content"]


async def chamar_llm(prompt: str) -> str:
    if not GEMINI_KEYS:
        logger.warning("Nenhuma chave Gemini configurada. Usando Groq.")
        try:
            return await _chamar_groq(prompt)
        except Exception as e:
            raise RateLimitError(
                f"Nenhuma chave Gemini configurada e o fallback Groq falhou: {type(e).__name__}: {str(e)}"
            ) from e

    max_tentativas = max(1, len(GEMINI_KEYS) * MAX_RETRIES)
    for _ in range(max_tentativas):
        chave = await _proxima_chave_disponivel()

        if not chave:
            logger.warning("Todas as chaves Gemini estao em cooldown. Usando fallback Groq.")
            break

        try:
            resultado = await _chamar_gemini_com_chave(prompt, chave)
            _key_rate_limit_hits[chave] = 0
            _key_cooldown_until[chave] = 0.0
            return resultado

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 429:
                retry_after = _parse_retry_after(e.response.headers)
                cooldown = _marcar_cooldown(chave, retry_after=retry_after)
                logger.warning(f"Rate limit na chave {_mascarar_chave(chave)}. Cooldown de {cooldown}s.")
                continue
            elif e.response.status_code == 404:
                logger.error("Modelo Gemini nao encontrado. Verifique GEMINI_URL.")
                raise
            else:
                logger.error(f"Erro HTTP Gemini: {e.response.status_code}")
                raise

        except httpx.TimeoutException:
            logger.warning(f"Timeout na chave {_mascarar_chave(chave)}. Tentando proxima...")
            await asyncio.sleep(1)
            continue

    logger.warning("Todas as chaves Gemini em rate limit. Usando fallback Groq.")
    try:
        return await _chamar_groq(prompt)
    except Exception as e:
        raise RateLimitError(
            f"Todas as chaves Gemini atingiram rate limit e o fallback Groq falhou: {type(e).__name__}: {str(e)}"
        ) from e


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

    texto = await chamar_llm(prompt)
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

    texto = await chamar_llm(prompt)
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
    if not GEMINI_KEYS and not GROQ_API_KEY:
        return {
            "tese_inferida_na_peticao": "Nenhuma API de LLM configurada",
            "adequacao_tematica": "INDETERMINADO",
            "adequacao_dispositivo": "INDETERMINADO",
            "peso_precedencial": "INDETERMINADO",
            "justificativa": "Configure GEMINI_API_KEYS ou GROQ_API_KEY no .env.",
            "recomendacao": "REVISAR",
            "nivel_urgencia": "ATENCAO"
        }

    try:
        resultado_tese = await inferir_tese(referencia, contexto)
        tese = resultado_tese.get("tese_inferida", "nao identificada")

        await asyncio.sleep(1)

        resultado_adequacao = await avaliar_adequacao(
            tese_inferida=tese,
            assunto_real=assunto_real or "nao identificado",
            dispositivo=dispositivo or "nao identificado",
            grau=grau or "nao identificado",
            flags=flags
        )

        return {"tese_inferida_na_peticao": tese, **resultado_adequacao}

    except RateLimitError as e:
        return {
            "tese_inferida_na_peticao": "Analise indisponivel (rate limit)",
            "adequacao_tematica": "INDETERMINADO",
            "adequacao_dispositivo": "INDETERMINADO",
            "peso_precedencial": "INDETERMINADO",
            "justificativa": str(e),
            "recomendacao": "REVISAR",
            "nivel_urgencia": "ATENCAO",
            "erro": "rate_limit"
        }
    except Exception as e:
        logger.exception("Falha inesperada na analise LLM")
        return {
            "tese_inferida_na_peticao": "Analise indisponivel (erro interno de LLM)",
            "adequacao_tematica": "INDETERMINADO",
            "adequacao_dispositivo": "INDETERMINADO",
            "peso_precedencial": "INDETERMINADO",
            "justificativa": f"Erro inesperado: {type(e).__name__}: {str(e)}",
            "recomendacao": "REVISAR",
            "nivel_urgencia": "ATENCAO",
            "erro": "llm_unexpected"
        }