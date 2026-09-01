# Manual de Instalação e Uso — Data Deduplication Tool

> **Nota:** No Windows, use `py` em vez de `python` se o comando `python` não for encontrado. O `py` é o Python Launcher for Windows.

## 1. Requisitos Prévios

| Requisito | Versão Mínima | Verificar |
|-----------|---------------|-----------|
| Python | 3.9+ | `py --version` |
| MySQL | 8.0+ | `mysql --version` |
| Git | qualquer | `git --version` |
| pip | atualizado | `py -m pip --version` |

> **Importante:** MySQL 8+ é obrigatório para suporte a `FOR UPDATE SKIP LOCKED`.

---

## 2. Clonar o Repositório

```bash
git clone https://github.com/samuelborges1991/datadeduplication.agildoc.git
cd datadeduplication.agildoc
```

---

## 3. Criar Ambiente Virtual (Recomendado)

```bash
# Windows
py -m venv venv
venv\Scripts\activate

# Linux/Mac (se necessário)
python3 -m venv venv
source venv/bin/activate
```

---

## 4. Instalar Dependências

```bash
pip install -r requirements.txt
```

### Dependências incluídas:

| Pacote | Finalidade |
|--------|------------|
| `python-dotenv` | Leitura do arquivo `.env` |
| `sqlalchemy` | ORM e conexão com banco |
| `pymysql` | Driver MySQL para Python |
| `PyPDF2` | Análise de metadados PDF |
| `python-docx` | Análise de metadados DOCX |
| `openpyxl` | Análise de metadados XLSX |
| `python-pptx` | Análise de metadados PPTX |
| `Pillow` | Análise de metadados de imagens |
| `mutagen` | Análise de metadados de áudio |
| `pandas` | Exportação de relatórios |

---

## 5. Instalar e Configurar o Banco MySQL

### 5.1 Instalar MySQL (se não tiver)

**Opção A — MySQL Community Server (recomendado):**

1. Baixe em: https://dev.mysql.com/downloads/mysql/
2. Execute o instalador e siga o assistente
3. Defina uma senha para o root durante a instalação
4. Marque "Start MySQL Server at System Startup"

**Opção B — XAMPP (mais fácil):**

1. Baixe em: https://www.apachefriends.org/download.html
2. Execute o instalador
3. No painel XAMPP, inicie o serviço "MySQL"

**Opção C — Docker:**

```bash
docker run --name mysql-dedup -e MYSQL_ROOT_PASSWORD=rootpass -p 3306:3306 -d mysql:8.0
```

### 5.2 Verificar se MySQL está rodando

```bash
# Windows (PowerShell)
Get-Service -Name "*mysql*"

# Ou testar conexão
mysql -u root -p -e "SELECT VERSION();"
```

### 5.3 Criar o banco de dados

```bash
mysql -u root -p
```

```sql
CREATE DATABASE datadeduplication CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER 'dedup_user'@'localhost' IDENTIFIED BY 'sua_senha_segura';
GRANT ALL PRIVILEGES ON datadeduplication.* TO 'dedup_user'@'localhost';
FLUSH PRIVILEGES;
EXIT;
```

> As tabelas são criadas automaticamente na primeira execução.

---

## 6. Configurar o Arquivo `.env`

```bash
cp .env.example .env
```

Edite o `.env` com suas configurações:

```env
# Diretório raiz para análise
RAIZ_ANALISE=C:\dados

# MySQL
DB_HOST=localhost
DB_PORT=3306
DB_USER=dedup_user
DB_PASSWORD=sua_senha_segura
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

---

## 7. Uso Básico

### 7.1 Verificar ajuda

```bash
py -m datadeduplication --help
```

### 7.2 Fluxo Completo

O uso envolve 4 etapas que rodam em **terminais separados**:

---

#### Terminal 1 — Varredura (Scan)

```bash
# Varredura completa do diretório
py -m datadeduplication scan --path "C:\dados"

# Retomar varredura interrompida
py -m datadeduplication scan --path "C:\dados" --resume
```

---

#### Terminal 2 — Orquestrador

```bash
# Rodar continuamente (padrão: 30s entre ciclos)
py -m datadeduplication orchestrate

# Com intervalo customizado (60 segundos)
py -m datadeduplication orchestrate --interval 60
```

---

#### Terminal 3 — Worker de Hash (SHA-256)

```bash
# Worker padrão
py -m datadeduplication worker-hash

# Com batch size customizado
py -m datadeduplication worker-hash --batch-size 200
```

---

#### Terminal 4 — Worker de Análise de Metadata

```bash
# Worker padrão
py -m datadeduplication worker-analyze

# Com batch size customizado
py -m datadeduplication worker-analyze --batch-size 100
```

---

### 7.3 Análises e Relatórios

```bash
# Arquivos duplicados (mesmo hash SHA-256)
py -m datadeduplication analyze --type duplicates

# Arquivos duplicados com tamanho mínimo (1MB)
py -m datadeduplication analyze --type duplicates --min-size 1048576

