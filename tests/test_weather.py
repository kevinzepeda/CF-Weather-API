from fastapi.testclient import TestClient
from api.main import app

client = TestClient(app)

def test_get_weather():
    response = client.get("/weather/New York")
    assert response.status_code == 200
    data = response.json()
    assert "city" in data
    assert "temperature" in data
    assert "description" in data
