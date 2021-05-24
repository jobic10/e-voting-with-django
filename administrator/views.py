from django.shortcuts import render

# Create your views here.


def dashboard(request):
    context = {}
    return render(request, "admin/home.html", context)
