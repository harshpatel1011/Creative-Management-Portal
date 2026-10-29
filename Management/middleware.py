import datetime
from Student.models import Student

class AutoExpireLeaveMiddleware:
    """
    Middleware that ensures student leave statuses are automatically updated
    on every request whenever a leave end date has passed.
    """
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        try:
            Student.sync_expired_leaves()
        except Exception:
            pass
        response = self.get_response(request)
        return response
