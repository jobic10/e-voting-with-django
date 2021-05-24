from django.urls import path
from . import views


urlpatterns = [
    path('', views.dashboard, name="adminDashboard"),
    path('voters', views.voters, name="adminViewVoters"),
    # path('register/', views.account_register, name="account_register"),
]
