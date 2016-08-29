"""
XP and Skill stuff!

Most utilities for xp/costs and skill checks are all handled
in the gamesrc.objects.stats_and_skills file, which we'll use
liberally here. In general, all the commands players and builders
will use to see their skills, use or adjust xp, and so on will
be here, as well as related commands such as voting to give
other players xp awards for good roleplay.
"""

from evennia.commands.default.muxcommand import MuxCommand, MuxPlayerCommand
from django.conf import settings
from world import stats_and_skills
from server.utils.utils import inform_staff
from evennia.utils.utils import list_to_string
from evennia.players.models import PlayerDB

class CmdUseXP(MuxCommand):
    """
    xp

    Usage:
        xp
        xp/spend  <stat or skill name>
        xp/cost   <stat or skill name>

    Displays how much xp you have available when used with no arguments,
    and allows you to spend xp to increase stats or skills with the
    /spend switch. Costs can be reduced by finding a teacher who is willing
    to use the '{wtrain{n' command on you, and has a skill or stat of the
    appropriate rank you're trying to achieve. Any training bonus is lost
    after the first time xp is spent in a week.

    Dominion influence is bought with 'resources' rather than xp. The
    'learn' command is the same as 'xp/spend'.
    """
    key = "xp"
    aliases = ["+xp", "experience", "learn"]
    locks = "cmd:all()"
    help_category = "Progression"
    def func(self):
        """
        Allows the character to check their xp, and spend it if they use
        the /spend switch and meet the requirements.
        """
        caller = self.caller
        if self.cmdstring == "learn":
            self.switches.append("spend")
        if not self.args:
            # Just display our xp
            caller.msg("{wUnspent XP:{n %s" % caller.db.xp)
            caller.msg("{wLifetime Earned XP:{n %s" % caller.db.total_xp)
            all_stats = ", ".join(stat for stat in stats_and_skills._valid_stats_)
            caller.msg("\n{wStat names:{n")
            caller.msg(all_stats)
            caller.msg("\n{wSkill names:{n")
            caller.msg(", ".join(skill for skill in stats_and_skills._valid_skills_))
            caller.msg("\n{wDominion skill names:{n")
            caller.msg(", ".join(skill for skill in stats_and_skills._domskills_))
            caller.msg("\n{wAbility names:{n")
            crafting = stats_and_skills._crafting_abilities_
            abilities = caller.db.abilities or {}
            abilities = set(abilities.keys()) | set(crafting)
            if caller.check_permstring("builder"):
                caller.msg(", ".join(ability for ability in stats_and_skills._valid_abilities_))
            else:
                caller.msg(", ".join(ability for ability in abilities))
            return
        args = self.args.lower()
        # get cost already factors in if we have a trainer, so no need to check
        if args in stats_and_skills._valid_stats_:
            cost = stats_and_skills.get_stat_cost(caller, args)
            if caller.attributes.get(args) >= 5:
                caller.msg("%s is already at its maximum." % args)
                return
            stype = "stat"
        elif args in stats_and_skills._valid_skills_:
            if not caller.db.skills: caller.db.skills = {}
            if caller.db.skills.get(args, 0) >= 6:
                caller.msg("%s is already at its maximum." % args)
                return
            cost = stats_and_skills.get_skill_cost(caller, args)
            stype = "skill"
        elif args in stats_and_skills._domskills_:
            try:
                dompc = caller.player.Dominion
                current = getattr(dompc, args)
                resource = stats_and_skills.get_dom_resource(args)
                if getattr(dompc, args) >= 10:
                    caller.msg("%s is already at its maximum." % args)
                    return
                cost = stats_and_skills.get_dom_cost(caller, args)
                stype = "dom"
            except Exception:
                caller.msg("Dominion object not found.")
                return
        elif args in stats_and_skills._valid_abilities_:
            # if we don't have it, determine if we can learn it
            if not caller.db.abilities.get(args, 0):
                if args in stats_and_skills._crafting_abilities_:
                    # check if we have valid skill:
                    if args == "tailor" and "sewing" not in caller.db.skills:
                        caller.msg("You must have sewing to be a tailor.")
                        return
                    if (args == "weaponsmith" or args == "armorsmith") and "smithing" not in caller.db.skills:
                        caller.msg("You must have smithing to be a %s." % args)
                        return
                    if args == "apothecary" and "alchemy" not in caller.db.skills:
                        caller.msg("You must have alchemy to be an apothecary.")
                        return
                    if args == "leatherworker" and "tanning" not in caller.db.skills:
                        caller.msg("You must have tanning to be a leatherworker.")
                        return
                    if args == "carpenter" and "woodworking" not in caller.db.skills:
                        caller.msg("You must have woodworking to be a carpenter.")
                        return
                    if args == "jeweler" and "smithing" not in caller.db.skills:
                        caller.msg("You must have smithing to be a jeweler.")
                        return
                    spec_warning = True
                elif not caller.check_permstring(args):
                    caller.msg("You do not have permission to learn %s." % args)
                    return
                else:
                    spec_warning = False
            if caller.db.abilities.get(args, 0) >= 6:
                caller.msg("%s is already at its maximum." % args)
                return
            set_specialization = False
            if args in stats_and_skills._crafting_abilities_:
                spec_warning = True
            if caller.db.abilities.get(args, 0) == 5:
                if caller.db.crafting_profession:
                    caller.msg("You have already chosen a crafting specialization.")
                    return
                else:
                    set_specialization = True
                    spec_warning = False
            stype = "ability"
            cost = stats_and_skills.get_ability_cost(caller, args)
        else:
            caller.msg("%s wasn't identified as either a stat, ability, or a skill." % args)
            return
        if "cost" in self.switches:           
            caller.msg("Cost for %s: %s" % (self.args, cost))
            return
        if "spend" in self.switches:
            if stype == "dom" and cost > getattr(dompc.assets, resource):
                msg = "Unable to buy influence in %s. The cost is %s, " % (args, cost)
                msg += "and you have %s %s resources available." % (getattr(dompc.assets, resource), resource)
                caller.msg(msg)
                return
            elif cost > caller.db.xp:
                caller.msg("Unable to raise %s. The cost is %s, and you have %s xp." % (args, cost, caller.db.xp))
                return
            if stype == "stat":
                caller.adjust_xp(-cost)
                stats_and_skills.adjust_stat(caller, args)
                caller.msg("You have increased your %s for a cost of %s xp." % (args, cost))
                caller.msg("XP remaining: %s" % caller.db.xp)
                return
            if stype == "skill":
                caller.adjust_xp(-cost)
                stats_and_skills.adjust_skill(caller, args)
                skill_history = caller.db.skill_history or {}
                spent_list = skill_history.get(args, [])
                spent_list.append(cost)
                skill_history[args] = spent_list
                caller.db.skill_history = skill_history
                caller.msg("You have increased your %s for a cost of %s xp." % (args, cost))
                return
            if stype == "ability":
                if set_specialization:
                    caller.db.crafting_profession = args
                    caller.msg("You have set your primary ability to be %s." % args)
                if spec_warning:
                    caller.msg("{wNote: The first crafting ability raised to 6 will be your specialization.{n")
                caller.adjust_xp(-cost)
                stats_and_skills.adjust_ability(caller, args)
                ability_history = caller.db.ability_history or {}
                spent_list = ability_history.get(args, [])
                spent_list.append(cost)
                ability_history[args] = spent_list
                caller.db.ability_history = ability_history
                caller.msg("You have increased your %s for a cost of %s xp." % (args, cost))
                return
            if stype == "dom":
                # charge them influence
                setattr(dompc.assets, resource, getattr(dompc.assets, resource) - cost)
                stats_and_skills.adjust_dom(caller, args)
                caller.msg("You have increased your %s influence for a cost of %s %s resources." % (args, resource, cost))
                dompc.assets.save()
                return
            return
        # invalid or no switch + arguments
        caller.msg("Usage: xp/spend <stat, ability or skill>")

