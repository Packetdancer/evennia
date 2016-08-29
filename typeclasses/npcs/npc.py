"""
Npc guards, which are connected to an AgentOb instance,
which is itself connected to an Agent instance. The Agent
instance determines the type of agents (guards, spies, etc),
and how many are currently unassigned. AgentOb is for assigned
agents, and stores how many, and this object which acts as its
in-game representation on the grid.

For this object, our values are populated by setup_agent, while
we already have the 'agentob' property given by the related
OneToOne field from our associated AgentOb.

We come into being in one of two ways:
1) We're assigned to an individual player as that player-character's
agents, who can them summon them.
2) A player is in a square that is marked as having the attribute
'unassigned_guards' which points to an Agent instance, and then
should have the cmdset in that room that allows them to draw upon
those guards if they meet certain criteria. If they execute that
command, it then summons guards for that player character.

"""
from typeclasses.characters import Character
from .npc_types import (get_npc_stats, get_npc_desc, get_npc_skills,
                        get_npc_singular_name, get_npc_plural_name, get_npc_weapon,
                        get_armor_bonus, get_hp_bonus)
from world.stats_and_skills import do_dice_check
import time


class Npc(Character):
    """
    NPC objects

    """    
    #------------------------------------------------
    # PC command methods
    #------------------------------------------------        
    def attack(self, targ, lethal=False):
        """
        Attack a given target. If lethal is False, we will not kill any
        characters in combat.
        """
        self.execute_cmd("+fight %s" % targ)
        if lethal:
            self.execute_cmd("kill %s" % targ)
        else:
            self.execute_cmd("attack %s" % targ)
    
    def stop(self):
        """
        Stop attacking/exit combat.
        """
        combat = self.location.ndb.combat_manager
        if not combat:
            return
        gfite = combat.get_fighter_data(self.id)
        if gfite:
            gfite.wants_to_end = True
            gfite.reset()

    #------------------------------------------------
    # Inherited Character methods
    #------------------------------------------------
    def at_object_creation(self):
        """
        Called once, when this object is first created.
        """
        #BriefMode is for toggling brief descriptions from rooms
        self.db.briefmode = False
        # identification attributes about our player
        self.db.player_ob = None
        self.db.dice_string = "Default Dicestring"
        self.db.health_status = "alive"
        self.db.sleep_status = "awake"
        self.db.attackable = True
        self.db.npc = True
        self.db.automate_combat = True
        self.db.damage = 0

    def at_init(self):
        """
        This is always called whenever this object is initiated --
        that is, whenever it its typeclass is cached from memory. This
        happens on-demand first time the object is used or activated
        in some way after being created but also after each server
        restart or reload.
        """
        self.is_room = False
        self.is_exit = False
        self.is_character = True

    def return_appearance(self, pobject, detailed=False, format_desc=False):
        """
        This is a convenient hook for a 'look'
        command to call.
        """
        if not pobject:
            return
        # get and identify all objects
        if pobject is self or pobject.check_permstring("builders"):
            detailed = True
        string = "{c%s{n" % self.get_fancy_name()
        # Health appearance will also determine whether we
        # use an alternate appearance if we are dead.
        health_appearance = self.get_health_appearance()
        # desc used to be db.desc. May use db.desc for temporary values,
        # such as illusions, masks, etc
        desc = self.desc
        if self.db.use_alt_desc and self.db.desc:
            desc = self.db.desc
        if desc:
            indent = 0
            if len(desc) > 78:
                indent = 4
            string += "\n\n%s" % desc
        if health_appearance:
            string += "\n\n%s" % health_appearance
        string += self.return_contents(pobject, detailed)
        return string
    
    def resurrect(self, *args, **kwargs):
        """
        Cue 'Bring Me Back to Life' by Evanessence.
        """
        self.db.health_status = "alive"
        if self.location:
            self.location.msg_contents("{w%s has returned to life.{n" % self.name)
        

    def fall_asleep(self, uncon=False):
        """
        Falls asleep. Uncon flag determines if this is regular sleep,
        or unconsciousness.
        """
        if uncon:
            self.db.sleep_status = "unconscious"
        else:
            self.db.sleep_status = "asleep"
        if self.location:
            self.location.msg_contents("%s falls %s." % (self.name, self.db.sleep_status))
        

    def wake_up(self):
        """
        Wakes up.
        """
        self.db.sleep_status = "awake"
        if self.location:
            self.location.msg_contents("%s wakes up." % self.name)
            combat = self.location.ndb.combat_manager
            if combat and self in combat.ndb.combatants:
                combat.wake_up(self)
        return

    def get_health_appearance(self):
        """
        Return a string based on our current health.
        """
        name = self.name
        if self.db.health_status == "dead":
            return "%s is currently dead." % name
        wound = float(self.dmg)/float(self.max_hp)
        if wound <= 0:
            msg = "%s is in perfect health." % name
        elif 0 < wound <= 0.1:
            msg = "%s is very slightly hurt." % name
        elif 0.1 < wound <= 0.25:
            msg = "%s is moderately wounded." % name
        elif 0.25 < wound <= 0.5:
            msg = "%s is seriously wounded." % name
        elif 0.5 < wound <= 0.75:
            msg = "%s is very seriously wounded." % name
        elif  0.75 < wound <= 2.0:
            msg = "%s is critically wounded." % name
        else:
            msg = "%s is very critically wounded, possibly dying." % name
        awake = self.db.sleep_status
        if awake and awake != "awake":
            msg += " They are %s." % awake
        return msg
    
    def recovery_test(self, diff_mod=0, free=False):
        """
        A mechanism for healing characters. Whenever they get a recovery
        test, they heal the result of a willpower+stamina roll, against
        a base difficulty of 0. diff_mod can change that difficulty value,
        and with a higher difficulty can mean it can heal a negative value,
        resulting in the character getting worse off. We go ahead and change
        the player's health now, but leave the result of the roll in the
        caller's hands to trigger other checks - death checks if we got
        worse, unconsciousness checks, whatever.
        """
        diff = 0 + diff_mod
        roll = do_dice_check(self, stat_list=["willpower", "stamina"], difficulty=diff)
        if roll > 0:
            self.msg("You feel better.")
        else:
            self.msg("You feel worse.")
        apply = self.dmg - roll # how much dmg character has after the roll
        if apply < 0: apply = 0 # no remaining damage
        self.db.damage = apply
        if not free:
            self.db.last_recovery_test = time.time()
        return roll
    
    def sensing_check(self, difficulty=15, invis=False):
        """
        See if the character detects something that is hiding or invisible.
        The difficulty is supplied by the calling function.
        Target can be included for additional situational
        """
        roll = do_dice_check(self, stat="perception", stat_keep=True, difficulty=difficulty)
        return roll


    def _get_npc_type(self):
        return self.db.npc_type or 0
    npc_type = property(_get_npc_type)

    def _get_quality(self):
        return self.db.npc_quality or 0
    quality = property(_get_quality)

    def get_fakeweapon(self, force_update=False):
        if not self.db.fakeweapon or force_update:
            npctype = self._get_npc_type()
            quality = self._get_quality()
            self.db.fakeweapon = get_npc_weapon(npctype, quality)
        return self.db.fakeweapon

    @property
    def quantity(self):
        return 1

