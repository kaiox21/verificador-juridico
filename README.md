# Verificador de Referencias Juridicas

API REST em FastAPI para validar referencias juridicas citadas em textos processuais, com foco em reduzir risco de alucinacoes de IA.

## O que o projeto faz hoje

- Parse local de referencia CNJ e de tribunais superiores (ex.: `REsp`, `RE`, `ADI`, `RR`)
- Validacao de formato e digito verificador CNJ (modulo 97-10)
- Verificacao de existencia em fonte externa (DataJud / STJ SCON)
- Analise de adequacao contextual com LLM (duas passagens)
- Guardrails de consistencia para recomendacao e urgencia
- Sugestao automatica de substituicao quando a citacao e inadequada
- Processamento unitario e em lote
- Trilha de auditoria em JSONL

## Arquitetura

- Camada 0 (parser local): `app/parser.py`
  - Identifica tipo (`CNJ`, `SUPERIOR`, `DESCONHECIDO`)
  - Gera flags como `FORMATO_INVALIDO`, `DIGITO_INVALIDO`, `ANO_FUTURO`
- Camada 1 (existencia): `app/verificador.py`
  - CNJ: consulta DataJud
  - STJ: consulta SCON
  - STF/TST: tentativa via DataJud e fallback controlado
  - Cache em memoria com TTL (`CACHE_TTL_SECONDS`, padrao 600)
- Camada 2 (conteudo): `app/pipeline.py`
  - Consolida assunto, dispositivo, grau e flags de metadados
- Camada 3 (adequacao): `app/llm.py`
  - Passagem 1: inferencia da tese no contexto
  - Passagem 2: avaliacao da aderencia da referencia

## Endpoints

- `GET /` - health basico
- `GET /ui` - interface web para verificacao unitaria
- `POST /verificar` - verificacao unica
- `POST /verificar-lote` - verificacao em lote
- `GET /docs` - Swagger/OpenAPI

## Estrutura de resposta (resumo)

```json
{
  "referencia_normalizada": "...",
  "tribunal_inferido": "...",
  "existencia": {
    "status": "EXISTE | EXISTE_COM_DIVERGENCIA | NAO_ENCONTRADO | FORMATO_INVALIDO",
    "numero_real": "...",
    "fonte": "...",
    "url_fonte": "...",
    "flags": []
  },
  "conteudo": {
    "assunto_real": "...",
    "dispositivo": "...",
    "grau": "...",
    "tema_repetitivo": "...",
    "flags": []
  },
  "adequacao": {
    "tese_inferida_na_peticao": "...",
    "adequacao_tematica": "ADEQUADO | PARCIALMENTE_ADEQUADO | INADEQUADO",
    "adequacao_dispositivo": "UTIL | PARCIALMENTE_UTIL | INUTIL",
    "peso_precedencial": "ALTO | MEDIO | BAIXO | NULO",
    "justificativa": "..."
  },
  "recomendacao": "MANTER | CORRIGIR | REVISAR | SUBSTITUIR | REMOVER",
  "nivel_urgencia": "OK | ATENCAO | CRITICO",
  "sugestao_substituicao": {
    "tema_inferido": "...",
    "estrategia": "...",
    "sugestoes": []
  }
}
```

## Requisitos

- Python 3.11+
- Dependencias em `requirements.txt`

## Instalacao local

```bash
git clone https://github.com/kaiox21/verificador-juridico
cd verificador-juridico
python -m venv .venv
```

Ativacao do ambiente virtual:

```bash
# Linux/macOS
source .venv/bin/activate

# Windows PowerShell
.\.venv\Scripts\Activate.ps1
```

Instalacao de dependencias:

```bash
pip install -r requirements.txt
```

Crie o `.env` a partir do exemplo:

```bash
# Linux/macOS
cp .env.example .env

# Windows PowerShell
Copy-Item .env.example .env
```

## Variaveis de ambiente

| Variavel | Obrigatoria | Uso |
|---|---|---|
| `DATAJUD_API_KEY` | Nao (mas recomendada) | Consulta de processos em DataJud |
| `GEMINI_API_KEYS` | Nao (se usar Groq) | Chaves Gemini separadas por virgula |
| `GROQ_API_KEY` | Nao (se usar Gemini) | Fallback de LLM |
| `GROQ_MODEL` | Nao | Modelo Groq (padrao: `llama-3.1-8b-instant`) |
| `CACHE_TTL_SECONDS` | Nao | TTL do cache de existencia (padrao: `600`) |

Observacoes:

- Sem `DATAJUD_API_KEY`, a API continua respondendo, mas consultas que dependem de DataJud voltam como nao encontradas/indisponiveis.
- Sem `GEMINI_API_KEYS` e sem `GROQ_API_KEY`, a camada de adequacao retorna status `INDETERMINADO` com justificativa explicita.

## Execucao

```bash
python -m uvicorn app.main:app --reload
```

Acesse:

- `http://localhost:8000/ui`
- `http://localhost:8000/docs`

## Exemplos

Verificacao unitaria:

```bash
curl -X POST http://localhost:8000/verificar \
  -H "Content-Type: application/json" \
  -d '{
    "referencia": "REsp 1.810.170/RS",
    "contexto": "Conforme entendimento pacificado no STJ..."
  }'
```

Verificacao em lote:

```bash
curl -X POST http://localhost:8000/verificar-lote \
  -H "Content-Type: application/json" \
  -d '{
    "referencias": [
      "REsp 1.810.170/RS",
      "0815641-45.2025.8.10.0040",
      "1234567-89.2030.8.26.0001"
    ],
    "contexto": "Trecho unico da peca em que as referencias sao usadas."
  }'
```

## Testes

Comando validado no projeto:

```bash
python -m pytest -q
```

Estado atual da suite:

- 12 testes (`tests/test_verificador.py`)
- Cobertura de parser, pipeline e guardrails

## Auditoria

Cada verificacao registra trilha em JSONL:

- Ambiente local: `app/auditoria/verificacoes.jsonl`
- Ambiente serverless (Vercel): `/tmp/verificador_auditoria/verificacoes.jsonl`

## Deploy

### Vercel

O projeto ja possui `vercel.json` com roteamento para `app/main.py`.

Variaveis recomendadas no deploy:

- `DATAJUD_API_KEY`
- `GEMINI_API_KEYS`
- `GROQ_API_KEY`
- `GROQ_MODEL`
- `CACHE_TTL_SECONDS`

### Procfile

Existe `Procfile` para execucao tipo Heroku:

```bash
web: uvicorn app.main:app --host 0.0.0.0 --port $PORT
```

## Limitacoes atuais

- Dependencia de disponibilidade de fontes externas (DataJud/STJ)
- Variacao de metadados por tribunal/fonte
- Qualidade da avaliacao contextual depende do contexto enviado para LLM

## Licenca

Licenca ainda nao definida no repositorio.
