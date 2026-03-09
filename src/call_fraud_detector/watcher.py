import asyncio
from pathlib import Path

from watchdog.events import FileSystemEvent, FileSystemEventHandler
from watchdog.observers import Observer

from call_fraud_detector.audio import SUPPORTED_EXTENSIONS
from call_fraud_detector.config import settings
from call_fraud_detector.database import async_session


class AudioFileHandler(FileSystemEventHandler):
    def __init__(self) -> None:
        self._loop = asyncio.get_event_loop()

    def on_created(self, event: FileSystemEvent) -> None:
        if event.is_directory:
            return
        path = Path(event.src_path)
        if path.suffix.lower() not in SUPPORTED_EXTENSIONS:
            return
        print(f"New audio file detected: {path.name}")
        self._loop.create_task(self._analyze(path))

    async def _analyze(self, path: Path) -> None:
        from call_fraud_detector.analyzer import analyze_file

        async with async_session() as session:
            try:
                call, result = await analyze_file(path, "watcher", session)
                status = "FRAUD" if result.is_fraud else "CLEAN"
                print(f"  [{status}] {path.name} — score: {result.fraud_score:.0%}")
            except Exception as e:
                print(f"  [ERROR] {path.name}: {e}")


def start_watcher(watch_dir: Path | None = None) -> None:
    directory = watch_dir or settings.watch_dir
    directory.mkdir(parents=True, exist_ok=True)
    print(f"Watching directory: {directory.resolve()}")

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    handler = AudioFileHandler()
    observer = Observer()
    observer.schedule(handler, str(directory), recursive=False)
    observer.start()

    try:
        loop.run_forever()
    except KeyboardInterrupt:
        observer.stop()
    observer.join()
