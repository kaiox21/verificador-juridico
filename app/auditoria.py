import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict

logger = logging.getLogger(__name__)

# Em serverless (ex.: Vercel), somente /tmp e gravavel.
if os.getenv("VERCEL"):
    AUDITORIA_DIR = Path("/tmp/verificador_auditoria")
else:
    AUDITORIA_DIR = Path(__file__).resolve().parent / "auditoria"

AUDITORIA_FILE = AUDITORIA_DIR / "verificacoes.jsonl"


def registrar_auditoria(registro: Dict[str, Any]) -> None:
    """
    Salva trilha de auditoria em JSONL.
    Cada linha contem entrada, saida e evidencias da verificacao.
    """
    payload = {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        **registro,
    }
    try:
        AUDITORIA_DIR.mkdir(parents=True, exist_ok=True)
        with AUDITORIA_FILE.open("a", encoding="utf-8") as f:
            f.write(json.dumps(payload, ensure_ascii=False) + "\n")
    except Exception:
        # Auditoria nao pode derrubar a API, mas o erro deve ficar visivel em log.
        logger.exception("Falha ao gravar trilha de auditoria.")
        return
