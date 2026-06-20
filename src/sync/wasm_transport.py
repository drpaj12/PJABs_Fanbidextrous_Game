"""Browser fetch() transport for the pygbag/WASM build.

urllib has no sockets in the browser, so live polling cannot use UrllibTransport there.
This routes requests through the page's own fetch() instead. pygbag exposes the JS window
as `platform.window`; window.fetch returns a JS promise that pygbag's asyncio can await,
and the response's .text() promise yields the body. The relay is same-origin (the page
and feed_cache.php both live under PROJECTS/PREDICTOR/), so there is no CORS handling to
do here.

This module is import-safe on desktop -- `platform` is imported lazily inside the methods,
so nothing here touches platform.window until a request actually runs in the browser.
"""


class FetchTransport:
    """Transport that satisfies relay_client.Transport using the browser's fetch()."""

    async def get(self, url: str) -> str:
        import platform  # pygbag shims this with the JS window object
        resp = await platform.window.fetch(url)
        text = await resp.text()
        return str(text)

    async def post(self, url: str, body: str) -> str:
        # Only the (deferred) multiplayer relay POSTs; the live feed path is GET-only.
        # Relies on pygbag marshalling the options dict into a JS object.
        import platform
        opts = {
            "method": "POST",
            "headers": {"Content-Type": "application/json"},
            "body": body,
        }
        resp = await platform.window.fetch(url, opts)
        text = await resp.text()
        return str(text)
