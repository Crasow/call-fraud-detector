import asyncio
import uuid
from pathlib import Path
from typing import Optional

import typer

from call_analyzer.audio import SUPPORTED_EXTENSIONS

app = typer.Typer(name="ca", help="Call Analyzer CLI")
profile_app = typer.Typer(name="profile", help="Manage analysis profiles")
app.add_typer(profile_app)


def _run(coro):
    return asyncio.run(coro)


@app.command()
def analyze(
    file: Path = typer.Argument(..., help="Path to audio file"),
    profile_id: Optional[str] = typer.Option(None, "--profile-id", help="Profile UUID to use for analysis"),
):
    """Analyze a single audio file for fraud."""
    if not file.exists():
        typer.echo(f"File not found: {file}")
        raise typer.Exit(1)
    if file.suffix.lower() not in SUPPORTED_EXTENSIONS:
        typer.echo(f"Unsupported format: {file.suffix}")
        raise typer.Exit(1)

    pid = uuid.UUID(profile_id) if profile_id else None

    async def _do():
        import json as _json
        from call_analyzer.analyzer import analyze_file
        from call_analyzer.database import async_session

        async with async_session() as session:
            call, result = await analyze_file(file, "cli", session, profile_id=pid)
            if hasattr(result, 'is_fraud'):
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
            else:
                typer.echo("[PROFILE] Analysis complete")
                typer.echo(_json.dumps(result.data, indent=2, ensure_ascii=False))

    _run(_do())


@app.command()
def analyze_dir(
    directory: Path = typer.Argument(..., help="Directory with audio files"),
    profile_id: Optional[str] = typer.Option(None, "--profile-id", help="Profile UUID to use for analysis"),
):
    """Batch analyze all audio files in a directory."""
    if not directory.is_dir():
        typer.echo(f"Not a directory: {directory}")
        raise typer.Exit(1)

    files = [f for f in directory.iterdir() if f.suffix.lower() in SUPPORTED_EXTENSIONS]
    if not files:
        typer.echo("No supported audio files found.")
        raise typer.Exit(0)

    typer.echo(f"Found {len(files)} audio file(s)")
    pid = uuid.UUID(profile_id) if profile_id else None

    async def _do():
        from call_analyzer.analyzer import analyze_file
        from call_analyzer.database import async_session

        async with async_session() as session:
            for f in files:
                try:
                    call, result = await analyze_file(f, "cli", session, profile_id=pid)
                    if hasattr(result, 'is_fraud'):
                        status = "FRAUD" if result.is_fraud else "CLEAN"
                        typer.echo(f"  [{status}] {f.name} — {result.fraud_score:.0%}")
                    else:
                        typer.echo(f"  [PROFILE] {f.name} — done")
                except Exception as e:
                    typer.echo(f"  [ERROR] {f.name}: {e}")

    _run(_do())


@app.command()
def watch(directory: Path = typer.Option(None, help="Directory to watch")):
    """Watch a directory for new audio files and analyze them."""
    from call_analyzer.watcher import start_watcher

    start_watcher(directory)


@app.command("list")
def list_calls(limit: int = typer.Option(10, help="Number of recent calls")):
    """Show recent analysis results."""

    async def _do():
        from sqlalchemy import select
        from sqlalchemy.orm import joinedload

        from call_analyzer.database import async_session
        from call_analyzer.models import Call

        async with async_session() as session:
            query = (
                select(Call)
                .options(joinedload(Call.analysis), joinedload(Call.profile), joinedload(Call.profile_result))
                .order_by(Call.created_at.desc())
                .limit(limit)
            )
            calls = (await session.execute(query)).unique().scalars().all()
            if not calls:
                typer.echo("No calls found.")
                return
            for c in calls:
                profile_label = f" [{c.profile.name}]" if c.profile else ""
                if c.profile_result:
                    typer.echo(f"[PROFILE] {c.filename}{profile_label} ({c.source}, {c.created_at})")
                elif c.analysis:
                    status = "FRAUD" if c.analysis.is_fraud else "CLEAN"
                    typer.echo(f"[{status}] {c.filename}{profile_label} — {c.analysis.fraud_score:.0%} ({c.source}, {c.created_at})")
                else:
                    typer.echo(f"[PENDING] {c.filename}{profile_label} ({c.source}, {c.created_at})")

    _run(_do())


@app.command()
def stats():
    """Show fraud detection statistics."""

    async def _do():
        from sqlalchemy import func, select

        from call_analyzer.database import async_session
        from call_analyzer.models import AnalysisResult, Call, ProfileResult

        async with async_session() as session:
            total = (await session.execute(select(func.count(Call.id)))).scalar() or 0
            fraud = (
                await session.execute(
                    select(func.count(AnalysisResult.id)).where(AnalysisResult.is_fraud.is_(True))
                )
            ).scalar() or 0
            profile_count = (
                await session.execute(select(func.count(ProfileResult.id)))
            ).scalar() or 0
            avg = (await session.execute(select(func.avg(AnalysisResult.fraud_score)))).scalar()

            typer.echo(f"Total calls:      {total}")
            typer.echo(f"Fraud detected:   {fraud}")
            typer.echo(f"Clean calls:      {total - fraud - profile_count}")
            typer.echo(f"Profile analyses: {profile_count}")
            typer.echo(f"Avg fraud score:  {avg:.1%}" if avg else "Avg fraud score:  N/A")

    _run(_do())


