"""
Roster command module.

This will handle things involving the roster manager and character sheets.
Roster Manager will be a roster_manager object, of which only one should
exist in the game. All commands using it should be player commands, to allow
players to peruse characters while OOC if they wish.

"""
from evennia.utils import utils
from server.utils import prettytable
from server.utils.arx_utils import inform_staff
from evennia.commands.default.muxcommand import MuxCommand, MuxPlayerCommand
from datetime import datetime
from commands.commands.jobs import get_apps_manager
from django.db.models import Q
from web.character.models import Roster
from server.utils import arx_more
from typeclasses.bulletin_board.bboard import BBoard


# limit symbol import for API
__all__ = ("CmdRosterList", "CmdAdminRoster", "CmdSheet", "CmdComment", "CmdRelationship")


def get_roster_manager():
    """
    returns roster manager object
    """
    return Roster.objects


def format_header(title):
    message = "\n{w" + "-"*60 + "{n\n"
    message += "{:^60}".format("{w" + title + "{n")
    message += "\n{w" + "-"*60 + "{n"
    return message


def list_characters(caller, character_list, roster_type="Active Characters", roster=None,
                    titles=False, hidden_chars=None, display_afk=False, use_keys=True):
    """
    Formats lists of characters. If we're given a list of 'hidden_chars', we compare
    the list of names in character_list to that, and if any match, we use the data
    in there for the character for things such as idle timer. Otherwise, we use
    the data fromt he roster object for the name match to propogate our fields.
    If display_afk is true, we list the idle timer for each character.
    """
    # format
    message = format_header(roster_type)
    if not character_list or not roster:
        message += "\nNo characters found."
    else:
        if display_afk:
            table = prettytable.PrettyTable(["{wName #",
                                             "{wSex",
                                             "{wAge",
                                             "{wFealty{n",
                                             "{wConcept{n",
                                             "{wSR{n",
                                             "{wIdle{n"])
        else:
            table = prettytable.PrettyTable(["{wName #",
                                             "{wSex",
                                             "{wAge",
                                             "{wFealty{n",
                                             "{wConcept{n",
                                             "{wSR{n"])
        for char in character_list:
            try:
                if use_keys:
                    name = char.key
                else:
                    name = char.name
                charob = char
                char = str(char)
            except AttributeError:
                # this was not an object, but just a name
                name = char
                charob = None
            sex = "-"
            age = "-"
            house = "-"
            concept = "-"
            srank = "-"
            afk = "-"
            # check if the name matches anything in the hidden characters list
            hide = False
            if charob and hasattr(charob, 'is_disguised') and charob.is_disguised:
                hide = True
            if not charob and hidden_chars:
                # convert both to lower case for case-insensitive matching
                match_list = [ob for ob in hidden_chars if ob.name.lower() == char.lower()]
                if match_list:
                    charob = match_list[0]
                    hide = True
            if charob:
                if not use_keys and charob.name and name != charob.name and caller.check_permstring("Builders"):
                    name += "{w(%s){n" % charob.name
                if titles:
                    title = charob.db.longname
                    if title and not hide:
                        name = '{n' + title.replace(char, '{c' + char + '{n')
                # yes, yes, I know they're not the same thing.
                # sex is only 3 characters and gender is 5.
                sex = charob.db.gender
                if not sex or hide:
                    sex = "-"
                sex = sex[0].capitalize()
                age = charob.db.age
                if not age or hide:
                    age = "-"
                house = charob.db.fealty
                if not house or hide:
                    house = "-"
                concept = charob.db.concept
                if not concept or hide:
                    concept = "-"
                srank = charob.db.social_rank
                if not srank or hide:
                    srank = "-"
                if not titles or hide:
                    name = "{c" + name + "{n"
                if display_afk:
                    afk = utils.time_format(charob.idle_time)
            if display_afk:
                table.add_row([name, sex, age, house, concept[:25], srank, afk])
            else:
                table.add_row([name, sex, age, house, concept[:30], srank])
        message += "\n%s" % table                
    message += "\n"
    arx_more.msg(caller, message, justify_kwargs=False)


def change_email(player, email, caller=None):
    from web.character.models import RosterEntry, PlayerAccount, AccountHistory
    try:
        entry = RosterEntry.objects.get(player__username__iexact=player)
    except RosterEntry.DoesNotExist:
        caller.msg("No player found by that name.")
        return
    # entry.previous_emails += "%s\n" % entry.player.email
    entry.player.email = email
    entry.player.save()
    try:
        entry.current_account = PlayerAccount.objects.get(email=email)
    except PlayerAccount.DoesNotExist:
        entry.current_account = PlayerAccount.objects.create(email=email)
    entry.save()
    date = datetime.now()
    if not AccountHistory.objects.filter(account=entry.current_account, entry=entry):
        AccountHistory.objects.create(entry=entry, account=entry.current_account, start_date=date)


def add_note(player, note, caller=None):
    from web.character.models import RosterEntry
    try:
        entry = RosterEntry.objects.get(player__username__iexact=player)
    except RosterEntry.DoesNotExist:
        caller.msg("No player found by that name.")
        return
    new_note = datetime.today().strftime("\n%x: ")
    new_note += note
    # null check
    if not entry.gm_notes:
        entry.gm_notes = ""
    entry.gm_notes += new_note
    entry.save()


def create_comment(sender, receiver, message):
    """
    This helper function will be called both by the @comment command and the
    web form that leaves a comment on a character sheet. The comment is stored
    as a Msg() object, which is placed in the character.db.comments dict, which
    maps the lowercase name of the sending character to a list of any Msg()
    objects they've sent. Msg.header should be the in-game date of when the comment
    was written.
    """
    receiver.messages.add_comment(message, sender)


