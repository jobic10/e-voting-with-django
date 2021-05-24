from django.urls import path
from . import views


urlpatterns = [
    path('', views.dashboard, name="adminDashboard"),
    path('voters', views.voters, name="adminViewVoters"),
    path('voters/view', views.view_voter_by_id, name="viewVoter"),
    path('position/view', views.view_position_by_id, name="viewPosition"),
    path('voters/update', views.updateVoter, name="updateVoter"),
    path('position/update', views.updatePosition, name="updatePosition"),
    path('voters/delete', views.deleteVoter, name='deleteVoter'),
    path('position/delete', views.deletePosition, name='deletePosition'),
    path('positions/view', views.viewPositions, name='viewPositions'),
    # path('register/', views.account_register, name="account_register"),
]
