from django.db.models import Q

from evennia.commands.default.muxcommand import MuxPlayerCommand
from evennia.utils.evtable import EvTable

from .models import Crisis, CrisisAction, CrisisActionAssistant


# noinspection PyUnresolvedReferences
class CrisisCmdMixin(object):
    @property
    def viewable_crises(self):
        qs = Crisis.objects.viewable_by_player(self.caller).order_by('end_date')
        return qs
        
    def list_crises(self):
        qs = self.viewable_crises
        if "old" in self.switches:
            qs = qs.filter(resolved=True)
        else:
            qs = qs.filter(resolved=False)
        table = EvTable("{w#{n", "{wName{n", "{wDesc{n", "{wUpdates On{n", width=78, border="cells")
        for ob in qs:
            date = "--" if not ob.end_date else ob.end_date.strftime("%m/%d")
            table.add_row(ob.id, ob.name, ob.headline, date)
        table.reformat_column(0, width=7)
        table.reformat_column(1, width=20)
        table.reformat_column(2, width=40)
        table.reformat_column(3, width=11)
        self.msg(table)
        
    def get_crisis(self):
        try:
            if self.lhs.isdigit():
                return self.viewable_crises.get(id=self.lhs)
            else:
                return self.viewable_crises.get(name__iexact=self.lhs)
        except (Crisis.DoesNotExist, ValueError):
            self.msg("Crisis not found by that # or name.")
            return
        
    def view_crisis(self):
        crisis = self.get_crisis()
        if not crisis:
            return self.list_crises()
        self.msg(crisis.display())
        return


class CmdGMCrisis(CrisisCmdMixin, MuxPlayerCommand):
    """
    GMs a crisis

    Usage:
        @gmcrisis
        @gmcrisis/old
        @gmcrisis <crisis #>
        @gmcrisis/create <name>/<headline>=<desc>
        
        @gmcrisis/update <crisis name or #>=<gemit text>[/<ooc notes>]
        @gmcrisis/update/nogemit <as above>

    Use the @actions command to answer individual actions, or mark then as
    published or pending publish. When making an update, all current actions
    for a crisis that aren't attached to a past update will then be attached to
    the current update, marking them as finished. That then allows players to
    submit new actions for the next round of the crisis, if the crisis is not
    resolved.
    
    Remember that if a crisis is not public (has a clue to see it), gemits
    probably shouldn't be sent or should be the vague details that people have
    no idea the crisis exists might notice.
    """
    key = "@gmcrisis"
    locks = "cmd:perm(wizards)"
    help_category = "GMing"

    def func(self):
        if not self.args:
            return self.list_crises()
        if "create" in self.switches:
            return self.create_crisis()
        if "update" in self.switches:
            return self.create_update()
        if not self.switches:
            return self.view_crisis()
        self.msg("Invalid switch")
        
    def create_crisis(self):
        lhs = self.lhs.split("/")
        if len(lhs) < 2:
            self.msg("Bad args.")
            return
        name, headline = lhs[0], lhs[1]
        desc = self.rhs
        Crisis.objects.create(name=name, headline=headline, desc=desc)
        self.msg("Crisis created. Make gemits or whatever for it.")
            
    def create_update(self):
        crisis = self.get_crisis()
        if not crisis:
            return
        rhs = self.rhs.split("/")
        gemit = rhs[0]
        gm_notes = None
        if len(rhs) > 1:
            gm_notes = rhs[1]
        crisis.create_update(gemit, self.caller, gm_notes, do_gemit="nogemit" not in self.switches)
        self.msg("You have updated the crisis.")


class CmdViewCrisis(CrisisCmdMixin, MuxPlayerCommand):
    """
    View the current or past crises

    Usage:
        +crisis [# or name]
        +crisis/old [<# or name>]
        +crisis/viewaction <action #>

    Crisis actions are queued and simultaneously resolved by GMs periodically. 
    To view crises that have since been resolved, use /old switch. Each crisis 
    that isn't resolved can have a rating assigned that determines the current 
    strength of the crisis, and any action taken can adjust that rating by the
    action's outcome value. If you choose to secretly support the crisis, you
    can use the /traitor option for a crisis action, in which case your action's
    outcome value will strengthen the crisis. Togglepublic can keep the action 
    from being publically listed. The addition of resources, armies, and extra 
    action points is taken into account when deciding outcomes. New actions cost
    50 action points, while assisting costs 10.

    To create a new action, use the @action command.
    """
    key = "+crisis"
    aliases = ["crisis"]
    locks = "cmd:all()"
    help_category = "Dominion"

    @property
    def current_actions(self):
        return self.caller.Dominion.actions.exclude(status=CrisisAction.PUBLISHED)

    @property
    def assisted_actions(self):
        return self.caller.Dominion.assisting_actions.all()

    def list_crises(self):
        super(CmdViewCrisis, self).list_crises()
        self.msg("{wYour pending actions:{n")
        table = EvTable("{w#{n", "{wCrisis{n")
        current_actions = list(self.current_actions) + [ass.crisis_action for ass in self.assisted_actions.exclude(
            crisis_action__status=CrisisAction.PUBLISHED)]
        for ob in current_actions:
            table.add_row(ob.id, ob.crisis)
        self.msg(table)
        past_actions = self.caller.past_participated_actions
        if past_actions:
            table = EvTable("{w#{n", "{wCrisis{n")
            self.msg("{wYour past actions:{n")
            for ob in past_actions:
                table.add_row(ob.id, ob.crisis)
            self.msg(table)

    def get_action(self, get_all=False, get_assisted=False, return_assistant=False):
        dompc = self.caller.Dominion
        if not get_all and not get_assisted:
            qs = self.current_actions
        else:
            qs = CrisisAction.objects.filter(Q(dompc=dompc) | Q(assistants=dompc)).distinct()
        try:
            action = qs.get(id=self.lhs)
            if not action.pk:
                self.msg("That action has been deleted.")
                return
            if return_assistant:
                try:
                    return action.assisting_actions.get(dompc=dompc)
                except CrisisActionAssistant.DoesNotExist:
                    self.msg("You are not assisting that crisis action.")
                    return
            return action
        except (CrisisAction.DoesNotExist, ValueError):
            self.msg("No action found by that id. Remember to specify the number of the action, not the crisis. " +
                     "Use /assist if trying to change your assistance of an action.")
        return

    def view_action(self):
        action = self.get_action(get_all=True, get_assisted=True)
        if not action:
            return
        msg = action.view_action(self.caller, disp_pending=True, disp_old=True)
        if not msg:
            msg = "You are not able to view that action."
        self.msg(msg)

    def func(self):
        if not self.args and (not self.switches or "old" in self.switches):
            self.list_crises()
            return
        if not self.switches or "old" in self.switches:
            self.view_crisis()
            return
        if "viewaction" in self.switches:
            self.view_action()
            return
        self.msg("Invalid switch")
