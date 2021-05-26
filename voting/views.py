from django.shortcuts import render
from account.views import account_login
from .models import Position, Candidate
from django.http import JsonResponse
from django.utils.text import slugify
# Create your views here.


def index(request):
    if not request.user.is_authenticated:
        return account_login(request)
    context = {}
    # return render(request, "voting/login.html", context)


def fetch_ballot(request):
    positions = Position.objects.order_by('priority').all()
    output = ""
    candidates_data = ""
    num = 1
    # return None
    for position in positions:
        if position.max_vote > 1:
            instruction = "You may select up to " + \
                str(position.max_vote) + " candidates"
            input_box = '<input type="checkbox" class="flat-red ' + \
                slugify(position.name)+'" name="' + \
                slugify(position.name)+"[]" + '">'
        else:
            instruction = "Select only one candidate"
            input_box = '<input type="radio" class="flat-red ' + \
                slugify(position.name)+'" name="'+slugify(position.name)+'">'
        candidates = Candidate.objects.filter(position=position)
        for candidate in candidates:
            image = "/media/" + str(candidate.photo)
            candidates_data = candidates_data + '<li>' + input_box + '<button class="btn btn-primary btn-sm btn-flat clist"><i class="fa fa-search"></i> Platform</button><img src="' + \
                image+'" height="100px" width="100px" class="clist"><span class="cname clist">' + \
                candidate.fullname+'</span></li>'
        up = ''
        if position.priority == 1:
            up = 'disabled'
        down = ''
        if position.priority == positions.count():
            down = 'disabled'
        output = output + f"""<div class="row">	<div class="col-xs-12"><div class="box box-solid" id="{position.id}">
             <div class="box-header with-border">
            <h3 class="box-title"><b>{position.name}</b></h3>
           
            <div class="pull-right box-tools">
            <button type="button" class="btn btn-default btn-sm moveup" data-id="{position.id}" {up}><i class="fa fa-arrow-up"></i> </button>
            <button type="button" class="btn btn-default btn-sm movedown" data-id="{position.id}" {down}><i class="fa fa-arrow-down"></i></button>
            </div>
            </div>
            <div class="box-body">
            <p>{instruction}
            <span class="pull-right">
            <button type="button" class="btn btn-success btn-sm btn-flat reset" data-desc="{position.name}"><i class="fa fa-refresh"></i> Reset</button>
            </span>
            </p>
            <div id="candidate_list">
            <ul>
            {candidates_data}
            </ul>
            </div>
            </div>
            </div>
            </div>
            </div>
        """
        position.priority = num
        position.save()
        num = num + 1
        candidates_data = ''
    return JsonResponse(output, safe=False)
