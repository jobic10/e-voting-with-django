from django.urls import path
from . import views


urlpatterns = [
    path('', views.dashboard, name="adminDashboard"),
    # path('register/', views.account_register, name="account_register"),
]