class CmdTrain(MuxCommand):
    """
    train

    Usage:
        train/stat  <trainee>=<stat>
        train/skill <trainee>=<skill>

    Allows you to flag a character as being trained with you, imparting a
    temporary xp cost reduction to the appropriate stat or skill. This bonus
    only lasts until they log out or the server reboots, so it should be
    used promptly.

    You may only train one character a week.
    """
    key = "train"
    aliases = ["+train", "teach", "+teach"]
    locks = "cmd:all()"
    help_category = "Progression"
    def func(self):
        "Execute command."
        MAX_TRAINEES = 1
        caller = self.caller
        switches = self.switches
        if not self.lhs or not self.rhs or not self.switches:
            caller.msg("Usage: train/[stat or skill] <character to train>=<name of stat or skill to train>")
            return
        targ = caller.search(self.lhs)
        currently_training = caller.db.currently_training or []
        if len(currently_training) > MAX_TRAINEES:
            caller.msg("You are training as many people as you can handle.")
            return
        if not targ:
            caller.msg("No one to train by the name of %s." % self.lhs)
            return
        if "stat" in switches:
            stat = self.rhs.lower()
            if stat not in stats_and_skills._valid_stats_:
                caller.msg("%s is not a valid stat." % self.rhs)
                return
            if caller.attributes.get(stat) <= targ.attributes.get(stat) + 1:
                caller.msg("Your %s is not high enough to train %s." % (stat, targ.name))
                return
        elif "skill" in switches:
            skill = self.rhs.lower()
            if skill not in stats_and_skills._valid_skills_:
                caller.msg("%s is not a valid skill." % self.rhs)
                return
            if caller.db.skills.get(skill, 0) <= targ.db.skills.get(skill, 0) + 1:
                caller.msg("Your %s is not high enough to train %s." % (skill, targ.name))
                return
            stat = skill
        else:
            caller.msg("Usage: train/[stat or skill] <character>=<stat or skill name>")
            return
        targ.db.trainer = caller
        currently_training.append(targ)
        caller.db.currently_training = currently_training
        caller.msg("You have provided training to %s for them to increase their %s." % (targ.name, stat))
        targ.msg("%s has provided you training, helping you increase your %s." % (caller.name, stat))
        return
         
        

