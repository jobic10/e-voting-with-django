from django.urls import path
from . import views

urlpatterns = [
    path('', views.index),
    path('ballot/fetch/', views.fetch_ballot, name='fetch_ballot'),
    path('dashboard/', views.dashboard, name='voterDashboard'),
    path('verify/', views.verify, name='voterVerify'),
    path('otp/resend/', views.resend_otp, name='resend_otp'),
]
