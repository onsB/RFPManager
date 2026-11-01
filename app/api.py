import json
import tempfile
from pathlib import Path

from fastapi import FastAPI, HTTPException, UploadFile
from fastapi.responses import FileResponse, StreamingResponse

from app.documents import load_document
from app.pipeline import run_pipeline

STATIC_DIR = Path(__file__).parent / "static"
SUPPORTED = {".pdf", ".docx", ".txt", ".md"}

app = FastAPI(title="RFP Manager")


@app.get("/")
def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@app.post("/extract")
def extract(file: UploadFile) -> StreamingResponse:
    """Runs the pipeline on an uploaded RFP, streaming each event as one JSON line.

    The page shows each section as it finishes instead of waiting minutes for the run.
    Event types are documented in app/pipeline.py.
    """
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in SUPPORTED:
        raise HTTPException(400, f"Unsupported file type: {suffix or 'none'}")

    # load_document reads from a path and picks the parser by extension.
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        tmp.write(file.file.read())
    try:
        text = load_document(tmp.name)
    finally:
        Path(tmp.name).unlink(missing_ok=True)

    events = run_pipeline(text, document=file.filename or "upload")
    return StreamingResponse((json.dumps(e) + "\n" for e in events), media_type="application/x-ndjson")


if __name__ == "__main__":
    # Lets VS Code's Run button start the server: then open http://127.0.0.1:8000
    import uvicorn

    uvicorn.run("app.api:app", host="127.0.0.1", port=8000, reload=True)
