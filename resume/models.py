from django.db import models

# Create your models here.
class Candidate(models.Model):
    email = models.EmailField()
    password = models.TextField()