class CmdRosterList(MuxPlayerCommand):
    """
    @roster - Displays the roster of player characters

    Usage:
       @roster - Displays all available characters.
       @roster/active - Displays only actively played characters.
       @roster/all - Displays active as well as available characters.
       @roster <filter1, filter2,...category1, etc>=<category1 description,
                                                     category2 description,
                                                                etc >
       @roster/view - see a character's @sheet
       @roster/apply <character>=<notes> - apply to play a character

    The @roster command allows you to see lists of all active characters
    as well as all characters that are currently unplayed and available
    for applications. Passing filters as arguments allows you to see
    characters that meet all your criteria. The following basic filters
    are valid: 'male', 'female', 'young', 'adult', 'mature', 'elder',
    'married', and 'single'. There are additional filters that require an
    additional description after the '=' sign to be valid. These are
    'family', 'fealty', 'social rank', and 'concept'.

    For example, if you wanted to search for a female character, the command
    would be '@roster female'. To search for unmarried female characters, you
    would add an additional filter, so the command becomes
    '@roster female,single'. If you wanted to narrow that to only characters
    under the age of 20, it becomes '@roster female,single,young'. To see
    all unmarried female characters who are under the age of 20 who have the
    word 'noblewoman' in their concept:
    '@roster female,young,single,concept=noblewoman'. An example of multiple
    filters that require an argument might be the same search, but now only
    for members of the Grayson royal family. That would look like:
    '@roster female,young,single,concept,family=noblewoman,Grayson'

    Please note that filters are exclusive - you only see results that match
    every filter given, so mutually exclusive filters will return no matches.
    For example, '@roster young, elder' would only look for characters that
    are both simultaneously young and old.

    To see the character sheet of a specific character, please use @sheet.
    
    """

    key = "@roster"
    aliases = ["+roster"]
    help_category = "General"
    locks = "cmd:all()"

    def func(self):
        """Implement the command"""
        caller = self.caller
        args = self.args
        roster = get_roster_manager()
        switches = self.switches
        if not roster:
            return
        if not args:
            # list all characters in active/available rosters
            if 'all' in switches or 'active' in switches:
                char_list = roster.get_all_active_characters()
                list_characters(caller, char_list, "Active Characters", roster, False)
                if 'active' in switches:
                    return
            if 'all' in self.switches or not self.switches:
                char_list = roster.get_all_available_characters()
                list_characters(caller, char_list, "Available Characters", roster, False)
            if caller.check_permstring("Immortals") or caller.check_permstring("Wizards") or \
                    caller.check_permstring("Builders"):
                if 'all' in self.switches or 'unavailable' in self.switches:
                    char_list = roster.get_all_unavailable_characters()
                    list_characters(caller, char_list, "Unavailable Characters", roster, False)
                    if 'unavailable' in self.switches:
                        return
                if 'all' in self.switches or 'incomplete' in self.switches:                
                    char_list = roster.get_all_incomplete_characters()
                    list_characters(caller, char_list, "Incomplete Characters", roster, False)
            return
        if 'view' in switches:
            caller.execute_cmd("@sheet/all %s" % args)
            return
        if 'apply' in switches:
            # will call apps_manager.add_app(char_name, char_ob, email, app_string)
            email = caller.email
            if caller.is_guest():
                # check for email
                email = caller.ndb.email
                if not email:
                    char = caller.db.char
                    if char:
                        email = char.db.player_ob.email
            if not email:
                caller.msg("You have no defined email address, which is required to apply to play another character.")
                if caller.is_guest():
                    caller.msg("You can add an email address with {w@add/email <address>{n")
                else:
                    caller.msg("This account is not a guest, so contact a GM to fix your email.")
                return
            char_name, app_string = self.lhs, self.rhs
            if not char_name or not app_string:
                caller.msg("Usage: @roster/apply <character name>=<application>")
                return
            if len(app_string) < 78:
                caller.msg("Please write a bit more detailed of an application. You should indicate" +
                           " why you want to play the character, how you intend to roleplay them, etc.")
                return
            char_name = char_name.lower()
            apps = get_apps_manager(caller)
            if not apps:
                caller.msg("Application manager not found! Please inform the admins.")
                return
            char_ob = roster.get_character(char_name)
            if not char_ob:
                caller.msg("No such character on the roster.")
                return
            if char_ob.roster.roster.name != "Available":
                caller.msg("That character is not marked as available for applications.")
                return
            apps.add_app(char_ob, email, app_string)
            mess = "Successfully applied to play %s. " % char_name.capitalize()
            mess += "You will receive a response by email once your application has been approved or declined."
            caller.msg(mess)
            message = "{wNew character application by [%s] for %s" % (caller.key.capitalize(), char_name.capitalize())
            inform_staff(message)
            return
        if ('family' in args or 'fealty' in args or 'concept' in args) and not self.rhs:
            caller.msg("The filters of 'family', 'fealty', 'social class', " +
                       "or 'concept' require an argument after an '='.")
            return
        if not self.rhs:
            filters = args.split(",")
            if 'all' in switches:
                match_list = roster.search_by_filters(filters)
                if match_list:
                    match_list = [_char.key.capitalize() for _char in match_list]
                list_characters(caller, match_list, "Active Characters", roster, False)
            match_list = roster.search_by_filters(filters, "available")
            if match_list:
                match_list = [_char.key.capitalize() for _char in match_list]
            list_characters(caller, match_list, "Available Characters", roster, False)
            return
        rhslist = self.rhslist
        lhslist = self.lhslist
        keynames = []
        for attr_filter in lhslist:
            if attr_filter in ['family', 'fealty', 'concept', 'social rank']:
                keynames.append(attr_filter)
        if len(keynames) != len(rhslist):
            caller.msg("Not enough arguments provided for the given filters.")
            return
        filtdict = dict(zip(keynames, rhslist))
        family = filtdict.get('family', "None")
        fealty = filtdict.get('fealty', "None")
        concept = filtdict.get('concept', "None")
        social_rank = filtdict.get('social rank', "None")
        if 'all' in switches:
            match_list = roster.search_by_filters(lhslist, "active", concept, fealty, social_rank, family)
            list_characters(caller, match_list, "Active Characters", roster, False)
        match_list = roster.search_by_filters(lhslist, "available", concept, fealty, social_rank, family)
        list_characters(caller, match_list, "Available Characters", roster, False)
        return