class CmdAwardXP(MuxPlayerCommand):
    """
    @awardxp

    Usage:
        @awardxp  <character>=<value>

    Gives some of that sweet, sweet xp to a character.
    """
    key = "@awardxp"
    locks = "cmd:perm(Wizards)"
    help_category = "Progression"
    def func(self):
        "Execute command."
        caller = self.caller
        targ = caller.search(self.lhs)
        val = self.rhs
        if not val or not val.isdigit():
            caller.msg("Invalid syntax.")
            return
        if not targ:
            caller.msg("No player found by that name.")
            return
        char = targ.db.char_ob
        if not char:
            caller.msg("No active character found for that player.")
            return
        char.adjust_xp(int(val))
        caller.msg("Giving %s xp to %s." % (val, char))
        if not caller.check_permstring("immortals"):
            inform_staff("%s has adjusted %s's xp by %s." % (caller, char, val))

class CmdAdjustSkill(MuxPlayerCommand):
    """
    @adjustskill

    Usage:
        @adjustskill  <character>/<skill>=<value>
        @adjustability <character>/<ability>=<value>
        @adjustskill/ability <character>/<ability>=<value>
        @adjustskill/reset <character>=<vocation>
        @adjustskill/refund <character>=<skill>
        @adjustability/refund <character>=<ability>

    Changes character's skill to be set to the value. Stats can be changed
    by @set character/<stat>=value, but skills are stored in a dict and are
    easier to do with this command.

    Reset will set a character's stats and skills to the starting values
    for the given vocation, and reset how much xp they have to spend based
    on their lifetime earned xp + the bonus for their social rank.
    """
    key = "@adjustskill"
    locks = "cmd:perm(Wizards)"
    help_category = "Progression"
    aliases = ["@adjustskills", "@adjustability", "@adjustabilities"]
    def func(self):
        "Execute command."
        caller = self.caller
        ability = "ability" in self.switches or self.cmdstring == "@adjustability" or self.cmdstring == "@adjustabilities"
        if "reset" in self.switches:
            try:
                char = caller.search(self.lhs).db.char_ob
            except (AttributeError, ValueError, TypeError):
                caller.msg("No player by that name.")
                return
            try:
                from game.gamesrc.commands.guest import setup_voc, XP_BONUS_BY_SRANK
                rhs = self.rhs.lower()
                setup_voc(char, rhs)
                char.db.vocation = rhs
                total_xp = char.db.total_xp or 0
                total_xp = int(total_xp)
                xp = XP_BONUS_BY_SRANK[char.db.social_rank]
                xp += total_xp
                char.db.xp = xp
                caller.msg("%s has had their skills and stats set up as a %s." % (char,rhs))
                return
            except (AttributeError, ValueError, TypeError, KeyError):
                caller.msg("Could not set %s to %s vocation." % (char, self.rhs))
                return
        try:
            player, skill = self.lhs.strip().split("/")
            rhs = int(self.rhs)
        except (AttributeError, ValueError, TypeError):
            caller.msg("Invalid syntax")
            return
        targ = caller.search(player)
        if not targ:
            caller.msg("No player found by that name.")
            return
        char = targ.db.char_ob
        if not char:
            caller.msg("No active character for %s." % targ)
            return
        if "refund" in self.switches:
            if not ability:
                skill_history = char.db.skill_history or {}
                try:
                    skill_list = skill_history[self.rhs]
                    cost = skill_list.pop()
                except KeyError:
                    current = caller.db.skills[self.rhs]
                    cost = stats_and_skills.cost_at_rank(caller, self.rhs, current - 1, current)
                char.db.skills[self.rhs] -= 1
                char.db.adjust_xp(cost)
            else:
                ability_history = char.db.ability_history or {}
                try:
                    ability_list = ability_history[self.rhs]
                    cost = ability_list.pop()
                except KeyError:
                    current = caller.db.abilities[self.rhs]
                    cost = stats_and_skills.cost_at_rank(caller, self.rhs, current - 1, current)
                char.db.abilities[self.rhs] -= 1
                char.db.adjust_xp(cost)
            caller.msg("%s had %s reduced by 1 and was refunded %s xp." %(char, self.rhs, cost))
            return
        if rhs <= 0:
            try:
                if ability:
                    del char.db.abilities[skill]
                    caller.msg("Removed ability %s from %s." % (skill, char))
                else:
                    del char.db.skills[skill]
                    caller.msg("Removed skill %s from %s." % (skill, char))
            except KeyError:
                caller.msg("%s did not have %s %s." % (char, skill,
                                                       "ability" if ability else "skill"))
                return
        else:
            if ability:
                char.db.abilities[skill.lower()] = rhs
            else:
                char.db.skills[skill.lower()] = rhs
            caller.msg("%s's %s set to %s." % (char, skill, rhs))
        if not caller.check_permstring("immortals"):
            inform_staff("%s set %s's %s skill to %s." % (caller, char, skill, rhs))
        

