from django.urls import path
from . import views


urlpatterns = [
    path('', views.dashboard, name="adminDashboard"),
    # * Voters
    path('voters', views.voters, name="adminViewVoters"),
    path('voters/view', views.view_voter_by_id, name="viewVoter"),
    path('voters/delete', views.deleteVoter, name='deleteVoter'),
    path('voters/update', views.updateVoter, name="updateVoter"),

    # * Position
    path('position/view', views.view_position_by_id, name="viewPosition"),
    path('position/update', views.updatePosition, name="updatePosition"),
    path('position/delete', views.deletePosition, name='deletePosition'),
    path('positions/view', views.viewPositions, name='viewPositions'),

    # * Candidate
    path('candidate/', views.viewCandidates, name='viewCandidates'),
    path('candidate/update', views.updateCandidate, name="updateCandidate"),
    path('candidate/delete', views.deleteCandidate, name='deleteCandidate'),
    path('candidate/view', views.view_candidate_by_id, name='viewCandidate'),

    # * Settings (Ballot Position and Election Title)
    path("settings/ballot/position", views.ballot_position, name='ballot_position'),
    path("settings/ballot/title/", views.ballot_title, name='ballot_title'),
    path("settings/ballot/position/update/<int:position_id>/<str:up_or_down>/",
         views.update_ballot_position, name='update_ballot_position'),

    # * Votes
    path('votes/view', views.viewVotes, name='viewVotes'),
    path('votes/reset/', views.resetVote, name='resetVote'),
    path('votes/print/', views.PrintView.as_view(), name='printResult'),




]
