import asyncio
import json
import logging
import os
import random
import time
from typing import Any, Dict, List, Optional

import httpx

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
LLM_HTTP_TIMEOUT_SECONDS = float(os.getenv("LLM_HTTP_TIMEOUT_SECONDS", "8"))
LLM_TOTAL_TIMEOUT_SECONDS = float(os.getenv("LLM_TOTAL_TIMEOUT_SECONDS", "9"))


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
        "generationConfig": {"temperature": 0.1, "maxOutputTokens": 1000},
    }
    async with httpx.AsyncClient(timeout=LLM_HTTP_TIMEOUT_SECONDS) as client:
        resp = await client.post(GEMINI_URL, json=body, params=params, headers=headers)
        resp.raise_for_status()
        data = resp.json()
        candidate = data["candidates"][0]
        content = candidate.get("content", {})
        if isinstance(content, dict):
            parts = content.get("parts", [])
            if parts:
                return parts[0].get("text", "")
        raise ValueError("Resposta Gemini sem texto em candidates[0].content.parts")


async def _chamar_groq(prompt: str) -> str:
    if not GROQ_API_KEY:
        raise RateLimitError("Groq nao configurado (GROQ_API_KEY ausente).")

    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type": "application/json",
    }
    body = {
        "model": GROQ_MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.1,
        "max_tokens": 1000,
    }
    async with httpx.AsyncClient(timeout=LLM_HTTP_TIMEOUT_SECONDS) as client:
        resp = await client.post(GROQ_URL, json=body, headers=headers)
        try:
            resp.raise_for_status()
        except httpx.HTTPStatusError:
            detalhe = resp.text[:500] if resp.text else "sem corpo de resposta"
            logger.error("Falha Groq HTTP %s: %s", resp.status_code, detalhe)
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
                "Nenhuma chave Gemini configurada e o fallback Groq falhou. "
                f"Detalhe do fallback Groq: {type(e).__name__}: {str(e)}"
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
            logger.debug("Gemini respondeu com chave %s", _mascarar_chave(chave))
            return resultado
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 429:
                retry_after = _parse_retry_after(e.response.headers)
                cooldown = _marcar_cooldown(chave, retry_after=retry_after)
                logger.warning(
                    "Rate limit na chave %s. Cooldown de %ss antes de reutilizar.",
                    _mascarar_chave(chave),
                    cooldown,
                )
                continue
            if e.response.status_code == 404:
                logger.error("Modelo Gemini nao encontrado. Verifique GEMINI_URL.")
                raise
            logger.error("Erro HTTP Gemini: %s", e.response.status_code)
            raise
        except httpx.TimeoutException:
            logger.warning("Timeout na chave %s. Tentando proxima...", _mascarar_chave(chave))
            await asyncio.sleep(1)
            continue

    logger.warning("Todas as chaves Gemini em rate limit. Usando fallback Groq.")
    try:
        return await _chamar_groq(prompt)
    except Exception as e:
        raise RateLimitError(
            "Todas as chaves Gemini atingiram rate limit e o fallback Groq tambem falhou. "
            f"Detalhe do fallback Groq: {type(e).__name__}: {str(e)}"
        ) from e


def _inferir_tese_heuristica(contexto: str) -> str:
    txt = (contexto or "").lower()
    if "taxa de conveniencia" in txt:
        return "A cobranca de taxa de conveniencia seria abusiva ao consumidor"
    if "precedente" in txt and "tribunal" in txt:
        return "A peticao tenta usar precedente como suporte principal da tese"
    contexto_limpo = " ".join((contexto or "").split())
    if not contexto_limpo:
        return "Tese nao identificada"
    return contexto_limpo[:180]


def _fallback_adequacao(
    referencia: str,
    contexto: str,
    assunto_real: Optional[str],
    dispositivo: Optional[str],
    grau: Optional[str],
    flags: List[str],
    motivo: str,
) -> Dict[str, Any]:
    tese = _inferir_tese_heuristica(contexto)
    assunto = (assunto_real or "").lower()
    dispositivo_norm = (dispositivo or "").upper()
    flags_set = {f.upper() for f in (flags or [])}
    contexto_norm = (contexto or "").lower()

    if "PROCESSO_NAO_LOCALIZADO" in flags_set or "NAO_ENCONTRADO" in flags_set:
        return {
            "tese_inferida_na_peticao": tese,
            "adequacao_tematica": "INADEQUADO",
            "adequacao_dispositivo": "INUTIL",
            "peso_precedencial": "NULO",
            "justificativa": "A referencia nao foi localizada na base consultada; a citacao nao sustenta a tese.",
            "recomendacao": "REMOVER",
            "nivel_urgencia": "CRITICO",
            "erro": motivo,
        }

    if "EXTINTO_SEM_MERITO" in flags_set or dispositivo_norm == "EXTINTO_SEM_MERITO":
        return {
            "tese_inferida_na_peticao": tese,
            "adequacao_tematica": "PARCIALMENTE_ADEQUADO",
            "adequacao_dispositivo": "INUTIL",
            "peso_precedencial": "NULO",
            "justificativa": "O processo foi extinto sem resolucao de merito; o valor precedencial para sustentar a tese e nulo.",
            "recomendacao": "SUBSTITUIR",
            "nivel_urgencia": "ATENCAO",
            "erro": motivo,
        }

    if "previdencia" in assunto and ("taxa de conveniencia" in contexto_norm or "consumidor" in contexto_norm):
        return {
            "tese_inferida_na_peticao": tese,
            "adequacao_tematica": "PARCIALMENTE_ADEQUADO",
            "adequacao_dispositivo": "INUTIL",
            "peso_precedencial": "NULO",
            "justificativa": "A tese da peticao e de consumo/taxa de conveniencia, mas o assunto real identificado e previdencia privada.",
            "recomendacao": "CORRIGIR",
            "nivel_urgencia": "ATENCAO",
            "erro": motivo,
        }

    if "NAO_CONHECIDO" in flags_set or dispositivo_norm == "NAO_CONHECIDO":
        return {
            "tese_inferida_na_peticao": tese,
            "adequacao_tematica": "PARCIALMENTE_ADEQUADO",
            "adequacao_dispositivo": "INUTIL",
            "peso_precedencial": "BAIXO",
            "justificativa": "O recurso foi identificado como nao conhecido, reduzindo utilidade argumentativa para a tese apresentada.",
            "recomendacao": "CORRIGIR",
            "nivel_urgencia": "ATENCAO",
            "erro": motivo,
        }

    return {
        "tese_inferida_na_peticao": tese,
        "adequacao_tematica": "PARCIALMENTE_ADEQUADO",
        "adequacao_dispositivo": "PARCIALMENTE_UTIL",
        "peso_precedencial": "MEDIO",
        "justificativa": "Analise heuristica aplicada por indisponibilidade temporaria de LLM; revisar a citacao antes de protocolar.",
        "recomendacao": "REVISAR",
        "nivel_urgencia": "ATENCAO",
        "erro": motivo,
    }


