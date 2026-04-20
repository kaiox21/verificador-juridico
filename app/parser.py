import re
from dataclasses import dataclass, field
from typing import Optional, List


@dataclass
class ReferenciaParseada:
    tipo: str  # "CNJ" ou "SUPERIOR" ou "DESCONHECIDO"
    referencia_original: str
    numero_limpo: str
    tribunal_inferido: str
    flags: List[str] = field(default_factory=list)

    # Campos CNJ
    seq: Optional[str] = None
    digito: Optional[str] = None
    ano: Optional[str] = None
    j: Optional[str] = None
    tr: Optional[str] = None
    vara: Optional[str] = None
    uf: Optional[str] = None

    # Campos Tribunal Superior
    classe: Optional[str] = None
    numero_tribunal: Optional[str] = None


# Mapa de codigo TR -> sigla do tribunal (CNJ)
TR_PARA_TRIBUNAL = {
    "01": "TJAC", "02": "TJAL", "03": "TJAP", "04": "TJAM", "05": "TJBA",
    "06": "TJCE", "07": "TJDFT", "08": "TJES", "09": "TJGO", "10": "TJMA",
    "11": "TJMT", "12": "TJMS", "13": "TJMG", "14": "TJPA", "15": "TJPB",
    "16": "TJPR", "17": "TJPE", "18": "TJPI", "19": "TJRJ", "20": "TJRN",
    "21": "TJRS", "22": "TJRO", "23": "TJRR", "24": "TJSC", "25": "TJSE",
    "26": "TJSP", "27": "TJTO",
}

J_PARA_JUSTICA = {
    "1": "JF",   # Justica Federal (compat)
    "2": "JT",   # Justica do Trabalho
    "3": "JE",   # Justica Eleitoral
    "4": "JF",   # Justica Federal
    "5": "TST",  # TST
    "6": "STM",  # STM
    "7": "STF",  # STF
    "8": "JE",   # Justica Estadual
    "9": "STJ",  # STJ
}

CLASSES_SUPERIORES = [
    "REsp", "AREsp", "AgInt", "HC", "RHC", "MS", "RMS",
    "AI", "Ag", "RE", "ARE", "ADI", "ADPF", "ACO",
    "RR", "AIRR", "TST",
]


def validar_digito_cnj(seq: str, digito: str, ano: str, j: str, tr: str, vara: str) -> bool:
    """Valida digito verificador CNJ pelo algoritmo modulo 97-10 (ISO 7064)."""
    numero_base = seq + ano + j + tr + vara
    try:
        digito_calculado = 98 - (int(numero_base) * 100 % 97)
        return int(digito) == digito_calculado
    except ValueError:
        return False


def parse_referencia(referencia: str) -> ReferenciaParseada:
    """Camada 0: parseia e valida localmente a referencia juridica."""
    if not isinstance(referencia, str) or not referencia.strip():
        return ReferenciaParseada(
            tipo="DESCONHECIDO",
            referencia_original=str(referencia),
            numero_limpo=str(referencia),
            tribunal_inferido="DESCONHECIDO",
            flags=["FORMATO_INVALIDO"],
        )

    flags = []

    # Tenta padrao CNJ: NNNNNNN-DD.AAAA.J.TR.OOOO
    cnj_pattern = re.compile(r"(\d{7})-(\d{2})\.(\d{4})\.(\d)\.(\d{2})\.(\d{4})")
    match_cnj = cnj_pattern.search(referencia)

    if match_cnj:
        seq, digito, ano, j, tr, vara = match_cnj.groups()

        # Validar digito verificador
        if not validar_digito_cnj(seq, digito, ano, j, tr, vara):
            flags.append("DIGITO_INVALIDO")

        # Flags de ano
        import datetime
        ano_int = int(ano)
        ano_atual = datetime.datetime.now().year
        if ano_int > ano_atual:
            flags.append("ANO_FUTURO")
        elif ano_int < 1988:
            flags.append("ANO_SUSPEITO")

        # Flag de grau (vara != 0000 -> 1o grau)
        if vara != "0000":
            flags.append("VARA_NAO_ZERO_PRIMEIRO_GRAU")

        # Inferir tribunal
        tribunal = TR_PARA_TRIBUNAL.get(tr, f"TR_{tr}")
        if j in J_PARA_JUSTICA:
            if j == "8":
                tribunal = TR_PARA_TRIBUNAL.get(tr, f"TJ_{tr}")
            elif j in {"1", "4"}:
                # CNJ federal costuma vir como .4.TR.; mantemos "1" por compatibilidade.
                tribunal = f"TRF{int(tr)}" if tr.isdigit() else f"TRF_{tr}"
            else:
                tribunal = J_PARA_JUSTICA[j]

        numero_limpo = f"{seq}-{digito}.{ano}.{j}.{tr}.{vara}"

        return ReferenciaParseada(
            tipo="CNJ",
            referencia_original=referencia,
            numero_limpo=numero_limpo,
            tribunal_inferido=tribunal,
            flags=flags,
            seq=seq,
            digito=digito,
            ano=ano,
            j=j,
            tr=tr,
            vara=vara,
        )

    # Tenta padrao tribunal superior: REsp 1.810.170/RS
    for classe in CLASSES_SUPERIORES:
        pattern = re.compile(rf"({re.escape(classe)})\s*([\d.,]+)(?:/([A-Z]{{2}}))?", re.IGNORECASE)
        match = pattern.search(referencia)
        if match:
            classe_encontrada = match.group(1).upper()
            numero_raw = match.group(2).replace(".", "").replace(",", "")
            uf = match.group(3) if match.group(3) else None

            # Inferir tribunal
            if classe_encontrada in ["RESP", "ARESP", "AGINT"]:
                tribunal = "STJ"
            elif classe_encontrada in ["RE", "ARE", "ADI", "ADPF"]:
                tribunal = "STF"
            elif classe_encontrada in ["RR", "AIRR"]:
                tribunal = "TST"
            else:
                tribunal = "STJ"

            numero_limpo = f"{classe_encontrada} {numero_raw}"
            if uf:
                numero_limpo += f"/{uf}"

            return ReferenciaParseada(
                tipo="SUPERIOR",
                referencia_original=referencia,
                numero_limpo=numero_limpo,
                tribunal_inferido=tribunal,
                flags=flags,
                classe=classe_encontrada,
                numero_tribunal=numero_raw,
                uf=uf,
            )

    # Formato desconhecido
    flags.append("FORMATO_INVALIDO")
    return ReferenciaParseada(
        tipo="DESCONHECIDO",
        referencia_original=referencia,
        numero_limpo=referencia,
        tribunal_inferido="DESCONHECIDO",
        flags=flags,
    )
