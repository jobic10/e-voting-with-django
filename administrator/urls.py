from django.urls import path
from . import views


urlpatterns = [
    path('', views.dashboard, name="adminDashboard"),
    path('voters', views.voters, name="adminViewVoters"),
    path('voters/view', views.view_voter_by_id, name="viewVoter"),
    path('voters/update', views.updateVoter, name="updateVoter"),
    # path('register/', views.account_register, name="account_register"),
]
