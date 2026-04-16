import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict

AUDITORIA_DIR = Path(__file__).resolve().parent / "auditoria"
AUDITORIA_FILE = AUDITORIA_DIR / "verificacoes.jsonl"


def registrar_auditoria(registro: Dict[str, Any]) -> None:
    AUDITORIA_DIR.mkdir(parents=True, exist_ok=True)
    payload = {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        **registro,
    }
    with AUDITORIA_FILE.open("a", encoding="utf-8") as f:
        f.write(json.dumps(payload, ensure_ascii=False) + "\n")