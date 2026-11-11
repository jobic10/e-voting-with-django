import json

from django.conf import settings
from django.contrib import messages
from django.core.serializers.json import DjangoJSONEncoder
from django.db import transaction
from django.db.models import Count, F, Prefetch
from django.http import HttpResponse, JsonResponse
from django.shortcuts import redirect, render, reverse
from django.utils.decorators import method_decorator
from django.utils.html import escape
from django.utils.http import url_has_allowed_host_and_scheme
from django.utils.safestring import mark_safe
from django.views import View
from django.views.decorators.http import require_POST

from account.decorators import admin_required
from account.forms import CustomUserForm
from voting.forms import CandidateForm, PositionForm, VoterForm
from voting.models import Candidate, Position, Voter, Votes

ELECTION_TITLE_MAX_LENGTH = 200

# Same escaping Django's json_script filter uses, so JSON can be embedded
# inside a <script> block without allowing "</script>" break-outs.
_JSON_SCRIPT_ESCAPES = {
    ord('>'): '\\u003E',
    ord('<'): '\\u003C',
    ord('&'): '\\u0026',
}


def js_json(value):
    return mark_safe(json.dumps(value, cls=DjangoJSONEncoder).translate(_JSON_SCRIPT_ESCAPES))


def positions_with_vote_counts(order_by='priority'):
    """Positions with their candidates annotated with vote totals (2 queries)."""
    candidates = Candidate.objects.annotate(
        votes_total=Count('votes')).order_by('id')
    return Position.objects.order_by(order_by, 'id').prefetch_related(
        Prefetch('candidate_set', queryset=candidates))


def find_n_winners(data, n):
    """Return the ``n`` candidates with the most votes as escaped HTML."""
    ranked = sorted(data, key=lambda x: x['votes'], reverse=True)[:n]
    final_list = [escape(winner['name']) + " with " +
                  str(winner['votes']) + " votes" for winner in ranked]
    return mark_safe(", &nbsp;".join(final_list))


def read_election_title(default="E-voting"):
    try:
        with open(settings.ELECTION_TITLE_PATH, 'r') as file:
            return file.read()
    except OSError:
        return default


def get_result_context():
    position_data = {}
    for position in positions_with_vote_counts():
        candidate_data = [
            {'name': candidate.fullname, 'votes': candidate.votes_total}
            for candidate in position.candidate_set.all()
        ]
        # ! Check Winner
        if len(candidate_data) < 1:
            winner = "Position does not have candidates"
        else:
            # Check if max_vote is more than 1
            if position.max_vote > 1:
                winner = find_n_winners(candidate_data, position.max_vote)
            else:
                winner = max(candidate_data, key=lambda x: x['votes'])
                if winner['votes'] == 0:
                    winner = "No one voted for this yet position, yet."
                else:
                    count = sum(1 for d in candidate_data if d.get(
                        'votes') == winner['votes'])
                    if count > 1:
                        winner = f"There are {count} candidates with {winner['votes']} votes"
                    else:
                        winner = "Winner : " + escape(winner['name'])
        position_data[position.name] = {
            'candidate_data': candidate_data, 'winner': winner, 'max_vote': position.max_vote}
    return position_data


@method_decorator(admin_required, name='dispatch')
class PrintView(View):
    template_name = 'admin/print.html'
    download_name = "result.pdf"

    def get_context_data(self, **kwargs):
        return {
            'title': read_election_title(),
            'positions': get_result_context(),
        }

    def get(self, request, *args, **kwargs):
        # Imported lazily: WeasyPrint needs system libraries (Pango) and the
        # rest of the admin should keep working without them.
        from django_renderpdf import helpers
        response = HttpResponse(content_type="application/pdf")
        response["Content-Disposition"] = f'attachment; filename="{self.download_name}"'
        helpers.render_pdf(
            template=self.template_name,
            file_=response,
            url_fetcher=helpers.django_url_fetcher,
            context=self.get_context_data(**kwargs),
        )
        return response


@admin_required
def dashboard(request):
    positions = list(positions_with_vote_counts())
    chart_data = {}

    for position in positions:
        candidates = position.candidate_set.all()
        chart_data[position] = {
            'candidates': js_json([candidate.fullname for candidate in candidates]),
            'votes': js_json([candidate.votes_total for candidate in candidates]),
            'pos_id': position.id
        }

    context = {
        'position_count': len(positions),
        'candidate_count': Candidate.objects.count(),
        'voters_count': Voter.objects.count(),
        'voted_voters_count': Voter.objects.filter(voted=True).count(),
        'positions': positions,
        'chart_data': chart_data,
        'page_title': "Dashboard"
    }
    return render(request, "admin/home.html", context)