class CmdAdminRoster(MuxPlayerCommand):
    """
    @chroster - Changes the roster. Admin commands.

    Usage:
        @chroster/move   <entry>=<new roster area>
        @chroster/note   <entry>=<Added note>
        @chroster/email  <entry>=<new email>
        @chroster/retire <entry>=<notes>

    Admin for roster commands. Added characters go in unavailable
    and inactive section until moved to active section. 
    """
    key = "@chroster"
    help_category = "Admin"
    locks = "cmd:perm(chroster) or perm(Wizards)"

    @staticmethod
    def award_alt_xp(alt, xp, history, current):
        if xp > current.total_xp:
            xp = current.total_xp
        altchar = alt.entry.character
        if xp > history.xp_earned:
            xp = history.xp_earned
        if not altchar.db.xp:
            altchar.db.xp = 0
        altchar.db.xp += xp

    def func(self):
        caller = self.caller
        args = self.args
        switches = self.switches
        if not args or not switches:
            caller.msg("Usage: @chroster/switches <arguments>")
            return
        from web.character.models import RosterEntry, Roster, AccountHistory
        if 'add' in switches:
            try:
                RosterEntry.objects.get(character__db_key__iexact=self.lhs)
                caller.msg("Character already is in the roster.")
                return
            except RosterEntry.DoesNotExist:
                active = Roster.objects.get(name__iexact="active")
                targ = caller.search(self.lhs)
                if not targ:
                    return
                active.entries.create(player=targ, character=targ.db.char_ob)
                caller.msg("Character added to active roster.")
                return
        if 'move' in switches:
            lhs = self.lhs
            rhs = self.rhs
            try:
                entry = RosterEntry.objects.get(character__db_key__iexact=lhs)
                roster = Roster.objects.get(name__iexact=rhs)
                entry.roster = roster
                entry.save()
                inform_staff("%s moved %s to %s roster." % (caller, lhs, rhs))
                caller.msg("Moved %s to %s roster." % (lhs, rhs))
                return
            except Exception as err:
                caller.msg("Move failed: %s" % err)
                return
        if 'retire' in switches:
            active = Roster.objects.get(name__iexact="active")
            avail = Roster.objects.get(name__iexact="available")
            try:
                entry = active.entries.get(character__db_key__iexact=self.lhs)
            except RosterEntry.DoesNotExist:
                caller.msg("Character not found in active roster.")
                return
            entry.roster = avail
            current = entry.current_account 
            xp = entry.character.db.xp or 0
            try:
                history = AccountHistory.objects.get(account=current, entry=entry)         
                if xp < 0:
                    xp = 0
                try:
                    alt = AccountHistory.objects.get(Q(account=current) & ~Q(entry=entry))
                    self.award_alt_xp(alt, xp, history, current)
                except AccountHistory.DoesNotExist:
                    if xp > current.total_xp:
                        xp = current.total_xp
                    # null check
                    if not current.gm_notes:
                        current.gm_notes = ""
                    current.gm_notes += "\n\nUnspent xp: %s" % xp
                    current.save()
                except AccountHistory.MultipleObjectsReturned:
                    caller.msg("ERROR: Found more than one account. Using the first.")
                    alt = AccountHistory.objects.filter(Q(account=current) & ~Q(entry=entry)).first()
                    self.award_alt_xp(alt, xp, history, current)
                except Exception as err:
                    import traceback
                    print "{rEncountered this error when trying to transfer xp{n:\n%s" % err
                    traceback.print_exc()
                entry.character.db.xp = 0
                entry.character.db.total_xp = 0
            except AccountHistory.DoesNotExist:
                history = AccountHistory.objects.create(account=current, entry=entry)
            entry.current_account = None
            entry.save()
            date = datetime.now()
            history.end_date = date
            if not history.gm_notes and self.rhs:
                history.gm_notes = self.rhs
            elif self.rhs:
                history.gm_notes += self.rhs
            history.save()
            # set up password
            # noinspection PyBroadException
            try:
                import string
                import random
                newpass = ''.join(random.choice(string.ascii_uppercase + string.digits) for _ in range(8))
                entry.player.set_password(newpass)
                entry.player.save()
                caller.msg("Random password generated for %s." % entry.player)
            except Exception:
                import traceback
                traceback.print_exc()
                caller.msg("Error when setting new password. Logged.")
            inform_staff("%s has returned %s to the available roster." % (caller, self.lhs))
            try:
                bb = BBoard.objects.get(db_key__iexact="Roster Changes")
                msg = "%s no longer has an active player and is now available for applications." % entry.character
                subject = "%s now available" % entry.character
                bb.bb_post(self.caller, msg, subject=subject, poster_name="Roster")
            except BBoard.DoesNotExist:
                self.msg("Board not found for posting announcement")
            return
        if 'view' in switches:
            try:
                entry = RosterEntry.objects.get(character__db_key__iexact=self.args)
            except RosterEntry.DoesNotExist:
                caller.msg("No character found by that name.")
                return
            caller.msg("{w" + "-"*20 + "{n")
            caller.msg("{wPlayer Object:{n %s {wID:{n %s" % (entry.player.key, entry.player.id))
            line = "{wCharacter: {n"
            line += entry.character.key
            line += " {wID:{n %s" % entry.character.id
            caller.msg(line)
            line = "{wGM Notes:{n " + entry.gm_notes
            caller.msg(line)
            if entry.current_account:
                caller.msg("{wCurrent Account:{n %s" % entry.current_account)
                caller.msg("{wAlts:{n %s" % ", ".join(str(ob) for ob in entry.alts))
            return
        if 'email' in switches:
            lhs, rhs = self.lhs, self.rhs
            if not lhs or not rhs:
                caller.msg("Usage: @chroster/email user=email")
                return
            change_email(lhs, rhs, caller)
            inform_staff("%s changed email for %s in roster." % (caller, lhs))
            caller.msg("Email for %s changed to %s." % (lhs, rhs))
            return
        if 'note' in switches:
            lhs = self.lhs
            if not lhs:
                caller.msg("Usage: @chroster/note <character>=<note>")
                return
            if not self.rhs:
                caller.msg("Cannot add an empty note.")
                return
            add_note(lhs, self.rhs, caller)
            inform_staff("%s added a note to %s in roster." % (caller, lhs))
            caller.msg("New note added.")
            return


def display_header(caller, character, show_hidden=False):
    """
    Header information. Name, Desc, etc.
    """
    if not caller or not character:
        return
    longname = character.db.longname
    if not longname:
        longname = character.key
        if not longname:
            longname = "Unknown"
    longname.capitalize()
    longname = longname.center(60)
    quote = character.db.quote
    if not quote:
        quote = ""
    else:
        quote = '"' + quote + '"'
        quote = quote.center(60)
    srank = character.db.social_rank
    if not srank:
        srank = "Unknown"
    concept = character.db.concept
    if not concept:
        concept = "Unknown"
    fealty = character.db.fealty
    if not fealty:
        fealty = "Unknown"
    fealty = fealty.capitalize()
    family = character.db.family
    if not family:
        family = "Unknown"
    family = family.capitalize()
    gender = character.db.gender
    if not gender:
        gender = "Unknown"
    gender = gender.capitalize()
    age = character.db.age
    if not age:
        age = "Unknown"
    else:
        age = str(age)   
    birth = character.db.birthday
    if not birth:
        birth = "Unknown"
    religion = character.db.religion
    if not religion:
        religion = "Unknown"
    vocation = character.db.vocation
    if not vocation:
        vocation = "Unknown"
    vocation = vocation.capitalize()
    height = character.db.height or ""
    eyecolor = character.db.eyecolor or ""
    eyecolor = eyecolor.title()
    haircolor = character.db.haircolor or ""
    haircolor = haircolor.title()
    skintone = character.db.skintone or ""
    skintone = skintone.title()
    marital_status = character.db.marital_status or "Single"

    header = \
        """
{w%(longname)s{n
%(quote)s
{w==================================================================={n
{wSocial Rank:{n %(srank)-20s {wConcept:{n %(concept)-20s
{wFealty:{n %(fealty)-25s {wFamily:{n %(family)-20s
{wGender:{n %(gender)-25s {wAge:{n %(age)-20s
{wBirthday:{n %(birth)-23s {wReligion:{n %(religion)-20s
{wVocation:{n %(vocation)-23s {wHeight:{n %(height)-20s
{wEye Color:{n %(eyecolor)-22s {wHair Color:{n %(haircolor)-20s
{wSkin Tone:{n %(skintone)-22s {wMarital Status:{n %(marital_status)-20s
        """ % {'longname': longname, 'quote': utils.fill(quote), 'srank': srank,
               'concept': concept, 'fealty': fealty, 'family': family,
               'gender': gender, 'age': age, 'birth': birth, 'religion': religion,
               'vocation': vocation, 'height': height, 'eyecolor': eyecolor,
               'haircolor': haircolor, 'skintone': skintone, 'marital_status': marital_status,
               }
    caller.msg(header)
    desc = character.desc
    if not desc:
        desc = "No description set."
    if show_hidden:
        rconcept = character.db.real_concept
        rage = character.db.real_age
        if rconcept or rage:
            mssg = ""
            if rconcept:
                mssg = "{w(Real Concept):{n %s \t\t\t" % rconcept
            if rage:
                mssg += "{w(Real Age):{n %s" % rage
            caller.msg(mssg)
    caller.msg("{wDescription:{n \n%s\n" % desc)
    return


