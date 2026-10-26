from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_root_returns_app_name_and_version() -> None:
    response = client.get("/")

    assert response.status_code == 200
    assert response.json() == {
        "message": "두 번째 자동 배포 테스트 성공!",
        "version": "local",
    }


def test_health_check() -> None:
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
