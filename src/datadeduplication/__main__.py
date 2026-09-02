"""CLI entry point for datadeduplication tool."""

import argparse
import json
import logging
import sys
from pathlib import Path

from datadeduplication.analyzer import Analyzer
from datadeduplication.config import Config
from datadeduplication.database import Database
from datadeduplication.orchestrator import Orchestrator
from datadeduplication.quarantine import QuarantineManager
from datadeduplication.scanner import Scanner
from datadeduplication.workers.analyze_worker import AnalyzeWorker
from datadeduplication.workers.hash_worker import HashWorker


def setup_logging(config: Config) -> None:
    """Configure logging to file and console."""
    log_format = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"

    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(config.log_level)
    console_handler.setFormatter(logging.Formatter(log_format))

    # File handler
    file_handler = logging.FileHandler(config.log_file, encoding="utf-8")
    file_handler.setLevel("DEBUG")
    file_handler.setFormatter(logging.Formatter(log_format))

    # Root logger
    root_logger = logging.getLogger()
    root_logger.setLevel("DEBUG")
    root_logger.addHandler(console_handler)
    root_logger.addHandler(file_handler)


def cmd_scan(args, config: Config, db: Database) -> None:
    """Execute scan command."""
    scanner = Scanner(config, db)
    try:
        stats = scanner.scan(resume=args.resume)
        print(json.dumps(stats, indent=2))
    except KeyboardInterrupt:
        print("\nScan interrupted. Saving progress...")
        # Scanner already handles saving partial batch via signal handler
        print("Use --resume to continue from where it stopped.")
    except Exception as e:
        logging.error(f"Scan failed: {e}", exc_info=True)
        print(f"Error: {e}")
        sys.exit(1)


def cmd_orchestrate(args, config: Config, db: Database) -> None:
    """Execute orchestrate command."""
    orchestrator = Orchestrator(config, db)
    try:
        orchestrator.run(interval=args.interval)
    except KeyboardInterrupt:
        orchestrator.stop()
        print("\nOrchestrator stopped.")


def cmd_worker_hash(args, config: Config, db: Database) -> None:
    """Execute hash worker command."""
    worker = HashWorker(config, db)
    try:
        result = worker.run(batch_size=args.batch_size)
        print(json.dumps(result, indent=2))
    except KeyboardInterrupt:
        worker.stop()
        print("\nWorker stopped.")


def cmd_worker_analyze(args, config: Config, db: Database) -> None:
    """Execute analyze worker command."""
    worker = AnalyzeWorker(config, db)
    try:
        result = worker.run(batch_size=args.batch_size)
        print(json.dumps(result, indent=2))
    except KeyboardInterrupt:
        worker.stop()
        print("\nWorker stopped.")


def cmd_analyze(args, config: Config, db: Database) -> None:
    """Execute analyze command."""
    analyzer = Analyzer(config, db)

    analysis_type = args.type
    output_format = args.format
    output_path = args.output

    if analysis_type == "duplicates":
        data = analyzer.find_duplicates(min_size=args.min_size)
    elif analysis_type == "large":
        limit_bytes = parse_size(args.limit)
        data = analyzer.find_large(min_bytes=limit_bytes)
    elif analysis_type == "old":
        data = analyzer.find_old(days=args.days)
    elif analysis_type == "temp":
        data = analyzer.find_temp()
    elif analysis_type == "empty":
        data = analyzer.find_empty()
    elif analysis_type == "search":
        if not args.keyword:
            print("Error: --keyword required for search analysis")
            sys.exit(1)
        data = analyzer.search_content(keyword=args.keyword)
    else:
        print(f"Error: Unknown analysis type: {analysis_type}")
        sys.exit(1)

    print(f"Found {len(data)} results")

    if output_path:
        path = analyzer.export_report(data, output_path, format=output_format)
        print(f"Report saved to: {path}")
    else:
        print(json.dumps(data, indent=2, default=str))


def cmd_quarantine(args, config: Config, db: Database) -> None:
    """Execute quarantine command."""
    quarantine_mgr = QuarantineManager(config, db)

    if args.list:
        items = quarantine_mgr.list_quarantine()
        print(json.dumps(items, indent=2))
        return

    if not args.from_report:
        print("Error: --from-report required")
        sys.exit(1)

    with open(args.from_report) as f:
        report = json.load(f)

    file_ids = [item["id"] for item in report if "id" in item]

    if not file_ids:
        print("No files to quarantine")
        return

    result = quarantine_mgr.move_to_quarantine(file_ids, dry_run=args.dry_run)
    print(json.dumps(result, indent=2))