class MultiNpc(Npc):
    def multideath(self, num, death=False):
        living = self.db.num_living or 0       
        if num > living: num = living
        self.db.num_living = living - num
        if death:
            dead = self.db.num_dead or 0            
            self.db.num_dead = dead + num
        else:
            incap = self.db.num_incap or 0
            self.db.num_incap = incap + num

    def get_singular_name(self):
        return self.db.singular_name or get_npc_singular_name(self._get_npc_type())

    def get_plural_name(self):
        return self.db.plural_name or get_npc_plural_name(self._get_npc_type())

    def death_process(self, *args, **kwargs):
        """
        This object dying. Set its state to dead, send out
        death message to location. Add death commandset.
        """
        if self.location:
            self.location.msg_contents("{r%s has died.{n" % get_npc_singular_name(self._get_npc_type()))
        self.multideath(num=1, death=True)
        self.db.damage = 0

    def fall_asleep(self, uncon=False):
        """
        Falls asleep. Uncon flag determines if this is regular sleep,
        or unconsciousness.
        """
        if self.location:
            self.location.msg_contents("{w%s falls %s.{n" % (get_npc_singular_name(self._get_npc_type()),
                                                             "unconscious" if uncon else "asleep"))
        self.multideath(num=1, death=False)
        # don't reset damage here since it's used for death check. Reset in combat process

    def setup_name(self):
        type = self.db.npc_type
        if self.db.num_living == 1 and not self.db.num_dead:
            self.key = self.db.singular_name or get_npc_singular_name(type)
        else:
            if self.db.num_living == 1:
                noun = self.db.singular_name or get_npc_singular_name(type)
            else:
                noun = self.db.plural_name or get_npc_plural_name(type)
            if not self.db.num_living and self.db.num_dead:
                noun = "dead %s" % noun
                self.key = "%s %s" % (self.db.num_dead, noun)
            else:
                self.key = "%s %s" % (self.db.num_living, noun)
        self.setup_aliases()
        self.save()

    def setup_aliases(self):
        self.aliases.clear()
        self.aliases.setup_aliases_from_key()
        self.aliases.add(self.get_singular_name())

    def setup_npc(self, ntype=0, threat=0, num=1, sing_name=None, plural_name=None, desc=None, keepold=False):
        self.db.num_living = num
        self.db.num_dead = 0
        self.db.num_incap = 0
        self.db.damage = 0
        self.db.health_status = "alive"
        self.db.sleep_status = "awake"
        # if we don't 
        if not keepold:
            self.db.npc_type = ntype
            self.db.singular_name = sing_name
            self.db.plural_name = plural_name
            self.desc = desc or get_npc_desc(ntype)
        self.db.npc_quality = threat
        for stat,value in get_npc_stats(ntype).items():
            self.attributes.add(stat, value)
        skills = get_npc_skills(ntype)
        for skill in skills:
            skills[skill] += threat
        self.db.skills = skills
        self.db.fakeweapon = get_npc_weapon(ntype, threat)
        self.db.armor_class = get_armor_bonus(self._get_npc_type(), self._get_quality())
        self.db.bonus_max_hp = get_hp_bonus(self._get_npc_type(), self._get_quality())       
        self.save()
        self.setup_name()

    def dismiss(self):
        self.location = None
        self.save()

    @property
    def quantity(self):
        return self.db.num_living

