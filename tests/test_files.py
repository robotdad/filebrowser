import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from filebrowser.routes.files import router as files_router, get_fs
from filebrowser.auth import require_auth
from filebrowser.services.filesystem import FilesystemService


@pytest.fixture
def client(tmp_home):
    app = FastAPI()
    app.include_router(files_router)
    app.dependency_overrides[get_fs] = lambda: FilesystemService(tmp_home)
    app.dependency_overrides[require_auth] = lambda: "testuser"
    with TestClient(app) as c:
        yield c


@pytest.fixture
def unauth_client(tmp_home):
    app = FastAPI()
    app.include_router(files_router)
    app.dependency_overrides[get_fs] = lambda: FilesystemService(tmp_home)
    with TestClient(app) as c:
        yield c


class TestListDirectory:
    def test_list_root(self, client):
        response = client.get("/api/files", params={"path": ""})
        assert response.status_code == 200
        names = [e["name"] for e in response.json()]
        assert "docs" in names
        assert "hello.txt" in names

    def test_list_subdirectory(self, client):
        response = client.get("/api/files", params={"path": "docs"})
        assert response.status_code == 200
        names = [e["name"] for e in response.json()]
        assert "readme.md" in names

    def test_list_nonexistent_returns_404(self, client):
        response = client.get("/api/files", params={"path": "nonexistent"})
        assert response.status_code == 404

    def test_list_traversal_returns_403(self, client):
        response = client.get("/api/files", params={"path": "../../etc"})
        assert response.status_code == 403


class TestFileInfo:
    def test_file_info(self, client):
        response = client.get("/api/files/info", params={"path": "hello.txt"})
        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "hello.txt"
        assert data["type"] == "file"
        assert data["category"] == "text"

    def test_info_not_found(self, client):
        response = client.get("/api/files/info", params={"path": "nope.txt"})
        assert response.status_code == 404


class TestFileContent:
    def test_read_text_file(self, client):
        response = client.get("/api/files/content", params={"path": "hello.txt"})
        assert response.status_code == 200
        assert "Hello World" in response.text

    def test_content_not_found(self, client):
        response = client.get("/api/files/content", params={"path": "nope.txt"})
        assert response.status_code == 404

    def test_content_traversal_returns_403(self, client):
        response = client.get("/api/files/content", params={"path": "../../etc/passwd"})
        assert response.status_code == 403


class TestDownload:
    def test_download_sets_content_disposition(self, client):
        response = client.get("/api/files/download", params={"path": "hello.txt"})
        assert response.status_code == 200
        assert "attachment" in response.headers.get("content-disposition", "")


class TestUpload:
    def test_upload_file(self, client, tmp_home):
        response = client.post(
            "/api/files/upload",
            params={"path": ""},
            files={"file": ("uploaded.txt", b"file content", "text/plain")},
        )
        assert response.status_code == 200
        assert response.json()["name"] == "uploaded.txt"
        assert (tmp_home / "uploaded.txt").read_text() == "file content"

    def test_upload_to_subdirectory(self, client, tmp_home):
        response = client.post(
            "/api/files/upload",
            params={"path": "docs"},
            files={"file": ("new.txt", b"new content", "text/plain")},
        )
        assert response.status_code == 200
        assert (tmp_home / "docs" / "new.txt").read_text() == "new content"

    def test_upload_to_nonexistent_dir_returns_error(self, client):
        response = client.post(
            "/api/files/upload",
            params={"path": "nonexistent"},
            files={"file": ("test.txt", b"data", "text/plain")},
        )
        assert response.status_code in (400, 404)


class TestMkdir:
    def test_create_directory(self, client, tmp_home):
        response = client.post("/api/files/mkdir", params={"path": "new_folder"})
        assert response.status_code == 200
        assert (tmp_home / "new_folder").is_dir()


class TestRename:
    def test_rename_file(self, client, tmp_home):
        response = client.put(
            "/api/files/rename",
            json={"old_path": "hello.txt", "new_path": "renamed.txt"},
        )
        assert response.status_code == 200
        assert not (tmp_home / "hello.txt").exists()
        assert (tmp_home / "renamed.txt").exists()

    def test_rename_nonexistent_returns_404(self, client):
        response = client.put(
            "/api/files/rename",
            json={"old_path": "nonexistent.txt", "new_path": "other.txt"},
        )
        assert response.status_code == 404


class TestDelete:
    def test_delete_file(self, client, tmp_home):
        response = client.delete("/api/files", params={"path": "hello.txt"})
        assert response.status_code == 200
        assert not (tmp_home / "hello.txt").exists()

    def test_delete_nonexistent_returns_404(self, client):
        response = client.delete("/api/files", params={"path": "nope.txt"})
        assert response.status_code == 404

    def test_delete_traversal_returns_403(self, client):
        response = client.delete("/api/files", params={"path": "../../etc/passwd"})
        assert response.status_code == 403


class TestAuthEnforcement:
    def test_list_requires_auth(self, unauth_client):
        response = unauth_client.get("/api/files", params={"path": ""})
        assert response.status_code == 401

    def test_content_requires_auth(self, unauth_client):
        response = unauth_client.get("/api/files/content", params={"path": "hello.txt"})
        assert response.status_code == 401

    def test_upload_requires_auth(self, unauth_client):
        response = unauth_client.post(
            "/api/files/upload",
            params={"path": ""},
            files={"file": ("test.txt", b"data", "text/plain")},
        )
        assert response.status_code == 401

    def test_delete_requires_auth(self, unauth_client):
        response = unauth_client.delete("/api/files", params={"path": "hello.txt"})
        assert response.status_code == 401
