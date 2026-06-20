"""Browser fetch() transport for the pygbag/WASM build.

urllib has no sockets in the browser, so live polling cannot use UrllibTransport there.

pygbag (0.9.x) CANNOT `await` a raw JS promise -- `await platform.window.fetch(url)` never
resumes the coroutine, so it hangs forever. pygbag's own HTTP path instead injects a JS
*generator* (window.Fetch.GET/POST) and drives it from Python with `platform.jsiter`, which
yields to the browser each step until the response resolves. We reuse that exact machinery
via `aio.fetch.RequestHandler` -- the supported way to make HTTP requests under pygbag.

The relay is same-origin (the page and feed_cache.php both live under PROJECTS/PREDICTOR/),
so there is no CORS handling to do here.

Import-safe on desktop: `aio.fetch` and `platform` are WASM-only and imported lazily inside
the methods, and the handler is built on first use -- nothing here touches them until a
request actually runs in the browser.
"""


class FetchTransport:
    """Transport that satisfies relay_client.Transport using pygbag's WASM fetch path."""

    def __init__(self) -> None:
        self._handler = None  # aio.fetch.RequestHandler, built lazily in the browser

    def _request_handler(self):
        """The shared pygbag RequestHandler, created on first use. Its constructor injects
        the window.Fetch.GET/POST JS helpers, so building it also primes POST."""
        if self._handler is None:
            import aio.fetch  # WASM-only pygbag module
            self._handler = aio.fetch.RequestHandler()
            self._handler.debug = False  # don't log every response body to the console
        return self._handler

    async def get(self, url: str) -> str:
        # url already carries the query string; pass no extra params.
        return str(await self._request_handler().get(url))

    async def post(self, url: str, body: str) -> str:
        # Only the (deferred) multiplayer relay POSTs; the live feed path is GET-only.
        # Build the handler first so window.Fetch.POST is defined, then drive that JS
        # generator directly with the already-serialised body.
        self._request_handler()
        import platform
        content = await platform.jsiter(platform.window.Fetch.POST(url, body))
        return str(content)
