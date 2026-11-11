import hmac
import json
import logging
import os
import secrets

import requests
from django.conf import settings
from django.contrib import messages
from django.db import transaction
from django.db.models import Prefetch
from django.http import JsonResponse
from django.shortcuts import redirect, render, reverse
from django.utils.html import format_html, format_html_join
from django.utils.safestring import mark_safe
from django.utils.text import slugify
from django.views.decorators.http import require_POST

from account import throttle
from account.decorators import admin_required, voter_required

from .models import Candidate, Position, Voter, Votes

logger = logging.getLogger(__name__)

OTP_LENGTH = 6


def index(request):
    if not request.user.is_authenticated:
        return redirect(reverse('account_login'))
    return redirect(reverse('voterDashboard'))


def positions_with_candidates():
    """All positions (ballot order) with their candidates in two queries."""
    return Position.objects.order_by('priority', 'id').prefetch_related(
        Prefetch('candidate_set', queryset=Candidate.objects.order_by('id')))


def normalize_priorities(positions):
    """Make priorities contiguous (1..n) without a write per position."""
    changed = []
    for num, position in enumerate(positions, start=1):
        if position.priority != num:
            position.priority = num
            changed.append(position)
    if changed:
        Position.objects.bulk_update(changed, ['priority'])


def generate_ballot(display_controls=False):
    positions = list(positions_with_candidates())
    normalize_priorities(positions)
    total = len(positions)
    output = []
    for position in positions:
        position_name = slugify(position.name)
        if position.max_vote > 1:
            instruction = "You may select up to %d candidates" % position.max_vote
        else:
            instruction = "Select only one candidate"
        candidates_data = []
        for candidate in position.candidate_set.all():
            if position.max_vote > 1:
                input_box = format_html(
                    '<input type="checkbox" value="{}" class="flat-red {}" name="{}[]">',
                    candidate.id, position_name, position_name)
            else:
                input_box = format_html(
                    '<input value="{}" type="radio" class="flat-red {}" name="{}">',
                    candidate.id, position_name, position_name)
            image = candidate.photo.url if candidate.photo else ''
            candidates_data.append(format_html(
                '<li>{}<button type="button" class="btn btn-primary btn-sm btn-flat clist platform" '
                'data-fullname="{}" data-bio="{}"><i class="fa fa-search"></i> Platform</button>'
                '<img src="{}" height="100px" width="100px" class="clist">'
                '<span class="cname clist">{}</span></li>',
                input_box, candidate.fullname, candidate.bio, image, candidate.fullname))

        controls = ''
        if display_controls:
            controls = format_html(
                ' <div class="pull-right box-tools">'
                '<button type="button" class="btn btn-default btn-sm moveup" data-id="{}" {}><i class="fa fa-arrow-up"></i> </button>'
                '<button type="button" class="btn btn-default btn-sm movedown" data-id="{}" {}><i class="fa fa-arrow-down"></i></button>'
                '</div>',
                position.id, 'disabled' if position.priority == 1 else '',
                position.id, 'disabled' if position.priority == total else '')

        output.append(format_html(
            '<div class="row"><div class="col-xs-12"><div class="box box-solid" id="{}">'
            '<div class="box-header with-border"><h3 class="box-title"><b>{}</b></h3>{}</div>'
            '<div class="box-body"><p>{}<span class="pull-right">'
            '<button type="button" class="btn btn-success btn-sm btn-flat reset" data-desc="{}">'
            '<i class="fa fa-refresh"></i> Reset</button></span></p>'
            '<div id="candidate_list"><ul>{}</ul></div></div></div></div></div>',
            position.id, position.name, controls, instruction, position_name,
            mark_safe(''.join(candidates_data))))
    return mark_safe(''.join(output))


@admin_required
def fetch_ballot(request):
    output = generate_ballot(display_controls=True)
    return JsonResponse(output, safe=False)


def generate_otp():
    """Cryptographically secure numeric OTP."""
    return ''.join(secrets.choice('0123456789') for _ in range(OTP_LENGTH))


def voter_is_verified(voter):
    return voter.verified and voter.otp is not None


