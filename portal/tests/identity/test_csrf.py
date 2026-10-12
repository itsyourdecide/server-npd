from app.identity.csrf import make_csrf_token


def test_csrf_token_is_deteerministic_for_same_session() -> None:
    token1 = make_csrf_token("session-token")
    token2 = make_csrf_token("session-token")

    assert token1 == token2

def test_csrf_token_differs_betweeb_sessions() -> None:

    token_a = make_csrf_token("session-a")
    token_b = make_csrf_token("session-b")

    assert token_a != token_b