def display_stats(caller, character):
    """
    Display character attributes. Str, int, etc.
    """
    title = "Stats"
    title = title.center(60)
    # It might make more sense to have a 3 character variable for
    # strength named 'str', but rather not be identical to str cast
    stg = character.db.strength
    if not stg:
        stg = 0
    dex = character.db.dexterity
    if not dex:
        dex = 0
    sta = character.db.stamina
    if not sta:
        sta = 0
    cha = character.db.charm
    if not cha:
        cha = 0
    cmd = character.db.command
    if not cmd:
        cmd = 0
    comp = character.db.composure
    if not comp:
        comp = 0
    # As above for str, so for using intel for int
    intel = character.db.intellect
    if not intel:
        intel = 0
    per = character.db.perception
    if not per:
        per = 0
    wit = character.db.wits
    if not wit:
        wit = 0
        
    disp = \
        """
{w==================================================================={n
{w%(title)s{n

{wPhysical                Social                Mental

{wStrength:{n %(stg)s            {wCharm:{n %(cha)s             {wIntellect:{n %(intel)s
{wDexterity:{n %(dex)s           {wCommand:{n %(cmd)s           {wPerception:{n %(per)s
{wStamina:{n %(sta)s             {wComposure:{n %(cmp)s         {wWits:{n %(wit)s
        """ % {'title': title, 'stg': stg, 'cha': cha, 'intel': intel,
               'dex': dex, 'cmd': cmd, 'per': per, 'sta': sta, 'cmp': comp,
               'wit': wit
               }
    disp = disp.rstrip()
    caller.msg(disp)
    mana = character.db.mana
    if not mana:
        mana = 0
    luck = character.db.luck
    if not luck:
        luck = 0
    will = character.db.willpower
    if not will:
        will = 0
    title = "Special Stats"
    title = title.center(60)
    disp = \
        """
{w%(title)s{n

{wMana:{n %(mana)s                {wLuck:{n %(luck)s             {wWillpower:{n %(will)s
        """ % {'title': title, 'mana': mana, 'luck': luck, 'will': will}
    disp = disp.rstrip()
    caller.msg(disp)
    pass


def display_title(caller, title):
    title = title.center(60)
    disp = \
        """
{w==================================================================={n
{w%(title)s{n
        """ % {'title': title}
    caller.msg(disp)


def display_skills(caller, character):
    """
    Display skills the character knows.
    """
    def format_skillstr(skill_name, skill_value):
        skstr = "{w%s: {n%s" % (skill_name.capitalize(), str(skill_value))
        skstr = "%-22s" % skstr
        return skstr
    title = "Skills"
    skills = character.db.skills
    if not skills:
        skillstr = "No skills known."
    else:
        skillstr = ""
        skills = character.db.skills.items()
        skills = sorted(skills)
        skills_count = 0
        for skill, value in skills:
            if value <= 0:
                continue
            skills_count += 1           
            skillstr += format_skillstr(skill, value)
            # only have 4 skills per line for formatting
            if skills_count % 4 == 0:
                skillstr += "\n"
    display_title(caller, title)
    caller.msg(skillstr)
    try:
        dompc = character.db.player_ob.Dominion
        domskills = ("population", "income", "farming", "productivity",
                     "upkeep", "loyalty", "warfare")
        skillstr = ""
        skills_count = 0
        title = "Dominion Influence"
        for skill in domskills:
            value = getattr(dompc, skill)
            if value > 0:
                skills_count += 1
                skillstr += format_skillstr(skill, value)
                if skills_count % 4 == 0:
                    skillstr += "\n"
        if skillstr:
            display_title(caller, title)
            caller.msg(skillstr)
    except AttributeError:
        pass


def display_abilities(caller, character):
    """
    Display magical abilities and attributes tied to that.
    """
    title = "Abilities"
    abilities = character.db.abilities
    if not abilities:
        abilstr = "No abilities known."
    else:
        abilstr = ""
        abilities = character.db.abilities.items()
        abilities = sorted(abilities)
        abilities_count = 0
        for ability, value in abilities:
            abilities_count += 1
            abstr = "{w" + ability.capitalize() + ": {n" + str(value)
            abstr = "%-22s" % abstr
            abilstr += abstr
            # only have 4 skills per line for formatting
            if abilities_count % 4 == 0:
                abilstr += "\n"
    display_title(caller, title)
    caller.msg(abilstr)


def display_relationships(caller, character, show_hidden=False):
    """
    Display short version of relationships. Long will
    be done by @relationship command separately.
    """
    if hasattr(character, 'get_fancy_name'):
        name = character.get_fancy_name(short=False)
    else:
        name = character.key
    if not name:
        name = "Unknown"
    if character.db.player_ob and hasattr(character.db.player_ob, 'Dominion'):
        dompc = character.db.player_ob.Dominion
        if dompc.patron:
            caller.msg("{wPatron:{n %s" % str(dompc.patron))
        proteges = dompc.proteges.all()
        if proteges:
            caller.msg("{wProteges:{n %s" % ", ".join(str(ob) for ob in proteges))
    caller.msg("\n{wSocial circle for {c%s{n:\n------------------------------------" % name)
    
    # relationship_short is a dict of types of relationships to a list of tuple of
    # character name and a very brief (2-3 word) description enclosed in parens.
    # More detailed relationships will be in character.db.relationships
    relationships = character.db.relationship_short
    if not relationships:
        caller.msg("No relationships found.")
        return
    showed_matches = False
    for rel_type, rel_value in sorted(relationships.items()):
        # rel_type will be 'Parent', 'Sibling', 'Friend', 'Enemy', etc
        # display it either if it's not secret, or if show_hidden is True
        if rel_type != 'secret' or show_hidden:          
            if rel_value:
                showed_matches = True
                disp = "{w%s: {n" % rel_type.capitalize()
                entrylist = []
                for entry in sorted(rel_value):
                    name, desc = entry
                    entrystr = "%s (%s)" % (name.title(), desc)
                    entrylist.append(entrystr)
                value_str = ", ".join(entrylist)
                disp += value_str
                caller.msg(disp)
    if not showed_matches:
        # everything was secret that we didn't display.
        caller.msg("No relationships found.")
    pass


