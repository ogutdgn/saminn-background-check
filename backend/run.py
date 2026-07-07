"""Windows-compatible uvicorn launcher.

On Windows, asyncio's default SelectorEventLoop does not support subprocess
creation, which Playwright needs to launch Chromium. We set the policy BEFORE
asyncio.run() creates the event loop so it picks up ProactorEventLoop.
"""
import asyncio
import sys

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

import uvicorn


async def main():
    config = uvicorn.Config("web.app:app", port=8099, reload=False)
    server = uvicorn.Server(config)
    await server.serve()


if __name__ == "__main__":
    asyncio.run(main())
