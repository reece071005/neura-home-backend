# Follow AAA approach
# Arrange, Act, Assert


def test_register_first_user(client):
    response = client.post("/auth/register", json={
        "email": "testuser@example.com",
        "username": "testuser",
        "password": "testpassword",
    })
    assert response.status_code == 201
    assert response.json()["email"] == "testuser@example.com"
    assert response.json()["username"] == "testuser"

    assert response.json()["role"] == "admin"

def test_register_second_user(client):
    # First user is already registered
    response = client.post("/auth/register", json={
        "email": "testuser2@example.com",
        "username": "testuser2",
        "password": "testpassword2",
    })
    assert response.status_code == 403
    assert response.json()["detail"] == "Registration is closed. Ask an admin to create an account for you."

def test_login_admin(client):
    response = client.post(
        "/auth/login",
        data={"username": "testuser", "password": "testpassword"},
    )
    assert response.status_code == 200
    assert response.json()["access_token"] is not None
    assert response.json()["token_type"] == "bearer"

def test_login_invalid_credentials_admin(client):
    response = client.post(
        "/auth/login",
        data={"username": "testuser", "password": "invalidpassword"},
    )
    assert response.status_code == 401
    assert response.json()["detail"] == "Incorrect username or password"

def test_add_user_from_admin(client):
    response = client.post(
        "/auth/login",
        data={"username": "testuser", "password": "testpassword"},
    )
    assert response.status_code == 200
    assert response.json()["access_token"] is not None
    assert response.json()["token_type"] == "bearer"

    token = response.json()["access_token"]

    response = client.post(
        "/auth/users/add-users",
        json={
            "email": "testuser2@example.com",
            "username": "testuser2",
            "password": "testpassword2",
            "role": "user",
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 201
    assert response.json()["email"] == "testuser2@example.com"
    assert response.json()["username"] == "testuser2"
    assert response.json()["role"] == "user"

def test_login_user(client):
    response = client.post(
        "/auth/login",
        data={"username": "testuser2", "password": "testpassword2"},
    )
    assert response.status_code == 200
    assert response.json()["access_token"] is not None
    assert response.json()["token_type"] == "bearer"

def test_login_invalid_credentials_user(client):
    response = client.post(
        "/auth/login",
        data={"username": "testuser2", "password": "invalidpassword"},
    )
    assert response.status_code == 401
    assert response.json()["detail"] == "Incorrect username or password"


def test_change_user_role_from_admin(client):
    response = client.post(
        "/auth/login",
        data={"username": "testuser", "password": "testpassword"},
    )
    assert response.status_code == 200
    assert response.json()["access_token"] is not None
    assert response.json()["token_type"] == "bearer"
    token = response.json()["access_token"]

    response = client.put(
        "/auth/users/change-role",
        json={
            "username": "testuser2",
            "role": "admin",
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    assert response.json()["role"] == "admin"

def test_change_user_password_from_admin(client):
    response = client.post(
        "/auth/login",
        data={"username": "testuser", "password": "testpassword"},
    )
    assert response.status_code == 200
    assert response.json()["access_token"] is not None
    assert response.json()["token_type"] == "bearer"
    token = response.json()["access_token"]

    response = client.put(
        "/auth/users/change-password",
        json={
            "username": "testuser2",
            "password": "newpassword",
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    
    response = client.post(
        "/auth/login",
        data={"username": "testuser2", "password": "newpassword"},
    )
    assert response.status_code == 200
    assert response.json()["access_token"] is not None
    assert response.json()["token_type"] == "bearer"


def test_change_user_password_invalid_old_password(client):
    response = client.post(
        "/auth/login",
        data={"username": "testuser2", "password": "newpassword"},
    )
    assert response.status_code == 200
    assert response.json()["access_token"] is not None
    assert response.json()["token_type"] == "bearer"
    token = response.json()["access_token"]

    response = client.put(
        "/auth/users/change-password-self",
        json={
            "old_password": "invalidpassword",
            "new_password": "newpassword2",
            "confirm_password": "newpassword2",
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 400
    assert response.json()["detail"] == "Old password is incorrect"


def test_change_user_password_invalid_new_password(client):
    response = client.post(
        "/auth/login",
        data={"username": "testuser2", "password": "newpassword"},
    )
    assert response.status_code == 200
    assert response.json()["access_token"] is not None
    assert response.json()["token_type"] == "bearer"
    token = response.json()["access_token"]

    response = client.put(
        "/auth/users/change-password-self",
        json={
            "old_password": "newpassword",
            "new_password": "newpassword2",
            "confirm_password": "newpassword3",
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 400
    assert response.json()["detail"] == "New password and confirmation do not match"


def test_change_user_password_self(client):
    response = client.post(
        "/auth/login",
        data={"username": "testuser2", "password": "newpassword"},
    )
    assert response.status_code == 200
    assert response.json()["access_token"] is not None
    assert response.json()["token_type"] == "bearer"
    token = response.json()["access_token"]

    response = client.put(
        "/auth/users/change-password-self",
        json={
            "old_password": "newpassword",
            "new_password": "newpassword2",
            "confirm_password": "newpassword2",
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    assert response.json()["username"] == "testuser2"

    response = client.post(
        "/auth/login",
        data={"username": "testuser2", "password": "newpassword2"},
    )
    assert response.status_code == 200
    assert response.json()["access_token"] is not None
    assert response.json()["token_type"] == "bearer"


def test_delete_user_from_admin(client):
    response = client.post(
        "/auth/login",
        data={"username": "testuser", "password": "testpassword"},
    )
    assert response.status_code == 200
    assert response.json()["access_token"] is not None
    assert response.json()["token_type"] == "bearer"
    token = response.json()["access_token"]

    response = client.get(
        "/auth/users/get-users",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    assert response.json() is not None
    assert len(response.json()) > 0
    user_id = response.json()[0]["id"]

    response = client.delete(
        f"/auth/users/delete-user/{user_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    assert response.json()["message"] == "User deleted successfully"