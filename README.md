# Data Deduplication Tool

Ferramenta Python para análise completa de diretórios Windows, identificando arquivos candidatos à remoção via deduplicação, limpeza e inventário.

## Arquitetura

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

## Instalação

```bash
pip install -r requirements.txt
```

## Configuração

Copie `.env.example` para `.env` e configure:

```bash
cp .env.example .env
```

### Variáveis de Ambiente

| Variável | Descrição | Padrão |
|----------|-----------|--------|
| `RAIZ_ANALISE` | Diretório raiz para análise | `C:\dados` |
| `DB_HOST` | Host MySQL | `localhost` |
| `DB_PORT` | Porta MySQL | `3306` |
| `DB_USER` | Usuário MySQL | `root` |
| `DB_PASSWORD` | Senha MySQL | (vazio) |
| `DB_NAME` | Nome do banco | `datadeduplication` |
| `BATCH_SIZE` | Tamanho do batch para inserts | `1000` |
| `ANALISAR_METADATA` | Habilitar análise de metadata | `true` |
| `TAMANHO_MAX_PARA_ANALISE` | Tamanho máximo para análise (bytes) | `52428800` (50MB) |
| `QUARENTENA_PATH` | Pasta de quarentena | `C:\quarentena` |

## Uso

### 1. Varredura (Scan)

```bash
# Varredura completa
python -m datadeduplication scan --path "C:\dados"

# Retomar varredura interrompida
python -m datadeduplication scan --path "C:\dados" --resume
```

### 2. Orquestrador

```bash
# Rodar orquestrador continuamente
python -m datadeduplication orchestrate

# Com intervalo customizado (segundos)
python -m datadeduplication orchestrate --interval 60
```

### 3. Workers

```bash
# Worker de hash (SHA-256)
python -m datadeduplication worker-hash --batch-size 100

# Worker de análise de metadata
python -m datadeduplication worker-analyze --batch-size 50
```

### 4. Análises

```bash
# Arquivos duplicados
python -m datadeduplication analyze --type duplicates

# Arquivos grandes (>100MB)
python -m datadeduplication analyze --type large --limit 100MB

# Arquivos antigos (não acessados há >1 ano)
python -m datadeduplication analyze --type old --days 365

# Arquivos temporários
python -m datadeduplication analyze --type temp

# Arquivos vazios
python -m datadeduplication analyze --type empty

# Busca por conteúdo
python -m datadeduplication analyze --type search --keyword "contrato"

# Exportar relatório
python -m datadeduplication analyze --type duplicates --output report.json --format json
```

### 5. Quarentena

```bash
# Listar arquivos em quarentena
python -m datadeduplication quarantine --list

# Simular quarentena (dry-run)
python -m datadeduplication quarantine --from-report report.json --dry-run

# Mover para quarentena
python -m datadeduplication quarantine --from-report report.json
```

### 6. Limpeza

```bash
# Excluir permanentemente (requer --confirm)
python -m datadeduplication clean --from-report report.json --confirm
```

## Fluxo Recomendado

1. **Scan**: `python -m datadeduplication scan --path "C:\dados"`
2. **Orchestrate**: `python -m datadeduplication orchestrate` (em terminal separado)
3. **Workers**: Inicie workers em terminais separados:
   - `python -m datadeduplication worker-hash`
   - `python -m datadeduplication worker-analyze`
4. **Análise**: Após workers completarem:
   - `python -m datadeduplication analyze --type duplicates --output duplicates.json`
   - `python -m datadeduplication analyze --type old --output old_files.json`
5. **Quarentena**: `python -m datadeduplication quarantine --from-report duplicates.json --dry-run`
6. **Limpeza**: `python -m datadeduplication clean --from-report duplicates.json --confirm`

## Requisitos

- Python 3.10+
- MySQL 8+ (para `FOR UPDATE SKIP LOCKED`)
- Windows (para atributos de arquivo e proprietário)

## Dependências

- `python-dotenv` - Carregamento de variáveis de ambiente
- `sqlalchemy` - ORM e conexão com banco
- `pymysql` - Driver MySQL
- `PyPDF2` - Análise de PDF
- `python-docx` - Análise de DOCX
- `openpyxl` - Análise de XLSX
- `python-pptx` - Análise de PPTX
- `Pillow` - Análise de imagens
- `mutagen` - Análise de áudio
- `pandas` - Exportação de relatórios