import asyncio
from pathlib import Path

import typer

from call_fraud_detector.audio import SUPPORTED_EXTENSIONS

app = typer.Typer(name="cfd", help="Call Fraud Detector CLI")


def _run(coro):
    return asyncio.run(coro)


@app.command()
def analyze(file: Path = typer.Argument(..., help="Path to audio file")):
    """Analyze a single audio file for fraud."""
    if not file.exists():
        typer.echo(f"File not found: {file}")
        raise typer.Exit(1)
    if file.suffix.lower() not in SUPPORTED_EXTENSIONS:
        typer.echo(f"Unsupported format: {file.suffix}")
        raise typer.Exit(1)

    async def _do():
        from call_fraud_detector.analyzer import analyze_file
        from call_fraud_detector.database import async_session

        async with async_session() as session:
            call, result = await analyze_file(file, "cli", session)
            status = "FRAUD" if result.is_fraud else "CLEAN"
            typer.echo(f"[{status}] Score: {result.fraud_score:.0%}")
            if result.fraud_categories:
                typer.echo(f"Categories: {', '.join(result.fraud_categories)}")
            if result.reasons:
                typer.echo("Reasons:")
                for r in result.reasons:
                    typer.echo(f"  - {r}")
            if result.transcript:
                typer.echo(f"\nTranscript:\n{result.transcript}")

    _run(_do())


@app.command()
def analyze_dir(directory: Path = typer.Argument(..., help="Directory with audio files")):
    """Batch analyze all audio files in a directory."""
    if not directory.is_dir():
        typer.echo(f"Not a directory: {directory}")
        raise typer.Exit(1)

    files = [f for f in directory.iterdir() if f.suffix.lower() in SUPPORTED_EXTENSIONS]
    if not files:
        typer.echo("No supported audio files found.")
        raise typer.Exit(0)

    typer.echo(f"Found {len(files)} audio file(s)")

    async def _do():
        from call_fraud_detector.analyzer import analyze_file
        from call_fraud_detector.database import async_session

        async with async_session() as session:
            for f in files:
                try:
                    call, result = await analyze_file(f, "cli", session)
                    status = "FRAUD" if result.is_fraud else "CLEAN"
                    typer.echo(f"  [{status}] {f.name} — {result.fraud_score:.0%}")
                except Exception as e:
                    typer.echo(f"  [ERROR] {f.name}: {e}")

    _run(_do())


@app.command()
def watch(directory: Path = typer.Option(None, help="Directory to watch")):
    """Watch a directory for new audio files and analyze them."""
    from call_fraud_detector.watcher import start_watcher

    start_watcher(directory)


@app.command("list")
def list_calls(limit: int = typer.Option(10, help="Number of recent calls")):
    """Show recent analysis results."""

    async def _do():
        from sqlalchemy import select
        from sqlalchemy.orm import joinedload

        from call_fraud_detector.database import async_session
        from call_fraud_detector.models import Call

        async with async_session() as session:
            query = (
                select(Call)
                .options(joinedload(Call.analysis))
                .order_by(Call.created_at.desc())
                .limit(limit)
            )
            calls = (await session.execute(query)).unique().scalars().all()
            if not calls:
                typer.echo("No calls found.")
                return
            for c in calls:
                if c.analysis:
                    status = "FRAUD" if c.analysis.is_fraud else "CLEAN"
                    typer.echo(f"[{status}] {c.filename} — {c.analysis.fraud_score:.0%} ({c.source}, {c.created_at})")
                else:
                    typer.echo(f"[PENDING] {c.filename} ({c.source}, {c.created_at})")

    _run(_do())


@app.command()
def stats():
    """Show fraud detection statistics."""

    async def _do():
        from sqlalchemy import func, select

        from call_fraud_detector.database import async_session
        from call_fraud_detector.models import AnalysisResult, Call

        async with async_session() as session:
            total = (await session.execute(select(func.count(Call.id)))).scalar() or 0
            fraud = (
                await session.execute(
                    select(func.count(AnalysisResult.id)).where(AnalysisResult.is_fraud.is_(True))
                )
            ).scalar() or 0
            avg = (await session.execute(select(func.avg(AnalysisResult.fraud_score)))).scalar()

            typer.echo(f"Total calls:    {total}")
            typer.echo(f"Fraud detected: {fraud}")
            typer.echo(f"Clean calls:    {total - fraud}")
            typer.echo(f"Avg score:      {avg:.1%}" if avg else "Avg score:      N/A")

    _run(_do())


@app.command()
def serve(host: str = "0.0.0.0", port: int = 8080):
    """Start the web server."""
    import uvicorn

    from call_fraud_detector.app import create_app

    application = create_app()
    uvicorn.run(application, host=host, port=port)


if __name__ == "__main__":
    app()