def display_comment_list(caller, character):
    """
    Display list of names of who have left comments on character
    """
    if character == caller.db.char_ob:
        caller.db.new_comments = False
    name = character.key.capitalize()
    caller.msg("{wCharacters who have left comments on %s:\n--------------------------------------" % name)
    comment_list = character.messages.comments
    if not comment_list:
        caller.msg("No comments have been left yet.")
        return
    disp = ""
    for name in sorted(comment_list.keys()):
        disp += "%s\t" % name.capitalize()
    caller.msg(disp)
    caller.msg("To see individual comments, use @sheet/comments <character>=<commenter>.")
    pass


def display_secrets(caller, character):
    """
    Display secrets
    """
    caller.msg("{wSecrets for %s:{n" % character.key.capitalize())
    caller.msg("{w-------------------------------{n")
    secrets = character.db.secrets
    if not secrets:
        caller.msg("No secrets to display.")
        return
    for num, secret in enumerate(secrets):
        caller.msg("{w%s) {n%s" % ((num + 1), secret))
    return


def display_visions(caller, character):
    """
    Displays visions
    """
    caller.msg("{wVisions for %s:{n" % character.key.capitalize())
    caller.msg("{w-------------------------------{n")
    visions = character.messages.visions
    if not visions:
        caller.msg("No visions to display.")
        return
    for vision in visions:
        caller.msg(character.messages.disp_entry(vision), options={'box': True})
        vision.receivers = caller


# noinspection PyUnusedLocal
def display_timeline(caller, character):
    """
    Display character timeline
    """
    pass


class CmdSheet(MuxPlayerCommand):
    """
    @sheet - Displays a character's sheet.

    Usage:
        @sheet <character name>
        @sheet/social <character name>
        @sheet/relationships <character name>
        @sheet/relationships <character>=<other character>
        @sheet/privaterels <character name>
        @sheet/privaterels <character name>=<other character>
        @sheet/secrets
        @sheet/visions
        @sheet/background <character>
        @sheet/personality <character>
        @sheet/comments <character>=<commenting character>
        @sheet/desc
        @sheet/stats
        @sheet/all

    Displays the character sheet of a player character. Only public
    information is displayed for a character you do not own, such
    as public relationships, and comments which are public statements
    and widely known gossip.

    @sheet/background displays a character's background written in
    the character's own words. @sheet/info displays notes about the
    character's personality. @sheet/relationships is a brief outline
    of the character's relationships. @sheet/comments displays quotes
    from other characters that display their publicly known opinions
    upon that character.
    """
    key = "@sheet"
    aliases = ["+sheet", "sheet"]
    help_category = "General"
    locks = "cmd:all()"

    def func(self):
        caller = self.caller
        args = self.args
        switches = self.switches
        show_hidden = False
        # permissions = str(caller.permissions)
        # if 'builders' in permissions or 'wizards' in permissions or 'immortals' in permissions:
        if caller.check_permstring("builders"):
            show_hidden = True
        if 'all' in switches:
            if not args:
                charob = caller.db.char_ob if not caller.is_guest() else caller.db.char
                show_hidden = True
            else:
                playob = caller.search(args)
                if not playob:
                    caller.msg("No character found by that name.")
                    return
                charob = playob.db.char_ob
                if charob == caller.db.char_ob:
                    show_hidden = True
            if not charob:
                caller.msg("No character found to @sheet.")
                return
            if not show_hidden and charob.roster.roster.name == "Unavailable":
                caller.msg("You cannot sheet that character.")
                return
            display_header(caller, charob, show_hidden)
            if show_hidden:
                display_stats(caller, charob)
                display_skills(caller, charob)
                display_abilities(caller, charob)            
                display_secrets(caller, charob)
                display_visions(caller, charob)
            display_relationships(caller, charob, show_hidden)          
            bground = charob.db.background
            if not bground:
                bground = "No background written yet."
            caller.msg("\n{wBackground:{n\n" + bground)
            pers = charob.db.personality
            if not pers:
                pers = "No personality written yet."
            caller.msg("\n{wPersonality:{n\n " + pers)
            display_comment_list(caller, charob)
            return
        if not switches or 'desc' in switches or 'stats' in switches:
            if not args:
                charob = caller.db.char_ob if not caller.is_guest() else caller.db.char
                show_hidden = True
            else:
                playob = caller.search(args)
                if not playob:
                    caller.msg("No character found by that name.")
                    return
                charob = playob.db.char_ob
            if not charob:
                caller.msg("No character found to @sheet.")
                return
            if charob.db.npc and not show_hidden:
                caller.msg("That character is an npc and cannot be viewed.")
                return
            if 'stats' not in switches:
                display_header(caller, charob, show_hidden)
            if show_hidden and 'desc' not in switches:
                display_stats(caller, charob)
                display_skills(caller, charob)
                display_abilities(caller, charob)                                
            return
        if 'secrets' in switches or 'secret' in switches:
            if args and show_hidden:
                playob = caller.search(args)
                if not playob:
                    caller.msg("No player found by that name.")
                    return
                charob = playob.db.char_ob
            else:
                charob = caller.db.char_ob or caller.db.char
            if not charob:
                caller.msg("No character found.")
                return
            display_secrets(caller, charob)
            return
        if 'visions' in switches or 'vision' in switches:
            if args and show_hidden:
                playob = caller.search(args)
                if not playob:
                    caller.msg("No player found by that name.")
                    return
                charob = playob.db.char_ob
            else:
                charob = caller.db.char_ob or caller.db.char
            if not charob:
                caller.msg("No character found.")
                return
            display_visions(caller, charob)
            return
        if 'social' in switches or 'background' in switches or 'info' in switches or 'personality' in switches:
            if not args:
                charob = caller.db.char_ob or caller.db.char
                show_hidden = True
            else:
                playob = caller.search(args)
                if not playob:
                    caller.msg("No character found by that name.")
                    return
                charob = playob.db.char_ob
            if not charob:
                caller.msg("No character found to @sheet.")
                return
            if charob.db.npc and not show_hidden:
                caller.msg("That character is an npc and cannot be viewed.")
                return
            if 'social' in switches:
                display_relationships(caller, charob, show_hidden)
                return
            elif 'background' in switches:
                bground = charob.db.background
                if not bground:
                    bground = "No background written yet."
                caller.msg("{wBackground:{n\n" + bground)
                return
            elif 'personality' in switches:
                pers = charob.db.personality
                if not pers:
                    pers = "No personality written yet."
                caller.msg("{wPersonality:{n\n " + pers)
                return
            return
        if 'comments' in switches or 'comment' in switches:
            # 3 use cases - no args, only lhs, and lhs=rhs
            # first check for no args. If so, that's a character
            # looking at their own comments list.
            if not args:
                # just a list of who has left comments on the player
                charob = caller.db.char_ob
                if not charob:
                    caller.msg("You have no character object to check.")
                    return
                display_comment_list(caller, charob)
                return
            else:
                args = self.args.lower()
                rhs = self.rhs
                if not rhs:
                    playob = caller.search(args)
                    if not playob:
                        caller.msg("No character found by that name.")
                        return
                    charob = playob.db.char_ob
                    if not charob:
                        caller.msg("No character found to @sheet.")
                        return
                    # list of who has left comments on the player
                    display_comment_list(caller, charob)
                    return
                else:
                    # We'll be looking for a list of all comments left by
                    # the character specified by self.rhs
                    rhs = self.rhs.lower()
                    lhs = self.lhs.lower()
                    if not lhs:
                        playob = caller
                    else:
                        playob = caller.search(lhs)
                    if not playob:
                        caller.msg("No character found by that name.")
                        return
                    charob = playob.db.char_ob
                    if not charob:
                        caller.msg("No character found to @sheet.")
                        return
                    comments = charob.messages.comments
                    if not comments:
                        caller.msg("No comments left on that character.")
                        return
                    # comments is a dict of character_name: comments_list
                    match = comments.get(rhs)
                    if not match:
                        caller.msg("No comments found by that character.")
                        return
                    # comments_list is a dict of date: comments
                    caller.msg("{wComments on %s by %s:{n" % (lhs.capitalize(), rhs.capitalize()))
                    for entry in match:
                        date, comment = charob.messages.get_date_from_header(entry), entry.message
                        caller.msg("%s:  %s" % (date, comment))
                    return
        if 'relationships' in self.switches or 'privaterels' in self.switches:
            targ = None
            if self.rhs:
                targ = caller.search(self.rhs)
                if not targ:
                    return
                targ = targ.db.char_ob
            if not self.lhs:
                char = caller
            else:
                char = caller.search(self.lhs)
            if not char:
                return
            char = char.db.char_ob
            if not char:
                caller.msg("No character found.")
                return
            journal = char.messages.white_relationships if 'privaterels' not in self.switches else \
                char.messages.black_relationships
            jname = "White Journal" if 'privaterels' not in self.switches else "Black Journal"
            if not targ:
                # we just display the most recent relationship status for each character
                caller.msg("Relationships you are permitted to read in {c%s{n's %s:" % (char, jname))
                for name in journal:
                    msglist = journal[name]
                    msglist = [msg for msg in msglist if msg.access(caller, 'read')]
                    if not msglist:
                        continue
                    msg = msglist[0]
                    caller.msg("\nMost recent relationship note on %s:" % name)
                    caller.msg(char.messages.disp_entry(msg))
                    # add viewer to receivers
                    msg.receivers = caller
                return
            caller.msg("Relationship notes you are permitted to read for {c%s{n in {c%s{n's %s:" % (targ, char, jname))
            msglist = [_msg for _msg in journal.get(targ.key.lower(), []) if _msg.access(caller, 'read')]
            if not msglist:
                caller.msg("No entries for %s." % targ)
                return
            for msg in msglist:
                caller.msg("\n" + char.messages.disp_entry(msg))
                msg.receivers = caller
            return
        caller.msg("Usage: @sheet/switches <character>")
        return


