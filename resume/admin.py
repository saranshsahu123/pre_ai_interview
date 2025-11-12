from django.contrib import admin

from django.contrib import admin
from .models import Candidate

class Admincandidate(admin.ModelAdmin):
    list_display=('email' , 'password')

admin.site.register(Candidate , Admincandidate)