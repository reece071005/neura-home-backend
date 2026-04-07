# Follow AAA approach
# Arrange, Act, Assert


def test_register_user(client):
    response = client.post("/auth/register", json={
        "email": "testuser@example.com",
        "username": "testuser",
        "password": "testpassword",
    })
    assert response.status_code == 201
    assert response.json()["email"] == "testuser@example.com"
    assert response.json()["username"] == "testuser"
    assert response.json()["role"] == "user"