# Arquivos grandes (>500MB)
py -m datadeduplication analyze --type large --limit 500MB

# Arquivos não acessados há mais de 1 ano
py -m datadeduplication analyze --type old --days 365

# Arquivos temporários (.tmp, .bak, .old, .log, etc.)
py -m datadeduplication analyze --type temp

# Arquivos vazios (0 bytes)
py -m datadeduplication analyze --type empty

# Busca por conteúdo nos metadados
py -m datadeduplication analyze --type search --keyword "contrato"

# Exportar relatório para JSON
py -m datadeduplication analyze --type duplicates --output duplicados.json

# Exportar relatório para CSV
py -m datadeduplication analyze --type large --output grandes.csv --format csv
```

---

### 7.4 Quarentena

```bash
# Listar arquivos em quarentena
py -m datadeduplication quarantine --list

# Simular quarentena (dry-run — não move nada)
py -m datadeduplication quarantine --from-report duplicados.json --dry-run

# Mover arquivos para quarentena
py -m datadeduplication quarantine --from-report duplicados.json
```

---

### 7.5 Limpeza (Exclusão Permanente)

```bash
# Excluir permanentemente (REQUER --confirm)
py -m datadeduplication clean --from-report duplicados.json --confirm
```

> **Atenção:** Esta operação é irreversível. Use sempre `quarantine --dry-run` antes.

---

## 8. Exemplo de Fluxo Completo

```bash
# 1. Clonar e instalar
git clone https://github.com/samuelborges1991/datadeduplication.agildoc.git
cd datadeduplication.agildoc
py -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
# Editar .env com suas configurações

# 2. Varredura (Terminal 1)
py -m datadeduplication scan --path "C:\Users\Documentos"

# 3. Orquestrador (Terminal 2)
py -m datadeduplication orchestrate

# 4. Workers (Terminais 3 e 4)
py -m datadeduplication worker-hash
py -m datadeduplication worker-analyze

# 5. Após workers finalizarem, gerar relatórios
py -m datadeduplication analyze --type duplicates --output duplicados.json
py -m datadeduplication analyze --type old --days 180 --output antigos.json
py -m datadeduplication analyze --type temp --output temporarios.json

# 6. Revisar antes de agir
py -m datadeduplication quarantine --from-report duplicados.json --dry-run

# 7. Mover para quarentena
py -m datadeduplication quarantine --from-report duplicados.json

# 8. Excluir (após revisão cuidadosa)
py -m datadeduplication clean --from-report duplicados.json --confirm
```

---

## 9. Estrutura do Projeto

```
datadeduplication.agildoc/
├── src/
│   └── datadeduplication/
│       ├── __init__.py          # Versão do pacote
│       ├── __main__.py          # CLI (argparse)
│       ├── config.py            # Carrega .env
│       ├── database.py          # Conexão MySQL
│       ├── models.py            # ORM (Arquivo, Tarefa, Log)
│       ├── enums.py             # TaskType, TaskStatus
│       ├── scanner.py           # Varredura de diretórios
│       ├── orchestrator.py      # Gerencia fila de tarefas
│       ├── workers/
│       │   ├── base.py          # Worker base (FOR UPDATE SKIP LOCKED)
│       │   ├── hash_worker.py   # SHA-256
│       │   └── analyze_worker.py # Metadata (PDF, imagens, etc.)
│       ├── analyzer.py          # Consultas (duplicados, grandes, etc.)
│       └── quarantine.py        # Quarentena de arquivos
├── tests/                       # Testes pytest
├── .env.example                 # Template de configuração
├── requirements.txt             # Dependências
└── README.md                    # Documentação principal
```

---

## 10. Troubleshooting

### Erro: `ModuleNotFoundError: No module named 'datadeduplication'`

```bash
# Execute a partir da raiz do projeto
py -m datadeduplication --help
```

### Erro: `Access denied for user` (MySQL)

```bash
# Verifique credenciais no .env
# Teste conexão manualmente:
mysql -u dedup_user -p datadeduplication
```

### Erro: `Table 'datadeduplication.arquivos' doesn't exist`

As tabelas são criadas automaticamente. Verifique se o banco existe:

```sql
SHOW DATABASES;
USE datadeduplication;
SHOW TABLES;
```

### Erro: `FOR UPDATE SKIP LOCKED` não suportado

Requer MySQL 8.0+. Verifique versão:

```sql
SELECT VERSION();
```

### Worker não processa tarefas

Verifique se o orquestrador está rodando (Terminal 2). Ele move tarefas de `pending` para `queued`.

---

## 11. Comandos Rápidos

| Ação | Comando |
|------|---------|
| Verificar ajuda | `py -m datadeduplication --help` |
| Verificar versão | `py -c "import datadeduplication; print(datadeduplication.__version__)"` |
| Rodar testes | `py -m pytest tests/ -v` |
| Limpar cache Python | `Get-ChildItem -Recurse -Directory -Filter __pycache__ \| Remove-Item -Recurse -Force` |