class Agent(MultiNpc):
    #-----------------------------------------------
    # AgentHandler Admin client methods
    #-----------------------------------------------
           
    def setup_agent(self):
        """
        We'll set up our stats based on the type given by our agent class.
        """
        agent = self.agentob
        agent_class = agent.agent_class
        quality = agent_class.quality or 0
        # set up our stats based on our type
        desc = agent_class.desc
        self.setup_npc(ntype=agent_class.type, threat=quality, num=agent.quantity, desc=desc)

    def setup_name(self):
        type = self.agentob.agent_class.type
        noun = self.agentob.agent_class.name
        if not noun:
            if self.db.num_living == 1:
                noun = get_npc_singular_name(type)
            else:
                noun = get_npc_plural_name(type)
        if self.db.num_living:
            self.key = "%s %s" % (self.db.num_living, noun)
        else:
            self.key = noun
        self.setup_aliases()
        self.save()  

    def setup_locks(self):
        # base lock - the 'command' lock string
        lockfunc = ["command: %s", "desc: %s"]
        player_owner = None
        org_owner = None
        assigned_char = self.db.guarding
        owner = self.agentob.agent_class.owner
        if owner.player:
            player_owner = owner.player.player
        if not player_owner:
            org_owner = owner.organization_owner
            if assigned_char:
                perm = "rank(2, %s) or id(%s)" % (org_owner.name, assigned_char.id)
            else:
                perm = "rank(2, %s)" % (org_owner.name)
        else:
            if assigned_char:
                perm = "pid(%s) or id(%s)" % (player_owner.id, assigned_char.id)
            else:
                perm = "pid(%s)" % (player_owner.id)
        for lock in lockfunc:
            # add the permission to the lock function from above
            lock = lock % perm
            # note that this will replace any currently defined 'command' lock
            self.locks.add(lock)
    
    def assign(self, targ):
        """
        When given a Character as targ, we add ourselves to their list of
        guards, saved as an Attribute in the character object.
        """
        guards = targ.db.assigned_guards or []
        if self not in guards:
            guards.append(self)
        targ.db.assigned_guards = guards
        self.db.guarding = targ
        self.setup_locks()
        self.setup_name()

    def lose_agents(self, num, death=False):
        """
        Called whenever we lose one of our agents, due to them being recalled
        or dying.
        """
        if num < 0:
            raise ValueError("Must pass a positive integer to lose_agents.")
        self.multideath(num, death)
        self.agentob.lose_agents(num)
        self.setup_name()       
        if self.db.num_living <= 0:
            self.unassign()
        return num
    
    def gain_agents(self, num):
        self.db.num_living += num
        self.setup_name()
        
    def unassign(self):
        """
        When unassigned from the Character we were guarding, we remove
        ourselves from their guards list and then call unassign in our
        associated AgentOb.
        """
        targ = self.db.guarding
        if targ:
            guards = targ.db.assigned_guards or []
            if self in guards:
                guards.remove(self)
        self.stop_follow(unassigning=True)
        self.agentob.unassign()
        self.locks.add("command: false()")

    def display(self):
        msg = "\n{wGuards:{n %s\n" % self.name
        if self.db.guarding:
            msg += "{wAssigned to:{n %s\n" % self.db.guarding
        msg += "{wLocation:{n %s\n" % (self.location or self.db.docked or "Home Barracks")
        return msg
    
    def _get_npc_type(self):
        agent = self.agentob
        agent_class = agent.agent_class
        return agent_class.type
    def _get_quality(self):
        agent = self.agentob
        agent_class = agent.agent_class
        return agent_class.quality or 0
    npc_type = property(_get_npc_type)
    quality = property(_get_quality)
    
    def stop_follow(self, unassigning=False):
        super(Agent, self).stop_follow()
        # if we're not being unassigned, we dock them. otherwise, they're gone
        self.dismiss(dock=not unassigning)
    
    def summon(self, summoner=None):
        """
        Have these guards appear to defend the character. This should generally only be
        called in a location that permits it, such as their house barracks, or in a
        square close to where the guards were docked.
        """
        if not summoner:
            summoner = self.db.guarding
        loc = summoner.location
        self.move_to(loc)
        self.follow(self.db.guarding)
        docked_loc = self.db.docked
        if docked_loc and docked_loc.db.docked_guards and self in docked_loc.db.docked_guards:
            docked_loc.db.docked_guards.remove(self)
        self.db.docked = None

    def dismiss(self, dock=True):
        """
        Dismisses our guards. If they're not being dismissed permanently, then
        we dock them at the location they last occupied, saving it as an attribute.
        """
        loc = self.location
        # being dismissed permanently while gone
        if not loc:
            docked = self.db.docked
            if docked and docked.db.docked_guards and self in docked.db.docked_guards:
                docked.db.docked_guards.remove(self)
            return       
        self.db.prelogout_location = loc
        if dock:
            self.db.docked = loc
            docked = loc.db.docked_guards or []
            if self not in docked:
                docked.append(self)
            loc.db.docked_guards = docked
        loc.msg_contents("%s have been dismissed." % self.name)
        self.location = None
        if self.ndb.combat_manager:
            self.ndb.combat_manager.remove_combatant(self)

    def death_process(self, *args, **kwargs):
        """
        This object dying. Set its state to dead, send out
        death message to location. Add death commandset.
        """
        if self.location:
            self.location.msg_contents("{r%s has died.{n" % get_npc_singular_name(self._get_npc_type()))
        self.lose_agents(num=1, death=True)
        self.db.damage = 0

    def at_init(self):
        try:
            if self.location and self.db.guarding:
                self.follow(self.db.guarding)
        except Exception:
            import traceback
            traceback.print_exc()


        