@admin_required
def voters(request):
    voters = Voter.objects.select_related('admin')
    userForm = CustomUserForm(request.POST or None)
    voterForm = VoterForm(request.POST or None)
    context = {
        'form1': userForm,
        'form2': voterForm,
        'voters': voters,
        'page_title': 'Voters List'
    }
    if request.method == 'POST':
        if userForm.is_valid() and voterForm.is_valid():
            with transaction.atomic():
                user = userForm.save(commit=False)
                user.user_type = '2'
                voter = voterForm.save(commit=False)
                user.save()
                voter.admin = user
                voter.save()
            messages.success(request, "New voter created")
        else:
            messages.error(request, "Form validation failed")
    return render(request, "admin/voters.html", context)


@admin_required
def view_voter_by_id(request):
    voter_id = request.GET.get('id', None)
    voter = Voter.objects.select_related('admin').filter(id=voter_id).first() \
        if str(voter_id).isdigit() else None
    context = {}
    if voter is None:
        context['code'] = 404
    else:
        context['code'] = 200
        context['first_name'] = voter.admin.first_name
        context['last_name'] = voter.admin.last_name
        context['phone'] = voter.phone
        context['id'] = voter.id
        context['email'] = voter.admin.email
    return JsonResponse(context)


@admin_required
def view_position_by_id(request):
    pos_id = request.GET.get('id', None)
    pos = Position.objects.filter(id=pos_id).first() if str(pos_id).isdigit() else None
    context = {}
    if pos is None:
        context['code'] = 404
    else:
        context['code'] = 200
        context['name'] = pos.name
        context['max_vote'] = pos.max_vote
        context['id'] = pos.id
    return JsonResponse(context)


@admin_required
@require_POST
def updateVoter(request):
    try:
        instance = Voter.objects.select_related('admin').get(id=request.POST.get('id'))
    except (Voter.DoesNotExist, ValueError):
        messages.error(request, "Access To This Resource Denied")
        return redirect(reverse('adminViewVoters'))
    user = CustomUserForm(request.POST, instance=instance.admin)
    voter = VoterForm(request.POST, instance=instance)
    if user.is_valid() and voter.is_valid():
        with transaction.atomic():
            user.save()
            voter.save()
        messages.success(request, "Voter's bio updated")
    else:
        messages.error(request, "Form validation failed")

    return redirect(reverse('adminViewVoters'))


@admin_required
@require_POST
def deleteVoter(request):
    try:
        admin = Voter.objects.select_related('admin').get(id=request.POST.get('id')).admin
        admin.delete()
        messages.success(request, "Voter Has Been Deleted")
    except (Voter.DoesNotExist, ValueError):
        messages.error(request, "Access To This Resource Denied")

    return redirect(reverse('adminViewVoters'))


@admin_required
def viewPositions(request):
    positions = Position.objects.order_by('-priority')
    form = PositionForm(request.POST or None)
    context = {
        'positions': positions,
        'form1': form,
        'page_title': "Positions"
    }
    if request.method == 'POST':
        if form.is_valid():
            form = form.save(commit=False)
            form.priority = Position.objects.count() + 1  # Just in case it is empty.
            form.save()
            messages.success(request, "New Position Created")
        else:
            messages.error(request, "Form errors")
    return render(request, "admin/positions.html", context)


@admin_required
@require_POST
def updatePosition(request):
    try:
        instance = Position.objects.get(id=request.POST.get('id'))
    except (Position.DoesNotExist, ValueError):
        messages.error(request, "Access To This Resource Denied")
        return redirect(reverse('viewPositions'))
    pos = PositionForm(request.POST, instance=instance)
    if pos.is_valid():
        pos.save()
        messages.success(request, "Position has been updated")
    else:
        messages.error(request, "Form errors")

    return redirect(reverse('viewPositions'))


@admin_required
@require_POST
def deletePosition(request):
    try:
        pos = Position.objects.get(id=request.POST.get('id'))
        pos.delete()
        messages.success(request, "Position Has Been Deleted")
    except (Position.DoesNotExist, ValueError):
        messages.error(request, "Access To This Resource Denied")

    return redirect(reverse('viewPositions'))


