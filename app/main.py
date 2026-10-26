import os

from fastapi import FastAPI

app = FastAPI(title="FastAPI CI/CD Demo")
app_version = os.getenv("APP_VERSION", "local")


@app.get("/")
def read_root() -> dict[str, str]:
    return {
        "message": "두 번째 자동 배포 테스트 성공!",
        "version": app_version,
    }


@app.get("/health")
def health_check() -> dict[str, str]:
    return {"status": "ok"}
