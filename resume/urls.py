from django.urls import path
from . import views   # 👈 import the views module

urlpatterns = [
    # Home → upload page
    path("", views.upload_resume, name="upload_resume"),

    # Resume upload (same view, different URL if you want)
    path("upload/", views.upload_resume, name="upload_resume"),

    # Interview flow
    path("result/interview/start/", views.start_interview, name="start_interview"),
    path("result/interview/question/", views.interview_question, name="interview_question"),
    path("result/interview/feedback/", views.interview_feedback, name="interview_feedback"),

    # Auth
    path("login/", views.login_candidate, name="login_candidate"),
    path("signup/", views.signup_candidate, name="signup_candidate"),
]
