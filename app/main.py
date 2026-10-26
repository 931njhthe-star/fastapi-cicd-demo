import os

from fastapi import FastAPI

app = FastAPI(title="FastAPI CI/CD Demo")
app_version = os.getenv("APP_VERSION", "local")


@app.get("/")
def read_root() -> dict[str, str]:
    return {
        "message": "FastAPI CI/CD demo is running",
        "version": app_version,
    }


@app.get("/health")
def health_check() -> dict[str, str]:
    return {"status": "ok"}
