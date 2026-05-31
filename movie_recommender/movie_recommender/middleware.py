from django.shortcuts import redirect
from django.contrib import messages

class BlockUserMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.user.is_authenticated and getattr(request.user, 'is_blocked', False):
            # Здесь твоя логика блокировки, например, разлогинить или выдать ошибку
            pass
        response = self.get_response(request)
        return response