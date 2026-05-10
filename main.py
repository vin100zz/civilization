"""Entry point — start the FastAPI server."""
import logging
import uvicorn

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)

if __name__ == "__main__":
    uvicorn.run(
        "web.server:app",
        host="0.0.0.0",
        port=8001,
        reload=False,
        log_level="info",
    )