def cmd_clean(args, config: Config, db: Database) -> None:
    """Execute clean command (permanent deletion)."""
    if not args.confirm:
        print("Error: --confirm required for permanent deletion")
        sys.exit(1)

    if not args.from_report:
        print("Error: --from-report required")
        sys.exit(1)

    with open(args.from_report) as f:
        report = json.load(f)

    file_paths = [item["caminho"] for item in report if "caminho" in item]

    if not file_paths:
        print("No files to delete")
        return

    print(f"WARNING: About to permanently delete {len(file_paths)} files")
    for path in file_paths[:10]:
        print(f"  - {path}")
    if len(file_paths) > 10:
        print(f"  ... and {len(file_paths) - 10} more")

    confirm = input("Type 'DELETE' to confirm: ")
    if confirm != "DELETE":
        print("Cancelled")
        return

    deleted = 0
    errors = 0
    for path in file_paths:
        try:
            Path(path).unlink()
            deleted += 1
        except Exception as e:
            print(f"Error deleting {path}: {e}")
            errors += 1

    print(f"Deleted: {deleted}, Errors: {errors}")


def parse_size(size_str: str) -> int:
    """Parse size string like '1GB', '500MB' to bytes."""
    size_str = size_str.upper().strip()
    multipliers = {
        "B": 1,
        "KB": 1024,
        "MB": 1048576,
        "GB": 1073741824,
        "TB": 1099511627776,
    }

    for suffix, multiplier in multipliers.items():
        if size_str.endswith(suffix):
            number = size_str[:-len(suffix)]
            return int(float(number) * multiplier)

    return int(size_str)


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Data Deduplication Tool - File analysis and cleanup",
        prog="datadeduplication",
    )
    parser.add_argument("--env", help="Path to .env file", default=None)

    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # Scan command
    scan_parser = subparsers.add_parser("scan", help="Scan directory and collect file metadata")
    scan_parser.add_argument("--path", help="Directory path to scan (overrides .env)")
    scan_parser.add_argument("--resume", action="store_true", help="Resume from last checkpoint")

    # Orchestrate command
    orch_parser = subparsers.add_parser("orchestrate", help="Run task orchestrator")
    orch_parser.add_argument("--interval", type=int, default=30, help="Seconds between iterations")

    # Worker hash command
    hash_parser = subparsers.add_parser("worker-hash", help="Run hash computation worker")
    hash_parser.add_argument("--batch-size", type=int, default=100, help="Tasks per batch")

    # Worker analyze command
    analyze_parser = subparsers.add_parser("worker-analyze", help="Run metadata analysis worker")
    analyze_parser.add_argument("--batch-size", type=int, default=50, help="Tasks per batch")

    # Analyze command
    analysis_parser = subparsers.add_parser("analyze", help="Run analysis queries")
    analysis_parser.add_argument("--type", required=True, choices=[
        "duplicates", "large", "old", "temp", "empty", "search"
    ], help="Analysis type")
    analysis_parser.add_argument("--min-size", type=int, default=0, help="Min size for duplicates")
    analysis_parser.add_argument("--limit", default="100MB", help="Size limit for large files")
    analysis_parser.add_argument("--days", type=int, default=365, help="Days for old files")
    analysis_parser.add_argument("--keyword", help="Search keyword")
    analysis_parser.add_argument("--output", help="Output file path")
    analysis_parser.add_argument("--format", choices=["json", "csv"], default="json", help="Output format")

    # Quarantine command
    quarantine_parser = subparsers.add_parser("quarantine", help="Manage file quarantine")
    quarantine_parser.add_argument("--from-report", help="JSON report file")
    quarantine_parser.add_argument("--dry-run", action="store_true", help="List without moving")
    quarantine_parser.add_argument("--list", action="store_true", help="List quarantined files")

    # Clean command
    clean_parser = subparsers.add_parser("clean", help="Permanently delete files")
    clean_parser.add_argument("--from-report", required=True, help="JSON report file")
    clean_parser.add_argument("--confirm", action="store_true", help="Confirm deletion")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    # Load config
    config = Config.from_env(args.env)

    # Override scan path if provided
    if hasattr(args, "path") and args.path:
        config.raiz_analise = Path(args.path)

    # Setup logging
    setup_logging(config)

    # Initialize database
    db = Database(config)
    db.create_tables()

    # Execute command
    commands = {
        "scan": cmd_scan,
        "orchestrate": cmd_orchestrate,
        "worker-hash": cmd_worker_hash,
        "worker-analyze": cmd_worker_analyze,
        "analyze": cmd_analyze,
        "quarantine": cmd_quarantine,
        "clean": cmd_clean,
    }

    try:
        commands[args.command](args, config, db)
    except KeyboardInterrupt:
        print("\nOperation cancelled.")
    except Exception as e:
        logging.error(f"Command failed: {e}", exc_info=True)
        print(f"Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
