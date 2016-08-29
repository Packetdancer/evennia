"""
Basic starting cmdsets for characters. Each of these
cmdsets attempts to represent some aspect of how
characters function, so that different conditions
on characters can extend/modify/remove functionality
from them without explicitly calling individual commands.

"""

try:
    from evennia.commands.default import help, admin, system
except Exception as err:
    print("<<ERROR>>: Error encountered in loading Character commandset: %s" % err)
try:
    from evennia.commands.default import general as default_general
except Exception as err:
    print("<<ERROR>>: Error encountered in loading Character commandset: %s" % err)
try:
    from evennia.commands.default import building
except Exception as err:
    print("<<ERROR>>: Error encountered in loading Character commandset: %s" % err)
try:
    from evennia.commands.default import batchprocess
except Exception as err:
    print("<<ERROR>>: Error encountered in loading Character commandset: %s" % err)
try:
    from commands.commands import staff_commands
except Exception as err:
    print("<<ERROR>>: Error encountered in loading Character commandset: %s" % err)
try:
    from commands.commands import roster
except Exception as err:
    print("<<ERROR>>: Error encountered in loading Character commandset: %s" % err)
try:
    from commands.commands import general
except Exception as err:
    import traceback
    traceback.print_exc()
    print("<<ERROR>>: Error encountered in loading Character commandset: %s" % err)
try:
    from typeclasses import rooms as extended_room
except Exception as err:
    print("<<ERROR>>: Error encountered in loading Character commandset: %s" % err)
try:
    from commands.commands import social
except Exception as err:
    print("<<ERROR>>: Error encountered in loading Character commandset: %s" % err)
try:
    from commands.commands import xp
except Exception as err:
    print("<<ERROR>>: Error encountered in loading Character commandset: %s" % err)
try:
    from commands.commands import maps
except Exception as err:
    print("<<ERROR>>: Error encountered in loading Character commandset: %s" % err)
try:
    from typeclasses.places import cmdset_places
except Exception as err:
    print("<<ERROR>>: Error encountered in loading Character commandset: %s" % err)
try:
    from commands.cmdsets import combat
except Exception as err:
    print("<<ERROR>>: Error encountered in loading Character commandset: %s" % err)
try:
    from game.dominion import commands as domcommands
except Exception as err:
    print("<<ERROR>>: Error encountered in loading Character commandset: %s" % err)
try:
    from commands.commands import crafting
except Exception as err:
    print("<<ERROR>>: Error encountered in loading Character commandset: %s" % err)
from evennia.commands.cmdset import CmdSet

class OOCCmdSet(CmdSet):
    "Character-specific OOC commands. Most OOC commands defined in player."    
    key = "OOCCmdSet"
    def at_cmdset_creation(self):
        """
        This is the only method defined in a cmdset, called during
        its creation. It should populate the set with command instances.

        Note that it can also take other cmdsets as arguments, which will
        be used by the character default cmdset to add all of these onto
        the internal cmdset stack. They will then be able to removed or
        replaced as needed.
        """
        self.add(default_general.CmdInventory())
        self.add(default_general.CmdNick())
        self.add(default_general.CmdAccess())
        self.add(help.CmdHelp())
        self.add(general.CmdDiceString())
        self.add(general.CmdDiceCheck())
        self.add(general.CmdPage())
        self.add(general.CmdBriefMode())
        self.add(extended_room.CmdGameTime())
        self.add(xp.CmdVoteXP())
        self.add(social.CmdPosebreak())

class StateIndependentCmdSet(CmdSet):
    """
    Character commands that will always exist, regardless of character state.
    Poses and emits, for example, should be allowed even when a character is
    dead, because they might be posing something about the corpse, etc.
    """  
    key = "StateIndependentCmdSet"   
    def at_cmdset_creation(self):
        self.add(default_general.CmdPose())
        #emit was originally an admin command. Replaced those with gemit
        self.add(admin.CmdEmit())
        #backup look for non-extended rooms, unsure if still used anywhere
        self.add(general.CmdLook())
        self.add(general.CmdOOCSay())
        self.add(general.CmdDirections())
        self.add(general.CmdKeyring())
        # sorta IC commands, since information is interpretted by the
        # character and may not be strictly accurate. 
        self.add(extended_room.CmdExtendedLook())
        self.add(roster.CmdHere())
        self.add(social.CmdHangouts())
        self.add(social.CmdWhere())
        self.add(social.CmdJournal())
        self.add(social.CmdMessenger())
        self.add(social.CmdRoomHistory())
        self.add(maps.CmdMap())