async def inferir_tese(referencia: str, contexto: str) -> Dict[str, Any]:
    prompt = f'''Voce e um especialista em direito processual brasileiro.

Analise o trecho de peticao abaixo, onde a referencia "{referencia}" e citada:

"{contexto}"

Responda em JSON com exatamente este formato:
{{
  "tese_inferida": "descricao objetiva da tese juridica que a citacao pretende sustentar",
  "tribunal_adequado": "qual tribunal seria hierarquicamente adequado para sustentar essa tese"
}}

Responda APENAS com o JSON, sem texto adicional.'''

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
    flags: list,
) -> Dict[str, Any]:
    flags_str = ", ".join(flags) if flags else "nenhuma"

    prompt = f'''Voce e um especialista em direito processual brasileiro.

A peticao usa uma referencia juridica para sustentar a seguinte tese:
"{tese_inferida}"

O julgado real tem estas caracteristicas:
- Assunto: {assunto_real}
- Dispositivo: {dispositivo}
- Grau: {grau}
- Flags identificadas: {flags_str}

Avalie a adequacao desta citacao e responda em JSON com exatamente este formato:
{{
  "adequacao_tematica": "ADEQUADO" ou "PARCIALMENTE_ADEQUADO" ou "INADEQUADO",
  "adequacao_dispositivo": "UTIL" ou "PARCIALMENTE_UTIL" ou "INUTIL",
  "peso_precedencial": "ALTO" ou "MEDIO" ou "BAIXO" ou "NULO",
  "justificativa": "explicacao objetiva em 2-3 frases",
  "recomendacao": "MANTER" ou "CORRIGIR" ou "REVISAR" ou "SUBSTITUIR" ou "REMOVER",
  "nivel_urgencia": "OK" ou "ATENCAO" ou "CRITICO"
}}

Responda APENAS com o JSON, sem texto adicional.'''

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
            "nivel_urgencia": "ATENCAO",
        }


async def analisar_adequacao(
    referencia: str,
    contexto: str,
    assunto_real: Optional[str],
    dispositivo: Optional[str],
    grau: Optional[str],
    flags: list,
) -> Dict[str, Any]:
    async def _executar_duas_passagens() -> Dict[str, Any]:
        resultado_tese = await inferir_tese(referencia, contexto)
        tese = resultado_tese.get("tese_inferida", "nao identificada")

        await asyncio.sleep(0.2)

        resultado_adequacao = await avaliar_adequacao(
            tese_inferida=tese,
            assunto_real=assunto_real or "nao identificado",
            dispositivo=dispositivo or "nao identificado",
            grau=grau or "nao identificado",
            flags=flags,
        )

        return {
            "tese_inferida_na_peticao": tese,
            **resultado_adequacao,
        }

    if not GEMINI_KEYS and not GROQ_API_KEY:
        return _fallback_adequacao(
            referencia=referencia,
            contexto=contexto,
            assunto_real=assunto_real,
            dispositivo=dispositivo,
            grau=grau,
            flags=flags,
            motivo="llm_nao_configurada",
        )

    try:
        return await asyncio.wait_for(
            _executar_duas_passagens(),
            timeout=LLM_TOTAL_TIMEOUT_SECONDS,
        )
    except RateLimitError:
        return _fallback_adequacao(
            referencia=referencia,
            contexto=contexto,
            assunto_real=assunto_real,
            dispositivo=dispositivo,
            grau=grau,
            flags=flags,
            motivo="rate_limit",
        )
    except asyncio.TimeoutError:
        return _fallback_adequacao(
            referencia=referencia,
            contexto=contexto,
            assunto_real=assunto_real,
            dispositivo=dispositivo,
            grau=grau,
            flags=flags,
            motivo="llm_timeout",
        )
    except Exception:
        logger.exception("Falha inesperada na analise LLM")
        return _fallback_adequacao(
            referencia=referencia,
            contexto=contexto,
            assunto_real=assunto_real,
            dispositivo=dispositivo,
            grau=grau,
            flags=flags,
            motivo="llm_unexpected",
        )