@admin_required
def viewCandidates(request):
    candidates = Candidate.objects.select_related('position')
    form = CandidateForm(request.POST or None, request.FILES or None)
    context = {
        'candidates': candidates,
        'form1': form,
        'page_title': 'Candidates'
    }
    if request.method == 'POST':
        if form.is_valid():
            form = form.save()
            messages.success(request, "New Candidate Created")
        else:
            messages.error(request, "Form errors")
    return render(request, "admin/candidates.html", context)


@admin_required
@require_POST
def updateCandidate(request):
    try:
        candidate = Candidate.objects.get(id=request.POST.get('id'))
    except (Candidate.DoesNotExist, ValueError):
        messages.error(request, "Access To This Resource Denied")
        return redirect(reverse('viewCandidates'))
    form = CandidateForm(request.POST, request.FILES or None, instance=candidate)
    if form.is_valid():
        form.save()
        messages.success(request, "Candidate Data Updated")
    else:
        messages.error(request, "Form has errors")

    return redirect(reverse('viewCandidates'))


@admin_required
@require_POST
def deleteCandidate(request):
    try:
        pos = Candidate.objects.get(id=request.POST.get('id'))
        pos.delete()
        messages.success(request, "Candidate Has Been Deleted")
    except (Candidate.DoesNotExist, ValueError):
        messages.error(request, "Access To This Resource Denied")

    return redirect(reverse('viewCandidates'))


@admin_required
def view_candidate_by_id(request):
    candidate_id = request.GET.get('id', None)
    candidate = Candidate.objects.filter(id=candidate_id).first() \
        if str(candidate_id).isdigit() else None
    context = {}
    if candidate is None:
        context['code'] = 404
    else:
        context['code'] = 200
        context['fullname'] = candidate.fullname
        previous = CandidateForm(instance=candidate)
        context['form'] = str(previous.as_p())
    return JsonResponse(context)


@admin_required
def ballot_position(request):
    context = {
        'page_title': "Ballot Position"
    }
    return render(request, "admin/ballot_position.html", context)


@admin_required
@require_POST
def update_ballot_position(request, position_id, up_or_down):
    context = {
        'error': False
    }
    if up_or_down not in ('up', 'down'):
        return JsonResponse({'error': True, 'message': "Invalid direction"}, status=400)
    with transaction.atomic():
        try:
            position = Position.objects.select_for_update().get(id=position_id)
        except Position.DoesNotExist:
            return JsonResponse({'error': True, 'message': "Position not found"}, status=404)
        if up_or_down == 'up':
            priority = position.priority - 1
            if priority < 1:
                context['error'] = True
                output = "This position is already at the top"
            else:
                Position.objects.filter(priority=priority).update(
                    priority=F('priority') + 1)
                position.priority = priority
                position.save(update_fields=['priority'])
                output = "Moved Up"
        else:
            priority = position.priority + 1
            if priority > Position.objects.count():
                output = "This position is already at the bottom"
                context['error'] = True
            else:
                Position.objects.filter(priority=priority).update(
                    priority=F('priority') - 1)
                position.priority = priority
                position.save(update_fields=['priority'])
                output = "Moved Down"
    context['message'] = output
    return JsonResponse(context)


@admin_required
@require_POST
def ballot_title(request):
    referer = request.META.get('HTTP_REFERER', '')
    if url_has_allowed_host_and_scheme(referer, allowed_hosts={request.get_host()},
                                       require_https=request.is_secure()):
        redirect_url = referer
    else:
        redirect_url = reverse('adminDashboard')
    title = (request.POST.get('title') or '').strip()
    if not title or len(title) > ELECTION_TITLE_MAX_LENGTH:
        messages.error(request, "Election title must be between 1 and %d characters" %
                       ELECTION_TITLE_MAX_LENGTH)
        return redirect(redirect_url)
    try:
        with open(settings.ELECTION_TITLE_PATH, 'w') as file:
            file.write(title)
    except OSError:
        messages.error(request, "Election title could not be saved")
        return redirect(redirect_url)
    messages.success(
        request, "Election title has been changed to " + str(title))
    return redirect(redirect_url)


@admin_required
def viewVotes(request):
    votes = Votes.objects.select_related('voter__admin', 'candidate', 'position')
    context = {
        'votes': votes,
        'page_title': 'Votes'
    }
    return render(request, "admin/votes.html", context)


@admin_required
@require_POST
def resetVote(request):
    with transaction.atomic():
        Votes.objects.all().delete()
        Voter.objects.all().update(voted=False, verified=False, otp=None, otp_sent=0)
    messages.success(request, "All votes has been reset")
    return redirect(reverse('viewVotes'))
