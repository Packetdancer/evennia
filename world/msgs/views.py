import json

from django.http import HttpResponse
from django.views.generic import ListView
from django.db.models import Q
from django.http import HttpResponseRedirect
from django.http import Http404
from django.core.urlresolvers import reverse
from django.core.exceptions import PermissionDenied

from evennia.comms.models import Msg

from .forms import (JournalMarkAllReadForm, JournalWriteForm, JournalMarkOneReadForm, JournalMarkFavorite,
                    JournalRemoveFavorite)
from server.utils.view_mixins import LimitPageMixin

# Create your views here.


class JournalListView(LimitPageMixin, ListView):
    model = Msg
    template_name = 'msgs/journal_list.html'
    paginate_by = 20

    def search_filters(self, queryset):
        get = self.request.GET
        if not get:
            return queryset
        sender = get.get('sender_name', None)
        if sender:
            queryset = queryset.filter(db_sender_objects__db_key__iexact=sender)
        receiver = get.get('receiver_name', None)
        if receiver:
            queryset = queryset.filter(db_receivers_objects__db_key__iexact=receiver)
        text = get.get('search_text', None)
        if text:
            queryset = queryset.filter(db_message__icontains=text)
        if self.request.user and self.request.user.is_authenticated():
            favtag = "pid_%s_favorite" % self.request.user.id
            favorites = get.get('favorites', None)
            if favorites:
                queryset = queryset.filter(db_tags__db_key=favtag)
        return queryset

    def get_queryset(self):
        user = self.request.user
        if not user or not user.is_authenticated() or not user.db.char_ob:
            qs = Msg.objects.filter(db_tags__db_key="white_journal").order_by('-db_date_created')
        elif user.is_staff:
            qs = Msg.objects.filter((Q(db_tags__db_key='white_journal') |
                                     Q(db_tags__db_key='black_journal')) &
                                    ~Q(db_receivers_players=user)).order_by('-db_date_created')
        else:
            qs = Msg.objects.filter((Q(db_tags__db_key='white_journal') |
                                     (Q(db_tags__db_key='black_journal') &
                                      Q(db_sender_objects=user.db.char_ob))) & ~Q(db_receivers_players=user)
                                    ).order_by('-db_date_created')
        return self.search_filters(qs)

    def get_context_data(self, **kwargs):
        context = super(JournalListView, self).get_context_data(**kwargs)
        # paginating our read journals as well as unread
        search_tags = ""
        sender = self.request.GET.get('sender_name', None)
        if sender:
            search_tags += "&sender_name=%s" % sender
        receiver = self.request.GET.get('receiver_name', None)
        if receiver:
            search_tags += "&receiver_name=%s" % receiver
        search_text = self.request.GET.get('search_text', None)
        if search_text:
            search_tags += "&search_text=%s" % search_text
        favorites = self.request.GET.get('favorites', None)
        if favorites:
            search_tags += "&favorites=True"
        context['search_tags'] = search_tags
        context['write_journal_form'] = JournalWriteForm()
        context['page_title'] = 'Journals'
        if self.request.user and self.request.user.is_authenticated():
            context['fav_tag'] = "pid_%s_favorite" % self.request.user.id
        else:
            context['fav_tag'] = None
        return context

    # noinspection PyUnusedLocal
    def post(self, request, *args, **kwargs):
        if "mark_all_read" in request.POST:
            form = JournalMarkAllReadForm(request.POST)
            if form.is_valid():
                for msg in form.cleaned_data['choices']:
                    msg.db_receivers_players.add(self.request.user)
            else:
                raise Http404(form.errors)
        if "mark_one_read" in request.POST:
            form = JournalMarkOneReadForm(request.POST)
            if form.is_valid():
                msg = form.cleaned_data['choice']
                msg.db_receivers_players.add(self.request.user)
            else:
                raise Http404(form.errors)
        if "mark_favorite" in request.POST:
            form = JournalMarkFavorite(request.POST)
            if form.is_valid():
                form.tag_msg(self.request.user.db.char_ob)
        if "remove_favorite" in request.POST:
            form = JournalRemoveFavorite(request.POST)
            if form.is_valid():
                form.untag_msg(self.request.user.db.char_ob)
        if "write_journal" in request.POST:
            form = JournalWriteForm(request.POST)
            if form.is_valid():
                # write journal
                form.create_journal(self.request.user.db.char_ob)
            else:
                raise Http404(form.errors)
        return HttpResponseRedirect(reverse('msgs:list_journals'))


class JournalListReadView(JournalListView):
    template_name = 'msgs/journal_list_read.html'

    def get_queryset(self):
        user = self.request.user
        if not user or not user.is_authenticated() or not user.db.char_ob:
            raise PermissionDenied("You must be logged in.")
        if user.is_staff:
            qs = Msg.objects.filter((Q(db_tags__db_key='white_journal') |
                                     Q(db_tags__db_key='black_journal')) &
                                    Q(db_receivers_players=user)).order_by('-db_date_created')
        else:
            qs = Msg.objects.filter((Q(db_tags__db_key='white_journal') |
                                     (Q(db_tags__db_key='black_journal') &
                                      Q(db_sender_objects=user.db.char_ob))) & Q(db_receivers_players=user)
                                    ).order_by('-db_date_created')
        return self.search_filters(qs)


API_CACHE = None


def journal_list_json(request):
    def get_fullname(char):
        commoner_names = {
            'Velenosa': 'Masque',
            'Valardin': 'Honor',
            'Crownsworn': 'Crown',
            'Redrain': 'Frost',
            'Grayson': 'Crucible',
            'Thrax': 'Waters'
        }
        last = commoner_names.get(char.db.fealty, "") if char.db.family == "None" else char.db.family
        return "{0} {1}".format(char.key, last)

    def get_response(entry):
        try:
            sender = entry.senders[0]
        except IndexError:
            sender = None
        try:
            target = entry.db_receivers_objects.all()[0]
        except IndexError:
            target = None
        from world.msgs.messagehandler import MessageHandler
        ic_date = MessageHandler.get_date_from_header(entry)
        return {
            'id': entry.id,
            'sender': get_fullname(sender) if sender else "",
            'target': get_fullname(target) if target else "",
            'message': entry.db_message,
            'ic_date': ic_date
        }

    try:
        timestamp = request.GET.get('timestamp', 0)
        import datetime
        timestamp = datetime.datetime.fromtimestamp(float(timestamp))
    except (AttributeError, ValueError, TypeError):
        timestamp = None
    global API_CACHE
    if timestamp:
        ret = map(get_response, Msg.objects.filter(Q(db_date_created__gt=timestamp) &
                                                   Q(db_tags__db_key="white_journal")
                                                   ).order_by('-db_date_created'))
        return HttpResponse(json.dumps(ret), content_type='application/json')
    if not API_CACHE:  # cache the list of all of them
        ret = map(get_response, Msg.objects.filter(db_tags__db_key="white_journal"
                                                   ).order_by('-db_date_created'))
        API_CACHE = json.dumps(ret)
    return HttpResponse(API_CACHE, content_type='application/json')
