"""Pytest configuration and shared fixtures."""

import pytest
from fastapi.testclient import TestClient

from app.main import create_app


@pytest.fixture(scope="session")
def app():
    return create_app()


@pytest.fixture(scope="session")
def client(app):
    with TestClient(app) as c:
        yield c
