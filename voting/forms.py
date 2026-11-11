from django import forms
from django.utils.text import slugify

from account.forms import FormSettings

from .models import Candidate, Position, Voter


class VoterForm(FormSettings):
    class Meta:
        model = Voter
        fields = ['phone']


class PositionForm(FormSettings):
    def clean_max_vote(self):
        max_vote = self.cleaned_data.get('max_vote')
        if max_vote is None or max_vote < 1:
            raise forms.ValidationError("Maximum vote must be at least 1")
        return max_vote

    def clean_name(self):
        name = (self.cleaned_data.get('name') or '').strip()
        slug = slugify(name)
        if not slug:
            raise forms.ValidationError("Please provide a valid position name")
        # Ballot fields are keyed by the slug, so two positions must never share one
        others = Position.objects.exclude(pk=self.instance.pk) if self.instance.pk else Position.objects.all()
        if any(slugify(other) == slug for other in others.values_list('name', flat=True)):
            raise forms.ValidationError("A position with a similar name already exists")
        return name

    class Meta:
        model = Position
        fields = ['name', 'max_vote']


class CandidateForm(FormSettings):
    class Meta:
        model = Candidate
        fields = ['fullname', 'bio', 'position', 'photo']
