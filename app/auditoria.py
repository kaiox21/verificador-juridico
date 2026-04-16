import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict

logger = logging.getLogger(__name__)

AUDITORIA_DIR = Path(__file__).resolve().parent / "auditoria"
AUDITORIA_FILE = AUDITORIA_DIR / "verificacoes.jsonl"
TMP_AUDITORIA_FILE = Path(os.getenv("TMPDIR", "/tmp")) / "verificacoes.jsonl"


def registrar_auditoria(registro: Dict[str, Any]) -> None:
    """
    Salva trilha de auditoria em JSONL.
    Cada linha contem entrada, saida e evidencias da verificacao.
    """
    payload = {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        **registro,
    }
    linha = json.dumps(payload, ensure_ascii=False) + "\n"

    # 1) Caminho local do projeto (ambiente dev)
    try:
        AUDITORIA_DIR.mkdir(parents=True, exist_ok=True)
        with AUDITORIA_FILE.open("a", encoding="utf-8") as f:
            f.write(linha)
        return
    except OSError:
        pass

    # 2) Fallback para ambientes serverless/read-only (ex.: Vercel)
    try:
        TMP_AUDITORIA_FILE.parent.mkdir(parents=True, exist_ok=True)
        with TMP_AUDITORIA_FILE.open("a", encoding="utf-8") as f:
            f.write(linha)
    except OSError as exc:
        # Auditoria nunca deve derrubar a API principal.
        logger.warning("Nao foi possivel registrar auditoria: %s", exc)
