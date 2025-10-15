def test_index_redirect(client):
    rv = client.get("/")
    assert rv.status_code in (200, 302)
