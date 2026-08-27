# Design Spec: Data Deduplication Tool

## Overview

Ferramenta Python para análise completa de diretórios Windows, identificando arquivos candidatos à remoção via deduplicação, limpeza e inventário. Arquitetura com orquestrador e workers separados, comunicando via task queue no banco MySQL.

## Decisões de Design

| Decisão | Escolha |
|---------|---------|
| Volume | >1M de arquivos |
| Objetivo | Inventário completo (deduplicação + limpeza) |
| Extração | Metadata leve (sem texto completo, sem Tika) |
| Banco | MySQL com batch inserts de 1000 |
| Quarentena | Manual (mover, exclusão sempre manual) |
| Paralelismo | Threads para I/O + Processos para CPU |
| Arquitetura | Orquestrador + Workers via task queue no banco |

## Estrutura de Módulos

```
datadeduplication/
├── src/
│   └── datadeduplication/
│       ├── __init__.py
│       ├── __main__.py        # CLI entry point
│       ├── config.py          # Carrega .env, dataclass Config
│       ├── database.py        # SQLAlchemy engine, session, criação de tabelas
│       ├── models.py          # SQLAlchemy ORM models (Arquivo, Tarefa, LogProcessamento)
│       ├── enums.py           # TaskType, TaskStatus enums
│       ├── scanner.py         # Walk + metadata básica + insert batch
│       ├── orchestrator.py    # Gerencia prioridade, retry, monitoramento
│       ├── workers/
│       │   ├── __init__.py
│       │   ├── base.py        # Worker base class
│       │   ├── hash_worker.py # SHA-256 computation
│       │   └── analyze_worker.py  # Metadata analysis per file type
│       ├── analyzer.py        # Consultas: duplicados, grandes, antigos, etc.
│       └── quarantine.py      # Mover para pasta de quarentena
├── .env.example
├── requirements.txt
└── README.md
```

## Arquitetura: Orquestrador + Workers via Task Queue

```
┌─────────────┐     ┌──────────────┐     ┌─────────────────┐
│  scan        │────▶│  MySQL       │◀────│  orchestrate     │
│  (coleta)    │     │  (tarefas)   │     │  (prioridade)    │
└─────────────┘     └──────┬───────┘     └─────────────────┘
                           │
              ┌────────────┼────────────┐
              ▼            ▼            ▼
        ┌──────────┐ ┌──────────┐ ┌──────────┐
        │ worker-  │ │ worker-  │ │ (futuro) │
        │ hash     │ │ analyze  │ │ cleanup  │
        └──────────┘ └──────────┘ └──────────┘
```

### Fluxo

1. **`scan`** — Varre diretório recursivamente, insere metadados básicos em batch de 1000 na tabela `arquivos`. Cria tarefas `PENDING` na tabela `tarefas` (uma `hash` + uma `analyze` por arquivo).

2. **`orchestrate`** — Roda continuamente ou periodicamente:
   - Lê tarefas `PENDING`
   - Define prioridade (configurável: arquivos menores primeiro, mais recentes, etc.)
   - Muda status para `QUEUED`
   - Monitora tarefas `ERROR` → decide retry (max tentativas configurável)
   - Log de progresso

3. **`worker-hash`** — Processo independente:
   - Poll: `SELECT ... FROM tarefas WHERE tipo='hash' AND status='QUEUED' ORDER BY prioridade LIMIT batch_size FOR UPDATE SKIP LOCKED`
   - Calcula SHA-256
   - Atualiza `arquivos.hash_sha256`
   - Marca tarefa como `DONE`

4. **`worker-analyze`** — Processo independente:
   - Mesmo padrão, tipo=`analyze`
   - Coleta metadata leve por tipo de arquivo
   - Atualiza `metadados_json`
   - Marca tarefa como `DONE`

### Concorrência

`FOR UPDATE SKIP LOCKED` (MySQL 8+) garante que workers concorrentes não peguem a mesma tarefa.

## Schema do Banco

### Tabela `arquivos`

```sql
CREATE TABLE arquivos (
    id INT AUTO_INCREMENT PRIMARY KEY,
    caminho VARCHAR(1024) NOT NULL,
    nome VARCHAR(255) NOT NULL,
    extensao VARCHAR(20),
    tamanho BIGINT NOT NULL,
    data_criacao DATETIME,
    data_modificacao DATETIME,
    data_acesso DATETIME,
    atributos VARCHAR(255),
    proprietario VARCHAR(255),
    hash_sha256 CHAR(64),
    tipo_mime VARCHAR(100),
    metadados_json JSON,
    data_processamento TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uk_caminho (caminho(255)),
    INDEX idx_hash (hash_sha256),
    INDEX idx_tamanho (tamanho),
    INDEX idx_data_modificacao (data_modificacao),
    INDEX idx_extensao (extensao)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
```

### Tabela `tarefas`

```sql
CREATE TABLE tarefas (
    id INT AUTO_INCREMENT PRIMARY KEY,
    arquivo_id INT NOT NULL,
    tipo ENUM('hash','analyze','cleanup') NOT NULL,
    status ENUM('pending','queued','running','done','error','retry') DEFAULT 'pending',
    prioridade INT DEFAULT 0,
    tentativas INT DEFAULT 0,
    max_tentativas INT DEFAULT 3,
    mensagem_erro TEXT,
    worker_id VARCHAR(100),
    data_criacao TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    data_inicio DATETIME,
    data_conclusao DATETIME,
    FOREIGN KEY (arquivo_id) REFERENCES arquivos(id) ON DELETE CASCADE,
    INDEX idx_status_tipo (status, tipo),
    INDEX idx_prioridade (prioridade)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
```