@voter_required
def dashboard(request):
    voter = request.user.voter
    # * Check if this voter has been verified
    if not voter_is_verified(voter):
        if not settings.SEND_OTP:
            # Bypass
            msg = bypass_otp(voter)
            messages.success(request, msg)
            return redirect(reverse('show_ballot'))
        else:
            return redirect(reverse('voterVerify'))
    else:
        if voter.voted:  # * User has voted
            # To display election result or candidates I voted for ?
            context = {
                'my_votes': Votes.objects.filter(voter=voter).select_related('position', 'candidate'),
            }
            return render(request, "voting/voter/result.html", context)
        else:
            return redirect(reverse('show_ballot'))


@voter_required
def verify(request):
    context = {
        'page_title': 'OTP Verification'
    }
    return render(request, "voting/voter/verify.html", context)


@voter_required
@require_POST
def resend_otp(request):
    """API For SMS
    I used https://www.multitexter.com/ API to send SMS
    You might not want to use this or this service might not be available in your Country
    For quick and easy access, set the SEND_OTP environment variable to False
    """
    user = request.user
    voter = user.voter
    error = False
    if settings.SEND_OTP:
        if voter.otp_sent >= 3:
            error = True
            response = "You have requested OTP three times. You cannot do this again! Please enter previously sent OTP"
        else:
            phone = voter.phone
            # Now, check if an OTP has been generated previously for this voter
            otp = voter.otp
            if otp is None:
                # Generate new OTP
                otp = generate_otp()
                voter.otp = otp
                voter.save(update_fields=['otp'])
            try:
                msg = "Dear " + str(user) + ", kindly use " + \
                    str(otp) + " as your OTP"
                message_is_sent = send_sms(phone, msg)
                if message_is_sent:  # * OTP was sent successfully
                    # Update how many OTP has been sent to this voter
                    # Limited to Three so voters don't exhaust OTP balance
                    voter.otp_sent = voter.otp_sent + 1
                    voter.save(update_fields=['otp_sent'])

                    response = "OTP has been sent to your phone number. Please provide it in the box provided below"
                else:
                    error = True
                    response = "OTP not sent. Please try again"
            except Exception:
                logger.exception("Could not send OTP")
                error = True
                response = "OTP could not be sent. Please try again later"
    else:
        #! OTP disabled: verify this voter and send them to the ballot
        response = bypass_otp(voter)
    return JsonResponse({"data": response, "error": error})


def bypass_otp(voter):
    Voter.objects.filter(pk=voter.pk).update(otp="0000", verified=True)
    voter.otp, voter.verified = "0000", True
    response = "Kindly cast your vote"
    return response


def send_sms(phone_number, msg):
    """Read More
    https://www.multitexter.com/developers
    """
    email = os.environ.get('SMS_EMAIL')
    password = os.environ.get('SMS_PASSWORD')
    if email is None or password is None:
        raise Exception("Email/Password cannot be Null")
    url = "https://app.multitexter.com/v2/app/sms"
    data = {"email": email, "password": password, "message": msg,
            "sender_name": "OTP", "recipients": phone_number, "forcednd": 1}
    headers = {'Content-type': 'application/json', 'Accept': 'text/plain'}
    r = requests.post(url, data=json.dumps(data), headers=headers, timeout=15)
    response = r.json()
    status = response.get('status', 0)
    return str(status) == '1'


@voter_required
@require_POST
def verify_otp(request):
    error = True
    voter = request.user.voter
    key = "otp-fail:%s" % voter.pk
    otp = (request.POST.get('otp') or '').strip()
    if throttle.is_limited(key, settings.OTP_MAX_ATTEMPTS):
        messages.error(request, "Too many invalid OTP attempts. Please try again later")
    elif not otp:
        messages.error(request, "Please provide valid OTP")
    elif voter.otp is None or not hmac.compare_digest(voter.otp, otp):
        throttle.hit(key, settings.OTP_LOCKOUT_SECONDS)
        messages.error(request, "Provided OTP is not valid")
    else:
        throttle.reset(key)
        messages.success(
            request, "You are now verified. Please cast your vote")
        voter.verified = True
        voter.save(update_fields=['verified'])
        error = False
    if error:
        return redirect(reverse('voterVerify'))
    return redirect(reverse('show_ballot'))


