from django.urls import path
from . import views
urlpatterns = [
    path('login/', views.account_login, name="account_login"),
    path('register/', views.account_register, name="account_register"),
]
