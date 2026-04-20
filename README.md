# Verificador de ReferÃªncias JurÃ­dicas

API REST para validar referÃªncias jurÃ­dicas citadas em peÃ§as processuais geradas (ou apoiadas) por IA, reduzindo risco de alucinaÃ§Ãµes e citaÃ§Ãµes inadequadas.

## Status da entrega

Este projeto estÃ¡ alinhado com o **nÃ­vel avanÃ§ado** do mini desafio:

- Parser CNJ + tribunais superiores
- VerificaÃ§Ã£o de existÃªncia (DataJud / STJ SCON)
- SaÃ­da estruturada em 3 dimensÃµes (`existencia`, `conteudo`, `adequacao`)
- ValidaÃ§Ã£o de dÃ­gito CNJ (mÃ³dulo 97-10)
- Flags automÃ¡ticas por metadados (ex.: `EXTINTO_SEM_MERITO`)
- Camada de adequaÃ§Ã£o com LLM (duas passagens)
- Cache bÃ¡sico de existÃªncia (TTL)
- Processamento em lote (`POST /verificar-lote`)
- SugestÃ£o de substituiÃ§Ã£o quando a referÃªncia Ã© inadequada
- Cobertura ampliada (TRFs, STF, TST)
- Trilha de auditoria em `app/auditoria/verificacoes.jsonl`

## Arquitetura

- **Camada 0 â€” Parser local**
  - Regex CNJ e superiores
  - ValidaÃ§Ã£o de formato
  - ValidaÃ§Ã£o do dÃ­gito CNJ
  - Flags locais (`FORMATO_INVALIDO`, `ANO_FUTURO`, etc.)
- **Camada 1 â€” ExistÃªncia em fonte oficial**
  - DataJud para CNJ
  - STJ SCON para STJ
  - EstratÃ©gias para tribunais superiores
- **Camada 2 â€” ConteÃºdo e metadados**
  - Assunto, dispositivo, grau, flags TPU
- **Camada 3 â€” AdequaÃ§Ã£o contextual (LLM)**
  - InferÃªncia da tese da petiÃ§Ã£o
  - ComparaÃ§Ã£o da tese com o julgado real
  - RecomendaÃ§Ã£o final

## Endpoints

- `POST /verificar`
- `POST /verificar-lote`
- `GET /ui`
- `GET /docs`

> ObservaÃ§Ã£o importante: a UI (`/ui`) estÃ¡ focada em verificaÃ§Ã£o unitÃ¡ria. O processamento em lote Ã© consumido via API em `/docs` ou Postman/cURL.

## InstalaÃ§Ã£o local

```bash
git clone https://github.com/kaiox21/verificador-juridico
cd verificador-juridico
python -m venv venv
```

AtivaÃ§Ã£o do ambiente virtual:

```bash
# Linux/macOS
source venv/bin/activate

# Windows PowerShell
.\venv\Scripts\Activate.ps1
```

Instale dependÃªncias:

```bash
pip install -r requirements.txt
```

Crie o `.env`:

```bash
cp .env.example .env
# Windows sem cp:
copy .env.example .env
```

## VariÃ¡veis de ambiente

| VariÃ¡vel | ObrigatÃ³ria | DescriÃ§Ã£o |
|---|---|---|
| `DATAJUD_API_KEY` | Sim | Chave da API pÃºblica do DataJud |
| `GEMINI_API_KEYS` | Sim | Chaves Gemini separadas por vÃ­rgula |
| `GROQ_API_KEY` | Sim | Chave Groq para fallback LLM |
| `CACHE_TTL_SECONDS` | NÃ£o | TTL do cache (padrÃ£o: 600) |

## Testes

Os testes rodam offline - sem necessidade de API keys ou acesso a internet.

```bash
pytest tests/ -v
```

Cobertura atual: 12 testes unitarios cobrindo parser, pipeline e guardrails de consistencia.


## ExecuÃ§Ã£o

```bash
python -m uvicorn app.main:app --reload
```

Acesse:

- [http://localhost:8000/ui](http://localhost:8000/ui)
- [http://localhost:8000/docs](http://localhost:8000/docs)

## Exemplos de uso

### VerificaÃ§Ã£o unitÃ¡ria

```bash
curl -X POST http://localhost:8000/verificar \
  -H "Content-Type: application/json" \
  -d '{
    "referencia": "REsp 1.810.170/RS",
    "contexto": "Conforme entendimento pacificado no STJ, a cobranÃ§a de taxa de conveniÃªncia Ã© abusiva ao consumidor."
  }'
```

### VerificaÃ§Ã£o em lote

```bash
curl -X POST http://localhost:8000/verificar-lote \
  -H "Content-Type: application/json" \
  -d '{
    "referencias": [
      "REsp 1.810.170/RS",
      "0815641-45.2025.8.10.0040",
      "1234567-89.2030.8.26.0001",
      "processo abc123 sem formato"
    ],
    "contexto": "Trecho Ãºnico da peÃ§a em que as referÃªncias sÃ£o usadas."
  }'
```

## Estrutura de resposta (resumo)

```json
{
  "referencia_normalizada": "...",
  "tribunal_inferido": "...",
  "existencia": { "status": "...", "numero_real": "...", "flags": [] },
  "conteudo": { "assunto_real": "...", "dispositivo": "...", "grau": "...", "flags": [] },
  "adequacao": {
    "tese_inferida_na_peticao": "...",
    "adequacao_tematica": "...",
    "adequacao_dispositivo": "...",
    "peso_precedencial": "...",
    "justificativa": "..."
  },
  "recomendacao": "...",
  "nivel_urgencia": "...",
  "sugestao_substituicao": { "tema_inferido": "...", "sugestoes": [] }
}
```

## Casos oficiais do desafio

### Caso 1

```json
{
  "referencia": "REsp 1.810.170/RS",
  "contexto": "Conforme entendimento pacificado no STJ, a cobranÃ§a de taxa de conveniÃªncia Ã© abusiva ao consumidor..."
}
```

### Caso 2

```json
{
  "referencia": "0815641-45.2025.8.10.0040",
  "contexto": "No Ã¢mbito deste EgrÃ©gio Tribunal de JustiÃ§a do Estado do MaranhÃ£o..."
}
```

## Auditoria

Cada verificaÃ§Ã£o gera uma linha em:

- `app/auditoria/verificacoes.jsonl`

Com:

- entrada
- parse
- evidÃªncia de fonte
- resultado final

## Deploy (Vercel)

1. FaÃ§a push do repositÃ³rio no GitHub.
2. Na Vercel: **Add New... > Project** e selecione o repositÃ³rio.
3. Mantenha as configuraÃ§Ãµes padrÃ£o (hÃ¡ `vercel.json` no projeto).
4. Cadastre variÃ¡veis de ambiente:
   - `DATAJUD_API_KEY`
   - `GEMINI_API_KEYS` 
   - `GROQ_API_KEY` 
   - `CACHE_TTL_SECONDS` (opcional)
5. FaÃ§a o deploy.

Rotas de uso apÃ³s deploy:

- `/ui`
- `/docs`
- `/verificar`
- `/verificar-lote`

## Stack

- FastAPI
- httpx
- DataJud (CNJ)
- STJ SCON
- Gemini API / Groq API

## LimitaÃ§Ãµes atuais

- DependÃªncia de disponibilidade das APIs externas
- Qualidade da camada LLM depende do contexto enviado
- Cobertura de metadados varia por tribunal/fonte

## LicenÃ§a

Defina a licenÃ§a do projeto (ex.: MIT).
