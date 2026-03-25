import asyncio
import logging

from sqlalchemy import select, update
from sqlalchemy.orm import joinedload

from call_analyzer.analyzer import analyze_call
from call_analyzer.config import settings
from call_analyzer.database import async_session
from call_analyzer.models import Call
from call_analyzer.notifications import send_fraud_alert

logger = logging.getLogger(__name__)


async def process_call(call_id, semaphore: asyncio.Semaphore) -> None:
    async with semaphore:
        async with async_session() as session:
            try:
                await session.execute(
                    update(Call).where(Call.id == call_id).values(status="processing")
                )
                await session.commit()

                call = (await session.execute(
                    select(Call).options(joinedload(Call.profile)).where(Call.id == call_id)
                )).scalar_one()
                result = await analyze_call(call, session)

                if hasattr(result, 'is_fraud') and result.is_fraud:
                    try:
                        await send_fraud_alert(call, result)
                    except Exception:
                        logger.exception("Failed to send fraud alert email for call %s", call_id)

                await session.execute(
                    update(Call).where(Call.id == call_id).values(status="done")
                )
                await session.commit()
            except Exception as e:
                await session.rollback()
                logger.exception("Worker failed for call %s", call_id)
                await session.execute(
                    update(Call).where(Call.id == call_id).values(status="error", error_message=str(e)[:1000])
                )
                await session.commit()


async def worker_loop(stop_event: asyncio.Event) -> None:
    semaphore = asyncio.Semaphore(settings.worker_concurrency)

    # Reset stuck processing tasks from previous run
    async with async_session() as session:
        await session.execute(
            update(Call).where(Call.status == "processing").values(status="pending")
        )
        await session.commit()

    logger.info("Worker started (concurrency=%d)", settings.worker_concurrency)

    while not stop_event.is_set():
        try:
            async with async_session() as session:
                result = await session.execute(
                    select(Call.id)
                    .where(Call.status == "pending")
                    .order_by(Call.created_at)
                    .limit(settings.worker_concurrency)
                )
                call_ids = result.scalars().all()

            for call_id in call_ids:
                asyncio.create_task(process_call(call_id, semaphore))

        except Exception:
            logger.exception("Worker poll error")

        try:
            await asyncio.wait_for(stop_event.wait(), timeout=1.0)
            break
        except asyncio.TimeoutError:
            pass

    logger.info("Worker stopped")