class CmdRelationship(MuxPlayerCommand):
    """
    @relationship - Displays information on a relationship.

    Usage:
        @relationship <name>[=<name>]
        @relationship/list <name>
        @relationship/new <name>=<description>
        @relationship/change <name>=<description>
        @relationship/newprivate <name>=<description>
        @relationship/changeprivate <name>=<description>
        @relationship/short <relationship type>=<name>,<desc>
        @relationship/changeshort <oldtype>,<newtype>=<name>,<desc>
        @relationship/delshort <name>

    Displays information on a relationship with another character,
    written from your character's IC point of view. Descriptions
    should be written in first person. Old relationships are never
    erased - when they are changed, the old relationship notes are
    stored with a timestamp to show how the relationship changed over
    time. Dates of relationship changes will be noted in a character's
    timeline to identify significant events for character development.
    Every relationship that you add should also have a short
    relationship added to it via @relationship/short, with 'secret'
    being the type for secret relationships. Those are not publicly
    viewable by other players.

    To list the relationships of other players, use the /list switch.
    To list your own, simply use @relationship with no arguments.

    For @relationship/short, this builds the {w@sheet/social{n tree
    on a character's sheet, such as friends, family, acquaintances,
    and enemies. For example:
    @relationship/short friend=percy,war buddy

    To create a new relationship or update an existing one, use
    @relationship/change.
    """
    key = "@relationship"
    aliases = ["+relationship", "@relationships", "+relationships"]
    help_category = "Social"
    locks = "cmd:all()"

    def func(self):
        caller = self.caller
        args = self.args
        switches = self.switches
        charob = caller.db.char_ob
        # builders can see /list info
        show_hidden = caller.check_permstring("builders")
        # check if it's a guest modifying their character
        if not charob:
            charob = caller.ndb.char
        if not charob:
            caller.msg("No character found.")
            return
        white = True
        if "newprivate" in self.switches:
            self.switches.append("changeprivate")
        if "changeprivate" in self.switches:
            white = False
        if "new" in self.switches:
            self.switches.append("change")
        jname = "White Journal" if white else "Black Journal"
        if not args or 'list' in self.switches:
            if 'list' in self.switches:
                old = charob
                charob = caller.search(self.lhs)
                if not charob:
                    return
                charob = charob.db.char_ob
                if not charob:
                    caller.msg("No character.")
                    return
                # check to see if this is caller's own character, if so, we show hidden stuff
                if old == charob:
                    show_hidden = True
            if show_hidden:
                rels = dict(charob.messages.white_relationships.items() + charob.messages.black_relationships.items())
            else:
                rels = dict(charob.messages.white_relationships.items())
            # display list of relationships
            if not rels:
                caller.msg("No relationships found.")
            else:
                caller.msg("{w%s has relationships with the following characters:{n" % charob)
                caller.msg("{w--------------------------------------------{n")
                disp = ", ".join(key for key in sorted(rels.keys()))
                caller.msg(disp)
                caller.msg("To see the individual relationships, use {w@relationship %s=<name>{n" % charob)
            caller.msg("\nSocial information for %s:" % charob.key)
            caller.execute_cmd("@sheet/social %s" % charob.key)
            return
        if not switches:
            if not self.lhs and self.rhs:
                char = charob
                name = self.rhs.lower()
            elif self.lhs and not self.rhs:
                char = charob
                name = self.lhs.lower()
            else:
                char = caller.search(self.lhs)
                if not char:
                    return
                char = char.db.char_ob
                if not char:
                    caller.msg("No character.")
                    return
                name = self.rhs.lower()
            white = char.messages.white_relationships
            black = char.messages.black_relationships
            rels = {k: white.get(k, []) + black.get(k, []) for k in set(white.keys() + black.keys())}
            if not rels:
                caller.msg("No relationships found.")
                return
            entries = rels.get(name, [])
            entries = [msg for msg in entries if msg.access(caller, 'read') or 'white' in msg.header]
            if not entries:
                caller.msg("No relationship found.")
                return
            if self.rhs:
                caller.msg("{wRelationship of %s to %s:{n" % (self.lhs.capitalize(), self.rhs.capitalize()))
            else:
                caller.msg("{wRelationship with %s:{n" % args.capitalize())
            sep = "{w-------------------------------------------------------------------{n"
            caller.msg(sep)
            for msg in entries:            
                jname = "{wJournal:{n %s\n" % ("White Journal" if msg in white.get(self.rhs.lower() if self.rhs
                                                                                   else self.args.lower(), [])
                                               else "Black Reflection")
                caller.msg("\n" + jname + charob.messages.disp_entry(msg), options={'box': True})
                msg.receivers = caller
            return
        lhs = self.lhs
        rhs = self.rhs
        if (not lhs or not rhs) and 'delshort' not in switches:
            caller.msg("Usage: @relationship/switches <name>=<description>")
            return
        # lhs will be used for keys, so need to make sure always lower case
        lhs = lhs.lower()
        desc = rhs
        if 'change' in switches or 'changeprivate' in switches:
            targ = caller.search(lhs)
            if not targ:
                return
            targ = targ.db.char_ob
            if not targ:
                caller.msg("No character found.")
                return
            msg = charob.messages.add_relationship(desc, targ, white)
            caller.msg("Entry added to %s:\n%s" % (jname, msg))
            caller.msg("Relationship note added. If the 'type' of relationship has changed, "
                       "such as a friend becoming an enemy, please adjust it with /changeshort.")
            if white:
                charob.msg_watchlist("A character you are watching, {c%s{n, has updated their white journal." % caller)
            return
        typelist = ['parent', 'sibling', 'friend', 'enemy', 'family',
                    'acquaintance', 'secret', 'rival']
        if 'short' in switches:
            rhslist = self.rhslist          
            if lhs not in typelist:
                caller.msg("The type of relationship must be in %s." % str(typelist))
                return
            if len(rhslist) < 2:
                caller.msg("Usage: @relationship/short <type>=<name>,<desc>")
                return
            name = rhslist[0].title()
            desc = ", ".join(rhslist[1:])
            name = name.rstrip()
            desc = desc.lstrip()
            # if there's no relationship tree yet, initialize it as an empty dict
            if not charob.db.relationship_short:
                charob.db.relationship_short = {}
            # if that type of relationship doesn't exist, add it
            if not charob.db.relationship_short.get(lhs):
                charob.db.relationship_short[lhs] = [(name, desc)]
                caller.msg("Short relationship added to tree.")
                return
            # it exists, so add our name/desc tuple to the list
            charob.db.relationship_short[lhs].append((name, desc))
            caller.msg("Short relationship added to tree.")
            return
        if 'changeshort' in switches:
            lhslist = lhs.split(",")
            if not lhslist or len(lhslist) != 2:
                caller.msg("Must have both old type and new type of relationship specified before '='.")
                return
            rhslist = self.rhslist
            if len(rhslist) < 2:
                caller.msg("Must have both name and description specified after '='.")
                return
            rels = charob.db.relationship_short
            if not rels:
                caller.msg("No relationships in tree to change - use /short to add instead.")
                return         
            oldtype, newtype = lhslist[0].lower(), lhslist[1].lower()
            if newtype not in typelist:
                caller.msg("Relationship must be one of the following: %s" % ", ".join(typelist))
                return
            name = rhslist[0].lower()
            desc = ", ".join(rhslist[1:])
            typelist = rels.get(oldtype)
            if not typelist:
                caller.msg("No relationships match the old type given.")
                return
            # now we go through the tuples in the list of that relationship type.
            # if one matches the name, we'll remove it before we add the new one.
            # Names are unique, so we stop with first instance we encounter
            for tups in typelist:
                # each tups == (name, desc)
                if tups[0].lower() == name:
                    # we got a match
                    typelist.remove(tups)
                    break
            if newtype not in rels:
                rels[newtype] = []
            name = name.title()
            name = name.rstrip()
            desc = desc.lstrip()
            rels[newtype].append((name, desc))
            caller.msg("Relationship tree changed.")
            return
        if 'delshort' in switches:
            args = self.args.lower()
            rels = charob.db.relationship_short
            if not rels:
                caller.msg("No relationships to delete.")
                return
            # Go through every list, remove first match
            for sh_list in rels.values():
                for tup in sh_list:
                    if tup[0].lower() == args:
                        sh_list.remove(tup)
                        caller.msg("Entry for %s deleted." % args.capitalize())
                        return
            caller.msg("No match found to delete.")
            return       
        caller.msg("Usage: @relationship/switches <arguments>")
        return