class MobileCmdSet(CmdSet):
    """
    Commands that should only be allowed if the character is able to move.
    Thought about making a 'living' cmdset, but there honestly aren't any
    current commands that could be executed while a player is alive but
    unable to move. The sets are just equal.
    """
    key = "MobileCmdSet"
    def at_cmdset_creation(self):
        self.add(default_general.CmdGet())
        self.add(default_general.CmdDrop())
        self.add(default_general.CmdGive())
        self.add(default_general.CmdSay())
        self.add(general.CmdWhisper())
        self.add(general.CmdFollow())
        self.add(general.CmdDitch())
        self.add(general.CmdShout())
        self.add(general.CmdPut())
        self.add(xp.CmdTrain())
        self.add(xp.CmdUseXP())
        self.add(cmdset_places.CmdListPlaces())
        try:
            from commands.cmdsets import combat
            self.add(combat.CmdStartCombat())
            self.add(combat.CmdProtect())
            self.add(combat.CmdAutoattack())
            self.add(combat.CmdCombatStats())
        except Exception as err:
            print("<<ERROR>>: Error encountered in loading Character commandset: %s" % err)
        self.add(domcommands.CmdGuards())
        self.add(domcommands.CmdTask())
        self.add(domcommands.CmdSupport())
        self.add(crafting.CmdCraft())
        self.add(crafting.CmdRecipes())
        self.add(crafting.CmdJunk())
        self.add(social.CmdPraise())
        self.add(social.CmdCondemn())

class StaffCmdSet(CmdSet):
    "OOC staff and building commands. Character-based due to interacting with game world."   
    key = "StaffCmdSet"   
    def at_cmdset_creation(self):
        # The help system       
        self.add(help.CmdSetHelp())
        # System commands
        self.add(system.CmdPy())
        self.add(system.CmdScripts())
        self.add(system.CmdObjects())
        self.add(system.CmdPlayers())
        self.add(system.CmdService())
        self.add(system.CmdAbout())
        self.add(system.CmdTime())
        self.add(system.CmdServerLoad())
        # Admin commands
        self.add(admin.CmdBoot())
        self.add(admin.CmdBan())
        self.add(admin.CmdUnban())  
        self.add(admin.CmdPerm())
        self.add(admin.CmdWall())
        # Building and world manipulation
        self.add(building.CmdTeleport())
        self.add(building.CmdSetObjAlias())
        self.add(building.CmdListCmdSets())
        self.add(building.CmdWipe())
        self.add(building.CmdSetAttribute())
        self.add(building.CmdName())
        self.add(building.CmdCpAttr())
        self.add(building.CmdMvAttr())
        self.add(building.CmdCopy())
        self.add(building.CmdFind())
        self.add(building.CmdOpen())
        self.add(building.CmdLink())
        self.add(building.CmdUnLink())
        self.add(building.CmdCreate())
        self.add(building.CmdDig())
        self.add(building.CmdTunnel())
        self.add(building.CmdDestroy())
        self.add(building.CmdExamine())
        self.add(building.CmdTypeclass())
        self.add(building.CmdLock())
        self.add(building.CmdScript())
        self.add(building.CmdSetHome())
        self.add(building.CmdTag())
        # Batchprocessor commands
        self.add(batchprocess.CmdBatchCommands())
        self.add(batchprocess.CmdBatchCode())
        # more recently implemented staff commands
        self.add(staff_commands.CmdGemit())
        self.add(staff_commands.CmdWall())
        self.add(staff_commands.CmdHome())
        self.add(staff_commands.CmdResurrect())
        self.add(staff_commands.CmdKill())
        self.add(staff_commands.CmdForce())
        self.add(extended_room.CmdExtendedDesc())
        self.add(xp.CmdAdjustSkill())
        self.add(xp.CmdAwardXP())
        self.add(maps.CmdMapCreate())
        self.add(maps.CmdMapRoom())
        try:
            from commands.cmdsets import combat
            self.add(combat.CmdObserveCombat())
            self.add(combat.CmdAdminCombat())
            self.add(combat.CmdCreateAntagonist())
        except Exception as err:
            print("<<ERROR>>: Error encountered in loading Character commandset: %s" % err)
        self.add(domcommands.CmdSetRoom())
        
