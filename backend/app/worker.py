"""Run separately from API: python -m app.worker (or --once for one job)."""
import argparse
import asyncio
import contextlib
import logging
import signal
import sys

from app.agent.pipeline import PipelineAborted, generate_reply
from app.config import settings
from app.db import engine, fetch_one, transaction
from app.jobs.maintenance import HANDLERS
from app.jobs.queue import GENERATION, MAINTENANCE, LeaseFenceLost, claim_job, fail_job, renew_lease, watchdog_once
from app.providers import ProviderError, get_provider


logger = logging.getLogger("companion.worker")


class LeaseLost(Exception):
    pass


class CancellationRequested(Exception):
    pass


async def guard(job):
    elapsed = 0.0
    while True:
        await asyncio.sleep(0.5 if job["kind"] == "generate_reply" else 2)
        elapsed += 0.5 if job["kind"] == "generate_reply" else 2
        if elapsed >= 10:
            if not await renew_lease(job):
                raise LeaseLost()
            elapsed = 0
        if job["kind"] == "generate_reply":
            async with transaction() as conn:
                state = await fetch_one(conn, """SELECT r.cancel_requested_at,r.status,p.status AS persona_status,
                    p.context_version,r.context_version AS run_version,j.state AS job_state,j.lease_token,
                    j.lease_until>clock_timestamp() AS lease_valid FROM chat_runs r
                    JOIN personas p ON p.id=r.persona_id JOIN jobs j ON j.id=:job
                    WHERE r.id=:run AND r.owner_id=:owner""", {"job": job["id"], "run": job["target_id"], "owner": job["owner_id"]})
            if not state or state["job_state"] != "leased" or state["lease_token"] != job["lease_token"] or not state["lease_valid"]:
                raise LeaseLost()
            if state["cancel_requested_at"] or state["persona_status"] != "active" or state["context_version"] != state["run_version"]:
                raise CancellationRequested()


async def process_job(job, provider):
    work = asyncio.create_task(generate_reply(job, provider) if job["kind"] == "generate_reply" else HANDLERS[job["kind"]](job, provider))
    lease = asyncio.create_task(guard(job))
    try:
        async with asyncio.timeout(settings.run_timeout_seconds if job["kind"] == "generate_reply" else 90):
            done, _ = await asyncio.wait((work, lease), return_when=asyncio.FIRST_COMPLETED)
            # A completed business transaction wins a simultaneous lease check.
            if work in done:
                await work
            else:
                await lease
    except (LeaseLost, LeaseFenceLost):
        # The watchdog/reset owns terminal state. Never publish with an old token.
        pass
    except CancellationRequested:
        work.cancel()
        await asyncio.gather(work, return_exceptions=True)
        await fail_job(job, "CANCELLED_OR_STALE_CONTEXT")
    except PipelineAborted:
        await fail_job(job, "TARGET_UNAVAILABLE")
    except TimeoutError:
        work.cancel()
        await asyncio.gather(work, return_exceptions=True)
        await fail_job(job, "RUN_TIMEOUT")
    except ProviderError as exc:
        await fail_job(job, exc.code)
    except asyncio.CancelledError:
        # Shutdown/crash is recovered as interrupted by lease expiry, no auto retry.
        raise
    except Exception:
        # Log type and identifiers only; provider exception bodies can contain text.
        logger.error("Job failed kind=%s id=%s", job["kind"], job["id"])
        await fail_job(job, "JOB_FAILED")
    finally:
        work.cancel()
        lease.cancel()
        await asyncio.gather(work, lease, return_exceptions=True)


async def process_once(provider=None):
    owned_provider = provider is None
    provider = provider or get_provider()
    try:
        await watchdog_once()
        job = await claim_job(GENERATION + MAINTENANCE)
        if job:
            await process_job(job, provider)
        return job is not None
    finally:
        if owned_provider:
            await provider.close()


async def serve():
    provider = get_provider()
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        with contextlib.suppress(NotImplementedError):
            loop.add_signal_handler(sig, stop.set)

    async def consumer(kinds):
        while not stop.is_set():
            try:
                job = await claim_job(kinds)
                if job:
                    await process_job(job, provider)
                else:
                    with contextlib.suppress(TimeoutError):
                        await asyncio.wait_for(stop.wait(), timeout=0.5)
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.error("Queue unavailable; retrying")
                with contextlib.suppress(TimeoutError):
                    await asyncio.wait_for(stop.wait(), timeout=2)

    async def watchdog():
        while not stop.is_set():
            try:
                await watchdog_once()
            except Exception:
                logger.error("Watchdog scan failed")
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(stop.wait(), timeout=15)

    tasks = [asyncio.create_task(consumer(GENERATION)) for _ in range(settings.worker_concurrency)]
    tasks.extend([asyncio.create_task(consumer(MAINTENANCE)), asyncio.create_task(watchdog())])
    try:
        await asyncio.gather(*tasks)
    finally:
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        await provider.close()
        await engine.dispose()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO)
    if sys.platform == "win32":
        # psycopg asynchronous connections require the selector loop on Windows.
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

    async def run_once():
        try:
            await process_once()
        finally:
            await engine.dispose()

    asyncio.run(run_once() if args.once else serve())


if __name__ == "__main__":
    main()
