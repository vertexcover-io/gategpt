import os
from dotenv import load_dotenv
import uvicorn

if __name__ == "__main__":
    load_dotenv()
    debug = os.getenv("DEBUG", "0") == "1"
    port = int(os.getenv("PORT", None) or "8000")
    uvicorn.run(
        "src.custom_gpts_paywall.api:app",
        host="0.0.0.0",
        port=port,
        reload=debug,
        log_level="debug" if debug else "info",
    )
