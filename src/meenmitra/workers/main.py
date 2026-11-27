"""The worker process:  uv run arq meenmitra.workers.main.WorkerSettings

It runs the same code as the API, with the same settings and the same database. The only
difference is where its work comes from: Redis instead of HTTP.
"""

import asyncio
import logging
import signal

from arq.worker import Worker

from meenmitra.config import Settings, get_settings
from meenmitra.db.ingest_jobs import IngestRepository
from meenmitra.db.llm_calls import make_recorder
from meenmitra.db.session import make_engine, make_sessionmaker
from meenmitra.ingest.fetch import make_client
from meenmitra.llm.doc_meta import DocMeta
from meenmitra.llm.gateway import build_gateway
from meenmitra.llm.prompts import latest, read_prompt
from meenmitra.logging_setup import setup_logging
from meenmitra.workers.ingest import Pace, ingest_document
from meenmitra.workers.queue import Queue, redis_settings

logger = logging.getLogger("meenmitra.worker")


async def startup(ctx: dict) -> None:
    settings: Settings = ctx["settings"]

    logger.info("checking Redis connection")
    await ctx["redis"].ping()
    logger.info("Redis connection successful")
    if not ctx.get("embedded"):  # inside the API, logging is already set up
        setup_logging(settings.log_level)
        logging.getLogger("arq").handlers.clear()  # one log format: ours
    logging.getLogger("httpx").setLevel(logging.WARNING)  # one line per download is too much
    engine = make_engine(settings)
    ctx["engine"], ctx["sessionmaker"] = engine, make_sessionmaker(engine)
    ctx["gateway"] = build_gateway(settings, make_recorder(ctx["sessionmaker"]))
    ctx["http"] = make_client()
    ctx["pace"] = Pace(settings.ingest_rpm)
    ctx["extract"] = None
    if ctx["gateway"].providers:
        try:
            version = latest(settings.prompts_dir, "extract")
        except FileNotFoundError:
            logger.warning("no prompts/extract_v*.md: documents are parsed, not extracted")
        else:
            prompt = read_prompt(settings.prompts_dir, version)
            ctx["extract"] = {
                "schema": DocMeta,
                "prompt": prompt,
                "version": version,
                "chars": 6000,
            }
    # Redis may have forgotten jobs (a restart without persistence). Postgres has not.
    async with ctx["sessionmaker"]() as session:
        lost = await Queue(ctx["redis"]).put(await IngestRepository(session).open_item_ids())
    logger.info("worker ready, %s unfinished item(s) put back in the queue", lost)


async def shutdown(ctx: dict) -> None:
    http = ctx.get("http")
    if http is not None:
        await http.aclose()

    engine = ctx.get("engine")
    if engine is not None:
        await engine.dispose()


def worker_options(settings: Settings, *, embedded: bool = False) -> dict:
    return {
        "functions": [ingest_document],
        "on_startup": startup,
        "on_shutdown": shutdown,
        "redis_settings": redis_settings(settings.redis_url),
        "ctx": {"settings": settings, "embedded": embedded},
        "max_jobs": settings.ingest_concurrency,  # backpressure: never more at the same time
        "job_timeout": settings.ingest_job_timeout,
        "max_tries": settings.ingest_max_tries,
        "keep_result": 0,  # results live in Postgres, not in Redis
        "poll_delay": 1.0,
    }


async def run_embedded(settings: Settings) -> None:
    """A worker inside the API process, for hosts that offer no free worker service."""
    worker = Worker(**worker_options(settings, embedded=True), handle_signals=False)
    try:
        await worker.async_run()
    except asyncio.CancelledError:
        raise
    except Exception:
        logger.exception("the embedded worker stopped: is REDIS_URL right?")
    finally:
        if not hasattr(signal, "SIGUSR1"):
            worker.handle_sig(signal.SIGTERM)
            worker._handle_signals = True
        await worker.close()


# What the `arq` command reads. Built from .env like everything else.
WorkerSettings = worker_options(get_settings())
