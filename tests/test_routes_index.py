def test_index_redirect(client):
    rv = client.get("/")
    assert rv.status_code in (200, 302)
    if rv.status_code == 302:
        assert "/login" in rv.headers.get("Location", "")
