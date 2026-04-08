import asyncio

from . import processes


async def run_timeout_checker() -> None:
    while True:
        try:
            await processes.check_timeouts()
        except Exception:
            pass
        await asyncio.sleep(60)
