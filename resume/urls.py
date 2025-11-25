from django.urls import path
from . import views

urlpatterns = [

    # Auth
    path("login/", views.login_candidate, name="login_candidate"),
    path("signup/", views.signup_candidate, name="signup_candidate"),

    # Resume Upload + Result
    path("", views.upload_resume, name="upload_resume"),
    path("upload/", views.upload_resume, name="upload_resume"),

    # Interview Flow
    path("interview/start/", views.start_interview, name="start_interview"),
    path("interview/question/", views.interview_question, name="interview_question"),
    path("interview/feedback/", views.interview_feedback, name="interview_feedback"),
]
