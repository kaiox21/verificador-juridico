import httpx
import re
from typing import Optional, Dict, Any
from app.parser import ReferenciaParseada

DATAJUD_BASE = "https://api-publica.datajud.cnj.jus.br"
DATAJUD_API_KEY = "APIKey cDZHYzlZa0JadVREZDJCendFbXNpVXgzZXRKTmFHWjZlSmxUZXpDNTZ4Nk1PZENob2lOM3p3Z1pMZE9hTjFZSA=="

# Códigos TPU relevantes
TPU_FLAGS = {
    22: "EXTINTO_SEM_MERITO",
    237: "EXTINTO_SEM_MERITO",
    848: "TEM_ACORDAO",
    904: "TRANSITADO",
}

# Mapa tribunal → índice Datajud
TRIBUNAL_PARA_INDICE = {
    "TJAC": "tjac", "TJAL": "tjal", "TJAP": "tjap", "TJAM": "tjam",
    "TJBA": "tjba", "TJCE": "tjce", "TJDF": "tjdft", "TJGO": "tjgo",
    "TJMA": "tjma", "TJMT": "tjmt", "TJMS": "tjms", "TJMG": "tjmg",
    "TJPA": "tjpa", "TJPB": "tjpb", "TJPR": "tjpr", "TJPE": "tjpe",
    "TJPI": "tjpi", "TJRJ": "tjrj", "TJRN": "tjrn", "TJRS": "tjrs",
    "TJRO": "tjro", "TJRR": "tjrr", "TJSC": "tjsc", "TJSP": "tjsp",
    "TJSE": "tjse", "TJTO": "tjto",
    "STJ": "stj", "STF": "stf", "TST": "tst",
}


async def verificar_datajud(ref: ReferenciaParseada) -> Dict[str, Any]:
    """Verifica processo CNJ no Datajud."""
    indice = TRIBUNAL_PARA_INDICE.get(ref.tribunal_inferido)
    if not indice:
        return {"encontrado": False, "erro": f"Tribunal {ref.tribunal_inferido} não coberto"}

    url = f"{DATAJUD_BASE}/api_publica_{indice}/_search"
    query = {
        "query": {
            "match": {
                "numeroProcesso": ref.numero_limpo.replace("-", "").replace(".", "")
            }
        }
    }

    headers = {
        "Authorization": DATAJUD_API_KEY,
        "Content-Type": "application/json"
    }

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(url, json=query, headers=headers)
            resp.raise_for_status()
            data = resp.json()

        hits = data.get("hits", {}).get("hits", [])
        if not hits:
            return {"encontrado": False}

        processo = hits[0]["_source"]
        flags = []

        # Verificar movimentos TPU
        movimentos = processo.get("movimentos", [])
        for mov in movimentos:
            codigo = mov.get("codigo")
            if codigo in TPU_FLAGS:
                flag = TPU_FLAGS[codigo]
                if flag not in flags:
                    flags.append(flag)

        # Verificar grau
        grau = processo.get("grau", "")
        grau_legivel = "primeiro grau" if grau == "G1" else "segundo grau" if grau == "G2" else grau

        # Assuntos
        assuntos = processo.get("assuntos", [])
        assunto_str = ", ".join([a.get("nome", "") for a in assuntos]) if assuntos else None

        return {
            "encontrado": True,
            "numero_real": processo.get("numeroProcesso", ref.numero_limpo),
            "assunto": assunto_str,
            "grau": grau_legivel,
            "tribunal": processo.get("tribunal", ref.tribunal_inferido),
            "orgao_julgador": processo.get("orgaoJulgador", {}).get("nome"),
            "flags": flags,
            "url_fonte": f"https://datajud-wiki.cnj.jus.br",
        }

    except httpx.HTTPError as e:
        return {"encontrado": False, "erro": str(e)}


async def verificar_stj_scon(ref: ReferenciaParseada) -> Dict[str, Any]:
    """Verifica acórdão no SCON do STJ."""
    numero = ref.numero_tribunal
    if not numero:
        return {"encontrado": False, "erro": "Número não extraído"}

    url = f"https://scon.stj.jus.br/SCON/pesquisar.jsp"
    params = {
        "b": "ACOR",
        "livre": f"{ref.classe} {numero}",
        "thesaurus": "JURIDICO",
    }

    try:
        async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
            resp = await client.get(url, params=params)
            html = resp.text

        # Verificar se encontrou resultado
        if "Nenhum documento" in html or "0 documento" in html:
            return {"encontrado": False}

        # Extrair UF real se disponível
        uf_match = re.search(r"REsp\s*[\d.,]+/([A-Z]{2})", html)
        uf_real = uf_match.group(1) if uf_match else None

        flags = []
        if ref.uf and uf_real and ref.uf != uf_real:
            flags.append(f"UF_DIVERGENTE: citado {ref.uf}, real {uf_real}")

        # Extrair ementa parcial
        ementa_match = re.search(r'class="docEmentaClass"[^>]*>(.*?)</p>', html, re.DOTALL)
        ementa = re.sub(r"<[^>]+>", "", ementa_match.group(1)).strip()[:500] if ementa_match else None

        numero_real = f"{ref.classe} {numero}"
        if uf_real:
            numero_real += f"/{uf_real}"

        url_processo = f"https://scon.stj.jus.br/SCON/pesquisar.jsp?b=ACOR&livre={ref.classe}+{numero}"

        return {
            "encontrado": True,
            "numero_real": numero_real,
            "uf_real": uf_real,
            "ementa_parcial": ementa,
            "flags": flags,
            "url_fonte": url_processo,
            "fonte": "STJ SCON",
        }

    except httpx.HTTPError as e:
        return {"encontrado": False, "erro": str(e)}


async def verificar_existencia(ref: ReferenciaParseada) -> Dict[str, Any]:
    """Roteia para a fonte correta baseado no tipo e tribunal."""
    if ref.tipo == "DESCONHECIDO":
        return {"encontrado": False, "erro": "Formato não reconhecido"}

    if ref.tipo == "CNJ":
        return await verificar_datajud(ref)

    if ref.tipo == "SUPERIOR":
        if ref.tribunal_inferido == "STJ":
            return await verificar_stj_scon(ref)
        # Outros superiores: tenta Datajud
        return await verificar_datajud(ref)

    return {"encontrado": False, "erro": "Tipo não coberto"}
