from django.conf import settings


def ElectionTitle(request):
    context = {}
    title = "No Title Yet"
    try:
        file = open(settings.ELECTION_TITLE_PATH, 'r')
        title = file.read()
    except:
        pass
    context['TITLE'] = title
    return context