class CmdVoteXP(MuxPlayerCommand):
    """
    vote

    Usage:
        vote <player>

    Lodges a vote for a character to receive an additional xp point for
    this week due to excellent RP. Please vote for players who have
    impressed you in RP, rather than just your friends. Voting for your
    alts is obviously against the rules.
    """
    key = "vote"
    aliases = ["+vote", "@vote"]
    locks = "cmd:all()"
    help_category = "Progression"
    def count_votes(self):
        num_votes = 0
        players = PlayerDB.objects.filter(roster__current_account__isnull=False,
                                             roster__current_account=self.caller.roster.current_account)
        for player in players:
            votes = player.db.votes or []
            num_votes += len(votes)

        return num_votes
    
    def func(self):
        """
        Stores a vote for the player in the caller's player object, to allow
        for easier sorting from the PlayerDB manager. Players are allowed 5
        votes per week, each needing to be a distinct character with a different
        email address than the caller. Email addresses that are not set (having
        the 'dummy@dummy.com' default, will be rejected as unsuitable.
        """
        caller = self.caller
        if not caller.roster.current_account:
            raise ValueError("ERROR: No PlayerAccount set for this player!")
        if not self.args:
            votes = caller.db.votes or []
            voted_for = list_to_string(votes) or "no one"        
            remaining = 10 - self.count_votes()
            caller.msg("You have voted for %s, and have %s votes remaining." % (voted_for, remaining))
            return
        targ = caller.search(self.args)
        if not targ:
            caller.msg("Vote for who?")
            return
        if targ.roster.current_account == caller.roster.current_account:
            caller.msg("You cannot vote for your alts.")
            return
        votes = caller.db.votes or []
        if targ.roster.roster.name != "Active" and targ not in votes:
            caller.msg("You can only vote for an active character.")
            return     
        if not targ.db.char_ob:
            caller.msg("%s doesn't have a character object assigned to them." % targ)
            return
        if targ in votes:
            caller.msg("Removing your vote for %s." % targ)
            votes.remove(targ)
            caller.db.votes = votes
            return
        num_votes = self.count_votes()
        if num_votes >= 10:
            caller.msg("You have voted %s times, which is the maximum." % num_votes)
            return  
        votes.append(targ)
        caller.db.votes = votes
        caller.msg("Vote recorded for %s." % targ)
