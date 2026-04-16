# Verificador de Referências Jurídicas

API REST para validar referências jurídicas citadas em peças processuais geradas (ou apoiadas) por IA, reduzindo risco de alucinações e citações inadequadas.

## Objetivo do desafio

Verificar uma referência jurídica e seu contexto em três dimensões independentes:
- existência
- conteúdo
- adequação ao argumento da petição

Com resposta estruturada e recomendação final (`MANTER`, `CORRIGIR`, `REVISAR`, `SUBSTITUIR`, `REMOVER`).

## Arquitetura

- **Camada 0 — Parser local**
  - Regex para CNJ e tribunais superiores
  - Validação de formato
  - Validação de dígito verificador CNJ (módulo 97-10)
  - Flags locais (`FORMATO_INVALIDO`, `ANO_FUTURO`, etc.)

- **Camada 1 — Verificação de existência**
  - DataJud (CNJ) para processos CNJ
  - STJ SCON para referências do STJ
  - Cobertura ampliada para TRFs, STF e TST via estratégia de consulta disponível

- **Camada 2 — Extração de metadados**
  - assunto real
  - dispositivo
  - grau
  - flags de movimentos TPU (`EXTINTO_SEM_MERITO`, `TEM_ACORDAO`, `TRANSITADO`)

- **Camada 3 — Adequação contextual (LLM)**
  - inferência da tese da petição
  - comparação tese x julgado real
  - classificação de adequação temática, utilidade do dispositivo e peso precedencial

## Funcionalidades implementadas

### Nível básico
- Parser CNJ + superior
- Verificação de existência (DataJud / SCON)
- Saída estruturada nas três dimensões
- API REST testável

### Nível intermediário
- Validação do dígito verificador CNJ
- Flags automáticas por metadados
- Camada de adequação com LLM
- Cache básico de existência (TTL)

### Nível avançado
- Processamento em lote (`POST /verificar-lote`)
- Sugestão de substituição quando referência está inadequada
- Cobertura ampliada de tribunais (TRFs, STF, TST)
- Trilha de auditoria com evidências (`app/auditoria/verificacoes.jsonl`)

## Endpoints

- `POST /verificar`
- `POST /verificar-lote`
- `GET /ui`
- `GET /docs`

## Instalação local

```bash
git clone https://github.com/seu-usuario/verificador-juridico
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
# No Windows (sem cp): copy .env.example .env
```

## Variáveis de ambiente

| Variável | Obrigatória | Descrição |
|---|---|---|
| `DATAJUD_API_KEY` | Sim | Chave de acesso à API pública do DataJud |
| `GEMINI_API_KEYS` | Não | Lista de chaves Gemini separadas por vírgula (rotação) |
| `GROQ_API_KEY` | Não | Chave Groq para fallback da camada LLM |
| `CACHE_TTL_SECONDS` | Não | Tempo de vida do cache de existência (padrão: 600) |

## Execução

```bash
uvicorn app.main:app --reload
```

Acesse:
- [http://localhost:8000/docs](http://localhost:8000/docs)
- [http://localhost:8000/ui](http://localhost:8000/ui)

## Exemplo de uso

### Requisição unitária

```bash
curl -X POST http://localhost:8000/verificar \
  -H "Content-Type: application/json" \
  -d '{
    "referencia": "REsp 1.810.170/RS",
    "contexto": "Conforme entendimento pacificado no STJ, a cobrança de taxa de conveniência é abusiva ao consumidor, como decidido no REsp 1.810.170/RS."
  }'
```

### Requisição em lote

```bash
curl -X POST http://localhost:8000/verificar-lote \
  -H "Content-Type: application/json" \
  -d '{
    "referencias": [
      "REsp 1.810.170/RS",
      "0815641-45.2025.8.10.0040"
    ],
    "contexto": "Trecho da petição em que as referências são utilizadas."
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

## Casos de teste sugeridos (enunciado)

### Caso 1

```json
{
  "referencia": "REsp 1.810.170/RS",
  "contexto": "Conforme entendimento pacificado no STJ, a cobrança de taxa de conveniência é abusiva ao consumidor, como decidido no REsp 1.810.170/RS."
}
```

Esperado: existe, mas com divergências relevantes (UF/tema/dispositivo), exigindo revisão ou correção.

### Caso 2

```json
{
  "referencia": "0815641-45.2025.8.10.0040",
  "contexto": "No âmbito deste Egrégio Tribunal de Justiça do Estado do Maranhão, cumpre citar o precedente firmado nos autos do processo nº 0815641-45.2025.8.10.0040."
}
```

Esperado: processo localizado, porém de 1º grau e extinto sem resolução de mérito, com peso precedencial baixo/nulo para a tese.

## Auditoria

Cada verificação salva trilha em:

- `app/auditoria/verificacoes.jsonl`

Conteúdo salvo por linha:
- entrada
- parse
- evidência de fonte
- resultado final

## Deploy (Vercel)

1. Faça push do repositório no GitHub.
2. No painel da Vercel, clique em **Add New... > Project** e selecione o repositório.
3. Mantenha as configurações padrão de build (o arquivo `vercel.json` já está configurado).
4. Em **Environment Variables**, cadastre:
   - `DATAJUD_API_KEY`
   - `GEMINI_API_KEYS` (opcional)
   - `GROQ_API_KEY` (opcional)
   - `CACHE_TTL_SECONDS` (opcional)
5. Faça o deploy.

Observação: a rota de interface continua em `/ui` e a documentação em `/docs`.

## Stack

- FastAPI
- httpx
- DataJud (CNJ)
- STJ SCON
- Gemini API / Groq API

## Limitações atuais

- Dependência de disponibilidade das APIs externas
- Variação de qualidade na camada LLM conforme contexto enviado
- Cobertura de metadados pode variar por tribunal/fonte

## Próximos passos

- Testes automatizados (unitários e integração)
- Healthcheck de integrações externas
- Ranking de precedentes sugeridos por aderência temática
- Melhorias contínuas de extração de conteúdo

## Licença

Defina a licença do projeto (ex.: MIT).