class CmdComment(MuxPlayerCommand):
    """
    @comment - Leave a public comment on another character's sheet.

    Usage:
        @comment
        @comment <name>
        @comment <name>=<comment>

    Using @comment without a right-hand-side argument will look up
    comments upon yourself or the given character.
    
    The @comment command represents an entry into a character's White
    Journal where they give their thoughts on another character. Like
    all white journal entries, they may be read by absolutely anyone.
    Therefore, all comments should be treated as IC and completely
    public knowledge.
    
    Remember, since all comments are treated as public knowledge,
    in-character retribution is very appropriate and may range from
    a mean-spirited retalitatory statement to a team of highly-paid
    assassins with surprisingly detailed instructions on how long it
    should take their target to die.

    As always, comments which are inappropriate (information that a
    character does not know, for example), may be removed or changed
    by GMs, and may incur possible penalties.
    """
    key = "@comment"
    aliases = ["+comment"]
    help_category = "Social"
    locks = "cmd:all()"

    def func(self):
        caller = self.caller
        lhs = self.lhs
        comment_txt = self.rhs
        caller_char = caller.db.char_ob
        if not caller_char:
            caller.msg("Can only leave IC @comments when you have a character.")
            return
        if not comment_txt:
            if not lhs:
                char = caller_char
            else:
                char = caller.search(lhs)
                try:
                    char = char.db.char_ob
                except AttributeError:
                    caller.msg("No character found by that name.")
                    return
            caller.msg("{wFive most recent comments on {c%s{n:" % char)
            if not char.messages.comments:
                caller.msg("No comments found.")
                return
            comment_list = []
            for comment in char.messages.comments.values():
                comment_list.extend(comment)
            comment_list.sort(key=lambda x: x.db_date_sent, reverse=True)
            caller.db.new_comments = False
            if not comment_list:
                caller.msg("No recent comments recorded.")
                return
            # get 5 most recent comments
            for entry in comment_list[:5]:
                caller.msg("\n%s\n" % char.messages.disp_entry(entry))
                entry.receivers = caller
            return
        playob = caller.search(lhs)
        if not playob:
            caller.msg("No character found by that name.")
            return
        charob = playob.db.char_ob
        if not charob:
            caller.msg("No character found to @comment upon.")
            return
        create_comment(caller_char, charob, comment_txt)
        caller.msg("Comment added.")
        playob.msg("New comment left on you by %s." % caller_char)
        if not playob.is_connected:
            playob.db.new_comments = True
        return


