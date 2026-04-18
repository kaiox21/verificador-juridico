# Verificador de Referências Jurídicas

API REST para validar referências jurídicas citadas em peças processuais geradas (ou apoiadas) por IA, reduzindo risco de alucinações e citações inadequadas.

## Status da entrega

Este projeto está alinhado com o **nível avançado** do mini desafio:

- Parser CNJ + tribunais superiores
- Verificação de existência (DataJud / STJ SCON)
- Saída estruturada em 3 dimensões (`existencia`, `conteudo`, `adequacao`)
- Validação de dígito CNJ (módulo 97-10)
- Flags automáticas por metadados (ex.: `EXTINTO_SEM_MERITO`)
- Camada de adequação com LLM (duas passagens)
- Cache básico de existência (TTL)
- Processamento em lote (`POST /verificar-lote`)
- Sugestão de substituição quando a referência é inadequada
- Cobertura ampliada (TRFs, STF, TST)
- Trilha de auditoria em `app/auditoria/verificacoes.jsonl`

## Arquitetura

- **Camada 0 — Parser local**
  - Regex CNJ e superiores
  - Validação de formato
  - Validação do dígito CNJ
  - Flags locais (`FORMATO_INVALIDO`, `ANO_FUTURO`, etc.)
- **Camada 1 — Existência em fonte oficial**
  - DataJud para CNJ
  - STJ SCON para STJ
  - Estratégias para tribunais superiores
- **Camada 2 — Conteúdo e metadados**
  - Assunto, dispositivo, grau, flags TPU
- **Camada 3 — Adequação contextual (LLM)**
  - Inferência da tese da petição
  - Comparação da tese com o julgado real
  - Recomendação final

## Endpoints

- `POST /verificar`
- `POST /verificar-lote`
- `GET /ui`
- `GET /docs`

> Observação importante: a UI (`/ui`) está focada em verificação unitária. O processamento em lote é consumido via API em `/docs` ou Postman/cURL.

## Instalação local

```bash
git clone https://github.com/kaiox21/verificador-juridico
cd verificador-juridico
python -m venv venv
```

Ativação do ambiente virtual:

```bash
# Linux/macOS
source venv/bin/activate

# Windows PowerShell
.\venv\Scripts\Activate.ps1
```

Instale dependências:

```bash
pip install -r requirements.txt
```

Crie o `.env`:

```bash
cp .env.example .env
# Windows sem cp:
copy .env.example .env
```

## Variáveis de ambiente

| Variável | Obrigatória | Descrição |
|---|---|---|
| `DATAJUD_API_KEY` | Sim | Chave da API pública do DataJud |
| `GEMINI_API_KEYS` | Sim | Chaves Gemini separadas por vírgula |
| `GROQ_API_KEY` | Sim | Chave Groq para fallback LLM |
| `CACHE_TTL_SECONDS` | Não | TTL do cache (padrão: 600) |

## Execução

```bash
python -m uvicorn app.main:app --reload
```

Acesse:

- [http://localhost:8000/ui](http://localhost:8000/ui)
- [http://localhost:8000/docs](http://localhost:8000/docs)

## Exemplos de uso

### Verificação unitária

```bash
curl -X POST http://localhost:8000/verificar \
  -H "Content-Type: application/json" \
  -d '{
    "referencia": "REsp 1.810.170/RS",
    "contexto": "Conforme entendimento pacificado no STJ, a cobrança de taxa de conveniência é abusiva ao consumidor."
  }'
```

### Verificação em lote

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
    "contexto": "Trecho único da peça em que as referências são usadas."
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
  "contexto": "Conforme entendimento pacificado no STJ, a cobrança de taxa de conveniência é abusiva ao consumidor..."
}
```

### Caso 2

```json
{
  "referencia": "0815641-45.2025.8.10.0040",
  "contexto": "No âmbito deste Egrégio Tribunal de Justiça do Estado do Maranhão..."
}
```

## Auditoria

Cada verificação gera uma linha em:

- `app/auditoria/verificacoes.jsonl`

Com:

- entrada
- parse
- evidência de fonte
- resultado final

## Deploy (Vercel)

1. Faça push do repositório no GitHub.
2. Na Vercel: **Add New... > Project** e selecione o repositório.
3. Mantenha as configurações padrão (há `vercel.json` no projeto).
4. Cadastre variáveis de ambiente:
   - `DATAJUD_API_KEY`
   - `GEMINI_API_KEYS` 
   - `GROQ_API_KEY` 
   - `CACHE_TTL_SECONDS` (opcional)
5. Faça o deploy.

Rotas de uso após deploy:

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

## Limitações atuais

- Dependência de disponibilidade das APIs externas
- Qualidade da camada LLM depende do contexto enviado
- Cobertura de metadados varia por tribunal/fonte

## Licença

Defina a licença do projeto (ex.: MIT).
