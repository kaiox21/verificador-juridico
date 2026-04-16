# Verificador de Referências Jurídicas

API REST que verifica automaticamente referências jurídicas geradas por IA em peças processuais, detectando alucinações, divergências e inadequações de contexto.

## Problema

Sistemas de IA generativa citam processos com números plausíveis mas inexistentes, com dados trocados (UF errada, classe errada) ou com conteúdo incompatível com o argumento que sustentam. Este serviço automatiza a verificação em quatro camadas independentes.

## Arquitetura

```
Camada 0 — Parser local (regex + dígito verificador CNJ)
Camada 1 — Verificação de existência (Datajud / STJ SCON)
Camada 2 — Extração de metadados (assunto, dispositivo, grau, TPU)
Camada 3 — Adequação contextual (Gemini, duas passagens sequenciais)
```

## Instalação local

```bash
git clone https://github.com/seu-usuario/verificador-juridico
cd verificador-juridico

python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

pip install -r requirements.txt

cp .env.example .env
# Edite .env e adicione sua GEMINI_API_KEY
```

## Rodando

```bash
uvicorn app.main:app --reload
```

Acesse: http://localhost:8000/docs

## Uso

```bash
curl -X POST http://localhost:8000/verificar \
  -H "Content-Type: application/json" \
  -d '{
    "referencia": "REsp 1.810.170/RS",
    "contexto": "Conforme entendimento pacificado no STJ, a cobrança de taxa de conveniência é abusiva ao consumidor, como decidido no REsp 1.810.170/RS."
  }'
```

## Resposta

```json
{
  "referencia_normalizada": "RESP 1810170/RS",
  "tribunal_inferido": "STJ",
  "existencia": {
    "status": "EXISTE_COM_DIVERGENCIA",
    "numero_real": "REsp 1810170/SP",
    "fonte": "STJ SCON",
    "url_fonte": "https://scon.stj.jus.br/...",
    "flags": ["UF_DIVERGENTE: citado RS, real SP"]
  },
  "conteudo": {
    "assunto_real": "Previdência privada complementar",
    "dispositivo": "NAO_CONHECIDO",
    "grau": "superior",
    "flags": []
  },
  "adequacao": {
    "tese_inferida_na_peticao": "Ilegalidade da cobrança de taxa de conveniência ao consumidor",
    "adequacao_tematica": "INADEQUADO",
    "adequacao_dispositivo": "INUTIL",
    "peso_precedencial": "NULO",
    "justificativa": "O julgado trata de previdência privada e foi encerrado sem análise de mérito."
  },
  "recomendacao": "REMOVER",
  "nivel_urgencia": "CRITICO"
}
```

## Variáveis de ambiente

| Variável | Descrição |
|---|---|
| `GEMINI_API_KEY` | Chave da API do Google Gemini (gratuita em aistudio.google.com) |

## Deploy (Render)

1. Faça push do repositório no GitHub
2. Acesse render.com → New Web Service
3. Conecte o repositório
4. Start command: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`
5. Adicione a variável de ambiente `GEMINI_API_KEY`

## Casos de teste

**Caso 1 — REsp com UF errada e assunto incompatível:**
```json
{
  "referencia": "REsp 1.810.170/RS",
  "contexto": "...taxa de conveniência é abusiva ao consumidor, como decidido no REsp 1.810.170/RS..."
}
```
Esperado: UF divergente (RS→SP), assunto incompatível, dispositivo inútil → REMOVER / CRITICO

**Caso 2 — Processo de 1º grau citado como precedente de tribunal:**
```json
{
  "referencia": "0815641-45.2025.8.10.0040",
  "contexto": "...neste Egrégio Tribunal de Justiça do Maranhão, cumpre citar o precedente firmado nos autos do processo nº 0815641-45.2025.8.10.0040..."
}
```
Esperado: processo de 1º grau, extinto por desistência → não é precedente → REMOVER / CRITICO

## Tecnologias

- **FastAPI** — framework da API
- **Datajud (CNJ)** — verificação de processos CNJ
- **STJ SCON** — verificação de acórdãos do STJ
- **Google Gemini** — análise de adequação contextual
- **httpx** — requisições HTTP assíncronas
