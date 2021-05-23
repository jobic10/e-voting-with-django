from django.db import models
from account.models import CustomUser
# Create your models here.


class Voter(models.Model):
    admin = models.OneToOneField(CustomUser, on_delete=models.CASCADE)
    phone = models.CharField(max_length=11, unique=True)  # Used for OTP
    otp = models.CharField(max_length=10)
    verified = models.IntegerField()
    # Will later limit how many OTPs is sent


class Position(models.Model):
    name = models.CharField(max_length=50, unique=True)
    max_vote = models.IntegerField()
    priority = models.IntegerField()


class Candidate(models.Model):
    fullname = models.CharField(max_length=50)
    photo = models.ImageField(upload_to="candidates")
    bio = models.TextField()
    position = models.ForeignKey(Position, on_delete=models.CASCADE)