class CmdHere(MuxCommand):
    """
    here - shows information about characters in current room
    Usage:
        here
        here/titles - displays titles of characters

    This command displays information about characters in the
    same room as your character.
    """
    key = "here"
    help_category = "General"
    locks = "cmd:all()"
    aliases = ["+look"]

    def func(self):
        caller = self.caller
        roster = get_roster_manager()
        disp_titles = False
        if not roster:
            return
        if not caller.location:
            return
        if self.switches and 'titles' in self.switches:
            disp_titles = True
        vis_list = caller.location.get_visible_characters(caller)
        rname = caller.location.name
        list_characters(caller, vis_list, rname, roster, disp_titles, hidden_chars=vis_list, display_afk=True,
                        use_keys=False)
        if caller.check_permstring("Builders"):
            masks = [char for char in vis_list if hasattr(char, "is_disguised") and char.is_disguised]
            char_list = []
            rname = "{mMasked/Illusioned Characters{n"
            for char in masks:
                name = char.name + "{w(" + char.key + "){n"
                char_list.append(name)
            char_list.sort()
            list_characters(caller, char_list, rname, roster, disp_titles)
    pass


class CmdAddSecret(MuxPlayerCommand):
    """
    @addsecret - adds a secret to a player
    Usage:
        @addsecret player=secret - adds secret to list
        @addsecret/del player=<# of secret> - deletes secret
        @addsecret/list player

    Adds or deletes a given secret. Secret to be added is
    text string. Deleting a secret with /del switch is by
    number. See secrets on a character by @sheet/secrets <char>.
    Secret number should be between 1 to whatever, rather than 0,
    because we made it start at 1 for player formatting.
    """
    key = "@addsecret"
    help_category = "General"
    locks = "cmd:perm(addsecret) or perm(Wizards)"

    def func(self):
        caller = self.caller
        roster = get_roster_manager()
        lhs = self.lhs
        rhs = self.rhs
        switches = self.switches
        if not lhs:
            caller.msg("Add secret to who?")
            return
        if not roster:
            return
        if not rhs and 'list' not in switches:
            caller.msg("No secret specified.")
            return
        playob = caller.search(lhs)
        if not playob:
            caller.msg("No character found by that name.")
            return
        charob = playob.db.char_ob
        if not charob:
            caller.msg("No character found to @comment upon.")
            return
        if 'del' in switches:
            if not rhs.isdigit():
                caller.msg("Secret to be deleted must be a number.")
                return
            if not charob.db.secrets:
                caller.msg("No secrets found to delete.")
                return
            rhs = int(rhs)
            if not (1 <= rhs <= len(charob.db.secrets)):
                caller.msg("No secret found by that number.")
                return
            rhs -= 1
            charob.db.secrets.pop(rhs)
            charob.save()
            caller.msg("Secret %s deleted." % (rhs + 1))
            return
        if 'list' in switches:
            secrets = charob.db.secrets
            caller.msg("Secrets:")
            secret_str = ""
            for num in range(len(secrets)):
                secret_str += "{w[%s]{n: " % (num + 1)
                secret_str += "%s\n" % secrets[num]
            caller.msg(secret_str)
            return
        if not charob.db.secrets:
            charob.db.secrets = []
        charob.db.secrets.append(rhs)
        caller.msg("Secret '%s' added to %s." % (rhs, charob.name))
        return


class CmdDelComment(MuxPlayerCommand):
    """
    @delcomment - removes a comment from a character
    Usage:
        @delcomment <character>=<commenting char>/<#>

    Deletes a comment. Format is:
        @delcomment bob=lou/0
    to delete lou's first comment from bob.
    """
    key = "@delcomment"
    help_category = "Admin"
    locks = "cmd:perm(addsecret) or perm(Wizards)"

    def func(self):
        caller = self.caller
        lhs = self.lhs
        rhs = self.rhs
        rhslist = rhs.split("/")
        if not lhs or len(rhslist) < 2:
            caller.msg("Invalid delcomment syntax.")
            return
        name = rhslist[0].lower()
        num = int(rhslist[1])
        player = caller.search(lhs)
        char = player.db.char_ob
        comment = char.messages.comments[name].pop(num)
        # destroy Msg
        comment.delete()
        caller.msg("Comment destroyed.")
        if len(char.messages.comments[name]) < 1:
            char.messages.comments.pop(name)
            caller.msg("No more comments from %s. Removed from comments dict." % name)
        return


class CmdAdmRelationship(MuxPlayerCommand):
    """
    Changes a player's relationship

    Usage:
        @admin_relationship player,target=description
        @admin_relationship/private player,target=description
        @admin_relationship/short player,target=type,desc
        @admin_relationship/deleteshort player,target=type 

    Adds a white journal or black journal (with /private switch)
    relationship of player's character to target's character. To
    change or delete relationships, just delete/change the appropriate
    Msg() object in django admin window.
    """
    key = "@admin_relationship"
    aliases = ["@admin_relationships"]
    help_category = "Builder"
    locks = "cmd:perm(Builders)"

    def func(self):
        caller = self.caller
        try:
            player = caller.search(self.lhslist[0])
            if "short" in self.switches or "deleteshort" in self.switches:
                targ = self.lhslist[1].capitalize()
            else:
                targ = caller.search(self.lhslist[1])
                targ = targ.db.char_ob
        except IndexError:
            caller.msg("Requires player,target=desc")
            return
        if not self.rhs:
            caller.msg("No description supplied.")
            return
        if not player or not targ:
            return
        charob = player.db.char_ob       
        if not charob or not targ:
            caller.msg("Character objects not found.")
            return
        if "short" in self.switches:
            try:
                rtype = self.rhslist[0]
                desc = self.rhslist[1]
            except IndexError:
                caller.msg("Need both type and desc for short rels.")
                return
            relshort = charob.db.relationship_short or {}
            rel = relshort.get(rtype) or []
            rel.append((targ, desc))
            relshort[rtype] = rel
            charob.db.relationship_short = relshort
            caller.msg("%s' short rel to %s set to %s: %s." % (charob, targ, rtype, desc))
            return
        if "deleteshort" in self.switches:
            rtype = self.rhs
            relshort = charob.db.relationship_short or {}
            rel = relshort.get(rtype) or []
            if not rel:
                caller.msg("Nothing found for %s." % rtype)
                return
            rel = [ob for ob in rel if ob[0].lower() != targ.lower()]
            if not rel:
                del relshort[rtype]
                caller.msg("Removing %s from dict." % rtype)
            else:
                relshort[rtype] = rel
                caller.msg("Removed instances of %s from dict." % targ)
            charob.db.relationship_short = relshort
            return          
        desc = self.rhs
        white = "private" not in self.switches
        jname = "relationships" if white else "private relationships"
        msg = charob.messages.add_relationship(desc, targ, white)
        caller.msg("Entry added to %s:\n%s" % (jname, msg))
        return
