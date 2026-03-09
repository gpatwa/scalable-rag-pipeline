# services/control-plane/app/proxy/streaming.py
"""
Streaming proxy for data plane requests.

Proxies SSE/NDJSON streams from the data plane to the end client
without buffering. Uses httpx.AsyncClient.stream() for true streaming.
"""
import json
import logging
import httpx
from fastapi import Request
from fastapi.responses import StreamingResponse, JSONResponse
from .mtls import create_mtls_client

logger = logging.getLogger(__name__)


async def proxy_stream(
    request: Request,
    data_plane_url: str,
    api_key: str,
    user_id: str,
    user_role: str,
    path: str,
) -> StreamingResponse:
    """
    Proxy a streaming POST request to the data plane.

    Forwards the request body and streams the NDJSON response
    back to the client line-by-line without buffering.
    """
    target_url = f"{data_plane_url}{path}"
    headers = {
        "X-DataPlane-Key": api_key,
        "X-User-Id": user_id,
        "X-User-Role": user_role,
        "Content-Type": "application/json",
    }
    body = await request.body()
    client = create_mtls_client()

    async def event_generator():
        try:
            async with client.stream(
                "POST",
                target_url,
                content=body,
                headers=headers,
            ) as response:
                if response.status_code != 200:
                    error_body = await response.aread()
                    yield json.dumps({
                        "type": "error",
                        "content": f"Data plane error ({response.status_code}): {error_body.decode()}"
                    }) + "\n"
                    return

                async for line in response.aiter_lines():
                    if line.strip():
                        yield line + "\n"

        except httpx.ConnectError:
            yield json.dumps({
                "type": "error",
                "content": "Data plane unreachable"
            }) + "\n"
        except Exception as e:
            logger.error(f"Streaming proxy error: {e}")
            yield json.dumps({
                "type": "error",
                "content": f"Proxy error: {str(e)}"
            }) + "\n"

    return StreamingResponse(
        event_generator(),
        media_type="application/x-ndjson",
    )


async def proxy_json(
    request: Request,
    data_plane_url: str,
    api_key: str,
    user_id: str,
    user_role: str,
    path: str,
) -> JSONResponse:
    """
    Proxy a non-streaming POST request to the data plane.

    Forwards the request and returns the JSON response.
    """
    target_url = f"{data_plane_url}{path}"
    headers = {
        "X-DataPlane-Key": api_key,
        "X-User-Id": user_id,
        "X-User-Role": user_role,
        "Content-Type": "application/json",
    }
    body = await request.body()
    client = create_mtls_client()

    try:
        response = await client.post(target_url, content=body, headers=headers)
        return JSONResponse(
            content=response.json(),
            status_code=response.status_code,
        )
    except httpx.ConnectError:
        return JSONResponse(
            content={"error": "Data plane unreachable"},
            status_code=503,
        )
    except Exception as e:
        logger.error(f"JSON proxy error: {e}")
        return JSONResponse(
            content={"error": str(e)},
            status_code=502,
        )
