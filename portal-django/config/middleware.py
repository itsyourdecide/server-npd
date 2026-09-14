import uuid


class RequestIDMiddleware:
    """Attach one server-generated correlation ID to each HTTP request."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request.audit_request_id = uuid.uuid4()
        response = self.get_response(request)
        response.headers["X-Request-ID"] = str(request.audit_request_id)
        return response