### Tabela `logs_processamento`

```sql
CREATE TABLE logs_processamento (
    id INT AUTO_INCREMENT PRIMARY KEY,
    data_inicio DATETIME NOT NULL,
    data_fim DATETIME,
    total_arquivos BIGINT DEFAULT 0,
    total_bytes BIGINT DEFAULT 0,
    status ENUM('running','completed','failed') DEFAULT 'running',
    mensagem_erro TEXT,
    comando VARCHAR(50)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
```

## Análise de Metadata (sem extração de texto)

| Tipo | Metadata coletada |
|------|------------------|
| PDF | páginas, autor, título, versão PDF |
| DOCX | páginas, autor, palavras, seções |
| XLSX | sheets, linhas, colunas |
| PPTX | slides, autor |
| TXT/CSV/JSON | linhas, tamanho em caracteres |
| Imagens | dimensões (LxA), EXIF (câmera, data, GPS) |
| Áudio | duração, bitrate, codec, sample rate |
| Vídeo | duração, resolução, codec, bitrate |

### Bibliotecas por tipo

| Tipo | Biblioteca |
|------|-----------|
| PDF | PyPDF2 |
| DOCX | python-docx |
| XLSX | openpyxl |
| PPTX | python-pptx |
| TXT/CSV/JSON | built-in open() |
| Imagens | Pillow |
| Áudio | mutagen |
| Vídeo | ffprobe (subprocess) |

### Controle via .env

```
ANALISAR_METADATA=true
TAMANHO_MAX_PARA_ANALISE=52428800
TIPOS_ANALISE=pdf,docx,xlsx,pptx,txt,jpg,png,mp3,mp4
```

## CLI (argparse)

```
python -m datadeduplication scan --path "C:\dados" [--resume]  # resume: retoma do último checkpoint no banco, pulando arquivos já registrados
python -m datadeduplication orchestrate [--interval 30]
python -m datadeduplication worker-hash [--batch-size 100] [--threads 4]
python -m datadeduplication worker-analyze [--batch-size 50] [--processes 4]
python -m datadeduplication analyze --type duplicates [--min-size 1048576]
python -m datadeduplication analyze --type large [--limit 1GB]
python -m datadeduplication analyze --type old [--days 365]
python -m datadeduplication analyze --type temp
python -m datadeduplication analyze --type empty
python -m datadeduplication analyze --type search --keyword "contrato"
python -m datadeduplication quarantine --from-report report.json [--dry-run]  # report.json: saída do comando analyze
python -m datadeduplication clean --from-report report.json [--confirm]  # --confirm obrigatório para exclusão
```

## Analisador — Consultas

| Método | Descrição |
|--------|-----------|
| `find_duplicates()` | Arquivos com mesmo hash, agrupados, sugere manter mais antigo |
| `find_large(min_bytes)` | Arquivos acima do limite |
| `find_old(days)` | Não acessados há X dias |
| `find_temp()` | Extensões .tmp, .bak, .old, .log, etc. |
| `find_empty()` | Tamanho 0 |
| `search_content(keyword)` | Busca em metadados_json |

Todos retornam `list[dict]` e podem ser exportados para JSON/CSV.

## Quarentena

- `--dry-run`: lista o que seria movido
- Sem `--dry-run`: move para `QUARENTENA_PATH` do .env
- `clean` sempre pede `--confirm`

## Segurança

- Variáveis de ambiente via `.env` (python-dotenv), nunca hardcoded
- Tratamento de erros de permissão durante varredura
- Não seguir symlinks/junções (configurável)
- Batch inserts para não sobrecarregar memória
- `FOR UPDATE SKIP LOCKED` para concorrência segura

## Dependências (requirements.txt)

```
python-dotenv
sqlalchemy
pymysql
PyPDF2
python-docx
openpyxl
python-pptx
Pillow
mutagen
pandas
```

## .env.example

```env
# Diretório raiz para análise
RAIZ_ANALISE=C:\dados

# MySQL
DB_HOST=localhost
DB_PORT=3306
DB_USER=root
DB_PASSWORD=
DB_NAME=datadeduplication

# Scanner
BATCH_SIZE=1000
SEGUIR_SYMLINKS=false

# Análise de metadata
ANALISAR_METADATA=true
TAMANHO_MAX_PARA_ANALISE=52428800
TIPOS_ANALISE=pdf,docx,xlsx,pptx,txt,jpg,png,mp3,mp4

# Quarentena
QUARENTENA_PATH=C:\quarentena

# Orquestrador
ORCHESTRATE_INTERVAL=30
MAX_TENTATIVAS=3

# Workers
WORKER_HASH_BATCH=100
WORKER_HASH_THREADS=4
WORKER_ANALYZE_BATCH=50
WORKER_ANALYZE_PROCESSES=4

# Logging
LOG_LEVEL=INFO
LOG_FILE=datadeduplication.log
```
