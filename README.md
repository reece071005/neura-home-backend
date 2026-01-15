# Neura API

A FastAPI application with PostgreSQL database and JWT-based user authentication.

## Features

- User registration
- User login with JWT tokens
- Protected routes requiring authentication
- PostgreSQL database integration
- Password hashing with bcrypt
- SQLAlchemy ORM

## Setup

### Prerequisites

- Python 3.8+ (for local development)
- PostgreSQL database (or use Docker)
- Docker and Docker Compose (for containerized setup)

### Docker Setup (Recommended)

The easiest way to run the application is using Docker Compose:

1. Clone the repository and navigate to the project directory:
```bash
cd neura-api
```

2. Create a `.env` file (optional, defaults are provided):
```bash
cp .env.example .env
```

Edit `.env` and set your `SECRET_KEY`:
```env
SECRET_KEY=your-secret-key-change-this-in-production-use-a-long-random-string
```

3. Build and start the services:
```bash
docker-compose up --build
```

This will:
- Start a PostgreSQL database container
- Build and start the FastAPI application container
- Automatically create database tables on first run

The API will be available at `http://localhost:8000`

4. To stop the services:
```bash
docker-compose down
```

5. To stop and remove volumes (clears database data):
```bash
docker-compose down -v
```

### Local Installation

1. Clone the repository and navigate to the project directory:
```bash
cd neura-api
```

2. Create a virtual environment:
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

3. Install dependencies:
```bash
pip install -r requirements.txt
```

4. Set up environment variables:
```bash
cp .env.example .env
```

Edit `.env` and update the following:
- `DATABASE_URL`: Your PostgreSQL connection string
- `SECRET_KEY`: A secure random string for JWT token signing

5. Create the PostgreSQL database:
```bash
createdb neura_db
# Or using psql:
# psql -U postgres
# CREATE DATABASE neura_db;
```

6. Run the application:
```bash
uvicorn app.main:app --reload
```

The API will be available at `http://localhost:8000`

## API Documentation

Once the server is running, you can access:
- Interactive API docs: `http://localhost:8000/docs`
- Alternative docs: `http://localhost:8000/redoc`

## API Endpoints

### Public Endpoints

- `GET /` - Root endpoint
- `GET /health` - Health check
- `POST /auth/register` - Register a new user
- `POST /auth/login` - Login and get JWT token

### Protected Endpoints

- `GET /auth/me` - Get current user information (requires authentication)

## Usage Examples

### Register a new user

```bash
curl -X POST "http://localhost:8000/auth/register" \
  -H "Content-Type: application/json" \
  -d '{
    "email": "user@example.com",
    "username": "testuser",
    "password": "securepassword123"
  }'
```

### Login

```bash
curl -X POST "http://localhost:8000/auth/login" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "username=testuser&password=securepassword123"
```

Response:
```json
{
  "access_token": "eyJ0eXAiOiJKV1QiLCJhbGc...",
  "token_type": "bearer"
}
```

### Access protected endpoint

```bash
curl -X GET "http://localhost:8000/auth/me" \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN"
```

## Project Structure

```
neura-api/
├── app/
│   ├── __init__.py
│   ├── main.py          # FastAPI application
│   ├── database.py      # Database configuration
│   ├── models.py        # SQLAlchemy models
│   ├── schemas.py       # Pydantic schemas
│   ├── auth.py          # Authentication utilities
│   └── routes/
│       ├── __init__.py
│       └── auth.py      # Authentication routes
├── requirements.txt
├── Dockerfile           # Docker image configuration
├── docker-compose.yml   # Docker Compose configuration
├── .dockerignore        # Docker ignore file
├── .env.example
├── .gitignore
└── README.md
```

## Security Notes

- Always use a strong `SECRET_KEY` in production
- Use HTTPS in production
- Consider implementing rate limiting
- Add email verification for user registration
- Implement password reset functionality
- Use environment variables for sensitive configuration