@app.command()
def serve(host: str = "0.0.0.0", port: int = 8080, root_path: str = ""):
    """Start the web server."""
    import uvicorn

    from call_analyzer.app import create_app

    application = create_app()
    uvicorn.run(application, host=host, port=port, root_path=root_path)


# ── Profile subcommands ─────────────────────────────────────────────

@profile_app.command("create")
def profile_create(
    name: str = typer.Option(..., help="Profile name"),
    prompt_mode: str = typer.Option("custom", help="Prompt mode: 'custom' or 'template'"),
    custom_prompt: Optional[str] = typer.Option(None, help="Custom prompt text"),
    expert: Optional[str] = typer.Option(None, help="Expert role (template mode)"),
    main_task: Optional[str] = typer.Option(None, help="Main task (template mode)"),
    fields_for_json: Optional[str] = typer.Option(None, help="JSON fields (template mode)"),
    trigger_words: Optional[str] = typer.Option(None, help="Comma-separated trigger words"),
    description: Optional[str] = typer.Option(None, help="Profile description"),
):
    """Create a new analysis profile."""
    if prompt_mode not in ("custom", "template"):
        typer.echo("Error: prompt_mode must be 'custom' or 'template'")
        raise typer.Exit(1)
    if prompt_mode == "template" and not main_task:
        typer.echo("Error: template mode requires --main-task")
        raise typer.Exit(1)

    async def _do():
        from call_analyzer.database import async_session
        from call_analyzer.models import Profile

        tw_list = [w.strip() for w in trigger_words.split(",") if w.strip()] if trigger_words else None

        async with async_session() as session:
            profile = Profile(
                id=uuid.uuid4(),
                name=name,
                description=description,
                prompt_mode=prompt_mode,
                custom_prompt=custom_prompt,
                expert=expert,
                main_task=main_task,
                fields_for_json=fields_for_json,
                trigger_words=tw_list,
            )
            session.add(profile)
            await session.commit()
            await session.refresh(profile)
            typer.echo(f"Created profile: {profile.name} (id={profile.id})")

    _run(_do())


@profile_app.command("list")
def profile_list():
    """List all analysis profiles."""

    async def _do():
        from sqlalchemy import select

        from call_analyzer.database import async_session
        from call_analyzer.models import Profile

        async with async_session() as session:
            profiles = (await session.execute(select(Profile).order_by(Profile.name))).scalars().all()
            if not profiles:
                typer.echo("No profiles found.")
                return
            for p in profiles:
                tw = f" [words: {', '.join(p.trigger_words)}]" if p.trigger_words else ""
                typer.echo(f"  {p.id}  {p.name} ({p.prompt_mode}){tw}")

    _run(_do())


@profile_app.command("update")
def profile_update(
    profile_id: str = typer.Argument(..., help="Profile UUID"),
    name: Optional[str] = typer.Option(None, help="New name"),
    custom_prompt: Optional[str] = typer.Option(None, help="New custom prompt"),
    expert: Optional[str] = typer.Option(None, help="New expert role"),
    main_task: Optional[str] = typer.Option(None, help="New main task"),
    fields_for_json: Optional[str] = typer.Option(None, help="New JSON fields"),
    trigger_words: Optional[str] = typer.Option(None, help="New trigger words (comma-separated)"),
    description: Optional[str] = typer.Option(None, help="New description"),
    prompt_mode: Optional[str] = typer.Option(None, help="New prompt mode"),
):
    """Update an existing analysis profile."""

    async def _do():
        from sqlalchemy import select

        from call_analyzer.database import async_session
        from call_analyzer.models import Profile

        pid = uuid.UUID(profile_id)
        async with async_session() as session:
            profile = (await session.execute(select(Profile).where(Profile.id == pid))).scalar_one_or_none()
            if not profile:
                typer.echo("Profile not found.")
                raise typer.Exit(1)

            if name is not None:
                profile.name = name
            if description is not None:
                profile.description = description or None
            if prompt_mode is not None:
                if prompt_mode not in ("custom", "template"):
                    typer.echo("Error: prompt_mode must be 'custom' or 'template'")
                    raise typer.Exit(1)
                profile.prompt_mode = prompt_mode
            if custom_prompt is not None:
                profile.custom_prompt = custom_prompt or None
            if expert is not None:
                profile.expert = expert or None
            if main_task is not None:
                profile.main_task = main_task or None
            if fields_for_json is not None:
                profile.fields_for_json = fields_for_json or None
            if trigger_words is not None:
                profile.trigger_words = [w.strip() for w in trigger_words.split(",") if w.strip()] if trigger_words else None

            await session.commit()
            await session.refresh(profile)
            typer.echo(f"Updated profile: {profile.name} (id={profile.id})")

    _run(_do())


if __name__ == "__main__":
    app()
