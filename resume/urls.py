from django.urls import path
from . import views

urlpatterns = [
    path('', views.login_candidate, name='login_candidate'),
    path('signup/', views.signup_candidate, name='signup_candidate'),
    path('upload/', views.upload_resume, name='upload_resume'),
    path('interview/start/', views.start_interview, name='start_interview'),
    path('interview/submit/', views.submit_answer, name='submit_answer'),
    path('interview/feedback/', views.interview_feedback, name='interview_feedback'),
]