def ensure_can_vote(request):
    """Return a redirect response if the voter may not see/submit a ballot."""
    voter = request.user.voter
    if voter.voted:
        messages.error(request, "You have voted already")
        return redirect(reverse('voterDashboard'))
    if not voter_is_verified(voter):
        if settings.SEND_OTP:
            messages.error(request, "Please verify your account before voting")
            return redirect(reverse('voterVerify'))
        bypass_otp(voter)
    return None


@voter_required
def show_ballot(request):
    denied = ensure_can_vote(request)
    if denied:
        return denied
    ballot = generate_ballot(display_controls=False)
    context = {
        'ballot': ballot
    }
    return render(request, "voting/voter/ballot.html", context)


class BallotError(Exception):
    pass


def parse_ballot(post_data):
    """Validate submitted ballot data.

    Returns a list of ``(position, [candidates])`` in ballot order. Raises
    ``BallotError`` with a user facing message if anything is off.
    """
    selections = []
    for position in positions_with_candidates():
        pos = slugify(position.name)
        key = pos + "[]" if position.max_vote > 1 else pos
        chosen_ids = post_data.getlist(key)
        if not chosen_ids:
            continue
        if position.max_vote <= 1:
            chosen_ids = chosen_ids[:1]
        if len(chosen_ids) > position.max_vote or len(set(chosen_ids)) != len(chosen_ids):
            raise BallotError("You can only choose " +
                              str(position.max_vote) + " candidates for " + position.name)
        candidates_by_id = {str(c.id): c for c in position.candidate_set.all()}
        try:
            chosen = [candidates_by_id[str(int(cid))] for cid in chosen_ids]
        except (KeyError, ValueError):
            raise BallotError("Please, browse the system properly")
        selections.append((position, chosen))
    return selections


@voter_required
@require_POST
def preview_vote(request):
    try:
        selections = parse_ballot(request.POST)
    except BallotError as e:
        return JsonResponse({'error': True, 'message': [str(e)], 'list': ''})
    output = []
    for position, candidates in selections:
        if position.max_vote > 1:
            items = format_html_join(
                '', '<li><i class="fa fa-check-square-o"></i> {}</li>',
                ((c.fullname,) for c in candidates))
            body = format_html(
                "<ul style='list-style-type:none; margin-left:-40px'>{}</ul>", items)
        else:
            body = format_html('<i class="fa fa-check-circle-o"></i> {}', candidates[0].fullname)
        output.append(format_html(
            "<div class='row votelist' style='padding-bottom: 2px'>"
            "<span class='col-sm-4'><span class='pull-right'><b>{} :</b></span></span>"
            "<span class='col-sm-8'>{}</span></div><hr/>",
            position.name, body))
    return JsonResponse({'error': False, 'list': ''.join(output)})


@voter_required
@require_POST
def submit_ballot(request):
    denied = ensure_can_vote(request)
    if denied:
        return denied
    try:
        selections = parse_ballot(request.POST)
    except BallotError as e:
        messages.error(request, str(e))
        return redirect(reverse('show_ballot'))

    # Ensure at least one vote is selected
    if not selections:
        messages.error(request, "Please select at least one candidate")
        return redirect(reverse('show_ballot'))

    with transaction.atomic():
        # Lock the voter row so two concurrent submissions cannot both vote
        voter = Voter.objects.select_for_update().get(pk=request.user.voter.pk)
        if voter.voted:
            messages.error(request, "You have voted already")
            return redirect(reverse('voterDashboard'))
        Votes.objects.bulk_create([
            Votes(voter=voter, position=position, candidate=candidate)
            for position, candidates in selections
            for candidate in candidates
        ])
        voter.voted = True
        voter.save(update_fields=['voted'])
    messages.success(request, "Thanks for voting")
    return redirect(reverse('voterDashboard'))
