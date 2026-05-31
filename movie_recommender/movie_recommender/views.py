from django.shortcuts import redirect


def csrf_failure(request, reason=''):
    referer = request.META.get('HTTP_REFERER', '/')
    return redirect(referer)
