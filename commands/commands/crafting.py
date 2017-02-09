"""
Crafting commands. BEHOLD THE MINIGAME.
"""
from django.conf import settings
from evennia.commands.default.muxcommand import MuxCommand
from world.dominion.models import (AssetOwner, PlayerOrNpc, CraftingRecipe, CraftingMaterials, CraftingMaterialType)
from world.dominion.setup_utils import setup_dom_for_char
from world.stats_and_skills import do_dice_check
from evennia.utils.create import create_object
from server.utils.prettytable import PrettyTable
from server.utils.arx_utils import validate_name, inform_staff
from evennia.utils import utils
from evennia.utils.utils import make_iter

AT_SEARCH_RESULT = utils.variable_from_module(*settings.SEARCH_AT_RESULT.rsplit('.', 1))

WIELD = "typeclasses.wearable.wieldable.Wieldable"
DECORATIVE_WIELD = "typeclasses.wearable.decorative_weapon.DecorativeWieldable"
WEAR = "typeclasses.wearable.wearable.Wearable"
PLACE = "typeclasses.places.places.Place"
BOOK = "typeclasses.readable.readable.Readable"
CONTAINER = "typeclasses.containers.container.Container"
WEARABLE_CONTAINER = "typeclasses.wearable.wearable.WearableContainer"
BAUBLE = "typeclasses.bauble.Bauble"
PERFUME = "typeclasses.consumable.perfume.Perfume"

QUALITY_LEVELS = {
    0: '{rawful{n',
    1: '{mmediocre{n',
    2: '{caverage{n',
    3: '{cabove average{n',
    4: '{ygood{n',
    5: '{yvery good{n',
    6: '{gexcellent{n',
    7: '{gexceptional{n',
    8: '{gsuperb{n',
    9: '{454perfect{n',
    10: '{553divine{n'
    }


def create_weapon(recipe, roll, proj, caller):
    skill = recipe.resultsdict.get("weapon_skill", "medium wpn")
    quality = get_quality_lvl(roll, recipe.difficulty)
    obj = create_obj(WIELD, proj[1], caller, caller, quality)
    obj.db.attack_skill = skill
    if skill == "archery":
        obj.ranged_mode()
    return obj, quality


def create_wearable(recipe, roll, proj, caller):
    slot = recipe.resultsdict.get("slot", None)
    slot_limit = int(recipe.resultsdict.get("slot_limit", 0))
    quality = get_quality_lvl(roll, recipe.difficulty)
    obj = create_obj(WEAR, proj[1], caller, caller, quality)
    obj.db.slot = slot
    obj.db.slot_limit = slot_limit
    return obj, quality


def create_decorative_weapon(recipe, roll, proj, caller):
    skill = recipe.resultsdict.get("weapon_skill", "small wpn")                           
    quality = get_quality_lvl(roll, recipe.difficulty)
    obj = create_obj(DECORATIVE_WIELD, proj[1], caller, caller, quality)
    obj.db.attack_skill = skill
    return obj, quality


def create_place(recipe, roll, proj, caller):
    scaling = float(recipe.resultsdict.get("scaling", 0))
    base = int(recipe.resultsdict.get("baseval", 2))
    quality = get_quality_lvl(roll, recipe.difficulty)
    obj = create_obj(PLACE, proj[1], caller, caller, quality)
    obj.db.max_spots = base + int(scaling * quality)
    return obj, quality


def create_book(recipe, roll, proj, caller):
    quality = get_quality_lvl(roll, recipe.difficulty)
    obj = create_obj(BOOK, proj[1], caller, caller, quality)
    return obj, quality


def create_container(recipe, roll, proj, caller):
    scaling = float(recipe.resultsdict.get("scaling", 0))
    base = int(recipe.resultsdict.get("baseval", 2))
    quality = get_quality_lvl(roll, recipe.difficulty)
    obj = create_obj(CONTAINER, proj[1], caller, caller, quality)
    obj.db.max_volume = base + int(scaling * quality)
    try:
        obj.grantkey(caller)
    except (TypeError, AttributeError, ValueError):
        import traceback
        traceback.print_exc()
    return obj, quality


def create_wearable_container(recipe, roll, proj, caller):
    scaling = float(recipe.resultsdict.get("scaling", 0))
    base = int(recipe.resultsdict.get("baseval", 2))
    quality = get_quality_lvl(roll, recipe.difficulty)
    obj = create_obj(WEARABLE_CONTAINER, proj[1], caller, caller, quality)
    obj.db.max_volume = base + int(scaling * quality)
    try:
        obj.grantkey(caller)
    except (TypeError, AttributeError, ValueError):
        import traceback
        traceback.print_exc()
    return obj, quality


def create_generic(recipe, roll, proj, caller):
    quality = get_quality_lvl(roll, recipe.difficulty)
    obj = create_obj(BAUBLE, proj[1], caller,
                     caller, quality)
    return obj, quality


def create_consumable(recipe, roll, proj, caller, typeclass):
    quality = get_quality_lvl(roll, recipe.difficulty)
    obj = create_obj(typeclass, proj[1], caller,
                     caller, quality)
    return obj, quality


def create_obj(typec, key, loc, home, quality):
    if "{" in key and not key.endswith("{n"):
        key += "{n"
    obj = create_object(typeclass=typec, key=key, location=loc, home=home)
    obj.db.quality_level = quality
    # will set color name and strip ansi from colorized name for key
    obj.name = key
    return obj


def get_ability_val(char, recipe):
    """
    Returns a character's highest rank in any ability used in the
    recipe.
    """
    ability_list = recipe.ability.split(",")
    abilities = char.db.abilities or {}
    skills = char.db.skills or {}
    if ability_list == "all" or not ability_list:
        # get character's highest ability
        values = sorted(abilities.values(), reverse=True)
        if not values:
            if "artwork" in skills:
                ability = skills['artwork']
            else:  # we have no abilities, and no artwork skill
                ability = 0
        else:
            ability = values[0]        
    else:
        abvalues = []
        for abname in ability_list:
            abvalues.append(abilities.get(abname, 0))
        ability = sorted(abvalues, reverse=True)[0]
    return ability
    

def do_crafting_roll(char, recipe, diffmod=0, diffmult=1.0, room=None):
    diff = int(recipe.difficulty * diffmult) - diffmod
    ability = get_ability_val(char, recipe)
    skill = recipe.skill
    stat = "luck" if char.db.luck > char.db.dexterity else "dexterity"
    return do_dice_check(char, stat=stat, difficulty=diff, skill=skill, bonus_dice=ability, quiet=False,
                         announce_room=room)


def get_difficulty_mod(recipe, money=0, action_points=0):
    from random import randint
    if not money:
        return 0
    divisor = recipe.value or 0
    if divisor < 1:
        divisor = 1
    val = float(money) / float(divisor)
    # for every 10% of the value of recipe we invest, we knock 1 off difficulty
    val = int(val/0.10) + 1
    val += randint(0, action_points)
    return val


def get_quality_lvl(roll, diff):
    # roll was against difficulty, so add it for comparison
    roll += diff
    if roll < diff/4:
        return 0
    if roll < (diff * 3)/4:
        return 1
    if roll < diff * 1.2:
        return 2
    if roll < diff * 1.6:
        return 3
    if roll < diff * 2:
        return 4
    if roll < diff * 2.5:
        return 5
    if roll < diff * 3.5:
        return 6
    if roll < diff * 5:
        return 7
    if roll < diff * 7:
        return 8
    if roll < diff * 10:
        return 9
    return 10
    

def change_quality(crafting_object, new_quality):
    """
    Given a crafted crafting_object, change various attributes in it
    based on its new quality level and recipe.
    """    
    recipe = crafting_object.db.recipe
    recipe = CraftingRecipe.objects.get(id=recipe)
    otype = recipe.type
    scaling = float(recipe.resultsdict.get("scaling", 0))
    base = float(recipe.resultsdict.get("baseval", 0))
    if otype == "place":
        crafting_object.db.max_spots = int(base) + int(scaling * new_quality)
    crafting_object.db.quality_level = new_quality
    if hasattr(crafting_object, "calc_weapon"):
        crafting_object.calc_weapon()
    if hasattr(crafting_object, "calc_armor"):
        crafting_object.calc_armor()


class CmdCraft(MuxCommand):
    """
    craft
    
    Usage:
        craft
        craft <recipe name>
        craft/name <name>
        craft/desc <description>
        craft/adorn <material type>=<amount>
        craft/forgery <real material>=<type it's faking as>
        craft/finish [<additional silver to invest>, <action points>
        craft/abandon
        craft/refine <object>[=<additional silver to spend>, <action points>]
        craft/changename <object>=<new name>

    Crafts an object. To start crafting, you must know recipes
    related to your crafting profession. Select a recipe, then
    describe the object with /name and /desc. To add more materials
    to an object, such as gemstones, use /adorn, or /forgery for
    if you are a highly unethical crafter and wish to pretend materials
    are something else. No materials or silver are used until you
    are ready to /finish the project and make the roll for its quality.
    Once you /finish an object, it can no longer have materials added
    to it, only be /refine'd for a better quality level. Additional
    money spent when finishing gives a bonus to the roll. For things
    such as perfume, the desc is the description that appears on the
    character, not the description of the bottle.

    To finish a project, use /finish, or /abandon if you wish to stop
    and do something else. To attempt to change the quality level of
    a finished object, use /refine to attempt to improve it, for a
    price based on how much it took to create. Refining can never
    make the object worse.

    Craft with no arguments will display the status of a current
    project.
    """
    key = "craft"
    locks = "cmd:all()"
    help_category = "Crafting"
    crafter = None

    def get_refine_price(self, base):
        return 0

    def get_recipe_price(self, recipe):
        return 0

    def pay_owner(self, price, msg):
        return

    def display_project(self, proj):
        """
        Project is a list of data related to what a character
        is crafting. (recipeid, name, desc, adorns, forgerydict)
        """
        caller = self.caller
        dompc = caller.db.player_ob.Dominion
        recipe = CraftingRecipe.objects.get(id=proj[0])
        msg = "{wRecipe:{n %s\n" % recipe.name
        msg += "{wName:{n %s\n" % proj[1]
        msg += "{wDesc:{n %s\n" % proj[2]
        adorns, forgery = proj[3], proj[4]
        if adorns:
            msg += "{wAdornments:{n %s\n" % ", ".join("%s: %s" % (CraftingMaterialType.objects.get(id=mat).name, amt)
                                                      for mat, amt in adorns.items())
        if forgery:
            msg += "{wForgeries:{n %s\n" % ", ".join("%s as %s" % (CraftingMaterialType.objects.get(id=value).name,
                                                                   CraftingMaterialType.objects.get(id=key).name)
                                                     for key, value in forgery.items())
        caller.msg(msg)
        caller.msg("{wTo finish it, use /finish after you gather the following:{n")
        caller.msg(recipe.display_reqs(dompc))

    def func(self):
        """Implement the command"""
        caller = self.caller
        if not self.crafter:
            self.crafter = caller
        crafter = self.crafter
        try:
            dompc = PlayerOrNpc.objects.get(player=caller.player)
            assets = AssetOwner.objects.get(player=dompc)
        except PlayerOrNpc.DoesNotExist:
            # dominion not set up on player
            dompc = setup_dom_for_char(caller)
            assets = dompc.assets
        except AssetOwner.DoesNotExist:
            # assets not initialized on player
            dompc = setup_dom_for_char(caller, create_dompc=False)
            assets = dompc.assets
        recipes = crafter.db.player_ob.Dominion.assets.recipes.all()
        if not self.args and not self.switches:
            # display recipes and any crafting project we have unfinished           
            materials = assets.materials.all()
            caller.msg("{wAvailable recipes:{n %s" % ", ".join(recipe.name for recipe in recipes))
            caller.msg("{wYour materials:{n %s" % ", ".join(str(mat) for mat in materials))
            project = caller.db.crafting_project
            if project:
                self.display_project(project)
            return
        # start a crafting project
        if not self.switches or "craft" in self.switches:
            try:
                recipe = recipes.get(name__iexact=self.lhs)
            except CraftingRecipe.DoesNotExist:
                caller.msg("No recipe found by the name %s." % self.lhs)
                return
            try:
                self.get_recipe_price(recipe)
            except ValueError:
                caller.msg("That recipe does not have a price defined.")
                return
            # proj = [id, name, desc, adorns, forgery]
            proj = [recipe.id, "", "", {}, {}]
            caller.db.crafting_project = proj
            stmsg = "You have" if caller == crafter else "%s has" % crafter
            caller.msg("{w%s started to craft:{n %s." % (stmsg, recipe.name))
            caller.msg("{wTo finish it, use /finish after you gather the following:{n")
            caller.msg(recipe.display_reqs(dompc))
            return
        if "changename" in self.switches:
            targ = caller.search(self.lhs, location=caller)
            if not targ:
                return
            if not validate_name(self.rhs):
                caller.msg("That is not a valid name.")
                return
            recipe = targ.db.recipe
            try:
                recipe = CraftingRecipe.objects.get(id=recipe)
                cost = recipe.value / 100
            except (CraftingRecipe.DoesNotExist, ValueError, TypeError):
                caller.msg("No recipe found for that item.")
                return
            if cost > caller.db.currency:
                caller.msg("You cannot afford to have its name changed.")
                return
            caller.pay_money(cost)
            targ.aliases.clear()
            targ.name = self.rhs
            caller.msg("Changed name to %s." % targ)
            return
        if "refine" in self.switches:
            targ = caller.search(self.lhs, location=caller)
            if not targ:
                return
            recipe = targ.db.recipe
            if not recipe:
                self.msg("This object has no recipe, and cannot be refined.")
                return
            recipe = CraftingRecipe.objects.get(id=recipe)
            base_cost = recipe.value / 4
            caller.msg("The base cost of refining this recipe is %s." % base_cost)
            try:
                price = self.get_refine_price(base_cost)
            except ValueError:
                caller.msg("Price for refining not set.")
                return
            if price:
                caller.msg("The additional price for refining is %s." % price)
            action_points = 0
            invest = 0
            if self.rhs:
                try:
                    invest = int(self.rhslist[0])
                    if len(self.rhslist) > 1:
                        action_points = int(self.rhslist[1])
                except ValueError:
                    caller.msg("Amount of silver/action points to invest must be a number.")
                    return
                if invest < 0 or action_points < 0:
                    caller.msg("Amount must be positive.")
                    return
            if not recipe:
                caller.msg("This is not a crafted object that can be refined.")
                return
            if targ.db.quality_level and targ.db.quality_level >= 10:
                caller.msg("This object can no longer be improved.")
                return    
            if get_ability_val(crafter, recipe) < recipe.level:
                err = "You lack" if crafter == caller else "%s lacks" % crafter
                caller.msg("%s the skill required to attempt to improve this." % err)
                return
            if invest > recipe.value:
                caller.msg("The maximum amount you can spend per roll is %s." % recipe.value)
                return
            # don't display a random number when they're prepping
            if caller.ndb.refine_targ != targ:
                diffmod = get_difficulty_mod(recipe, invest)
            else:
                diffmod = get_difficulty_mod(recipe, invest, action_points)
            cost = base_cost + invest + price
            # difficulty gets easier by 1 each time we attempt it
            refine_attempts = crafter.db.refine_attempts or {}
            attempts = refine_attempts.get(targ.id, 0)
            if attempts > 60:
                attempts = 60
            diffmod += attempts
            if diffmod:
                self.msg("Based on silver spent and previous attempts, the difficulty is adjusted by %s." % diffmod)
            if caller.ndb.refine_targ != targ:
                caller.ndb.refine_targ = targ
                caller.msg("The total cost would be {w%s{n. To confirm this, execute the command again." % cost)
                return
            if cost > caller.db.currency:
                caller.msg("This would cost %s, and you only have %s." % (cost, caller.db.currency))
                return
            if not caller.db.player_ob.pay_action_points(2 + action_points):
                self.msg("You do not have enough action points to refine.")
                return
            # pay for it
            caller.pay_money(cost)
            self.pay_owner(price, "%s has refined '%s', a %s, at your shop and you earn %s silver." % (caller, targ,
                                                                                                       recipe.name,
                                                                                                       price))

            roll = do_crafting_roll(crafter, recipe, diffmod, diffmult=0.75, room=caller.location)
            quality = get_quality_lvl(roll, recipe.difficulty)
            old = targ.db.quality_level or 0
            attempts += 1
            refine_attempts[targ.id] = attempts
            crafter.db.refine_attempts = refine_attempts
            self.msg("The roll is %s, a quality level of %s." % (roll, QUALITY_LEVELS[quality]))
            if quality <= old:
                caller.msg("You failed to improve %s." % targ)
                return
            caller.msg("New quality level is %s." % QUALITY_LEVELS[quality])
            change_quality(targ, quality)
            return
        proj = caller.db.crafting_project
        if not proj:
            caller.msg("You have no crafting project.")
            return
        if "name" in self.switches:
            if not self.args:
                caller.msg("Name it what?")
                return
            if not validate_name(self.args):
                caller.msg("That is not a valid name.")
                return
            proj[1] = self.args
            caller.db.crafting_project = proj
            caller.msg("Name set to %s." % self.args)
            return
        if "desc" in self.switches:
            if not self.args:
                caller.msg("Name it what?")
                return
            proj[2] = self.args
            caller.db.crafting_project = proj
            caller.msg("Desc set to:\n%s" % self.args)
            return
        if "abandon" in self.switches:
            caller.msg("You have abandoned this crafting project. You may now start another.")
            caller.db.crafting_project = None
            return
        if "adorn" in self.switches:
            if not (self.lhs and self.rhs):
                caller.msg("Usage: craft/adorn <material>=<amount>")
                return
            try:
                mat = CraftingMaterialType.objects.get(name__iexact=self.lhs)
                amt = int(self.rhs)
            except CraftingMaterialType.DoesNotExist:
                caller.msg("No material named %s." % self.lhs)
                return
            except CraftingMaterialType.MultipleObjectsReturned:
                caller.msg("More than one match. Please be more specific.")
                return
            except (TypeError, ValueError):
                caller.msg("Amount must be a number.")
                return
            if amt < 1:
                caller.msg("Amount must be positive.")
                return
            recipe = CraftingRecipe.objects.get(id=proj[0])
            if not recipe.allow_adorn:
                caller.msg("This recipe does not allow for additional materials to be used.")
                return
            adorns = proj[3] or {}
            adorns[mat.id] = amt
            proj[3] = adorns
            caller.db.crafting_project = proj
            caller.msg("Additional materials: %s" % ", ".join("%s: %s" % (CraftingMaterialType.objects.get(id=mat).name,
                                                                          amt) for mat, amt in adorns.items()))
            return
        if "forgery" in self.switches:
            self.msg("Temporarily disabled until I have time to revamp this.")
            return
            # if not (self.lhs and self.rhs):
            #     caller.msg("Usage: craft/forgery <real>=<fake>")
            #     return
            # # check that the materials are legit
            # try:
            #     real = CraftingMaterialType.objects.get(name__iexact=self.lhs)
            #     fake = CraftingMaterialType.objects.get(name__iexact=self.rhs)
            # except CraftingMaterialType.DoesNotExist:
            #     caller.msg("Could not find materials for both those types.")
            #     return
            # except CraftingMaterialType.MultipleObjectsReturned:
            #     caller.msg("Matches were not unique for types. Must be more specific.")
            #     return
            # # we have matches, make sure real ones are in recipe, or the object
            # recipe = CraftingRecipe.objects.get(id=proj[0])
            # types = [_mat.type for _mat in recipe.materials.all()]
            # if fake not in types:
            #     # not in base recipe, check if it's in adornments
            #     if fake.id not in proj[3].keys():
            #         caller.msg("Material that you want to fake does not "
            # "appear in the project's recipe nor adornments.")
            #         return
            # if real.category != fake.category:
            #     caller.msg("The categories of the materials must match. %s is %s, %s is %s." % (real, real.category,
            #                                                                                     fake, fake.category))
            #     return
            # proj[4][fake.id] = real.id
            # caller.db.crafting_project = proj
            # caller.msg("Now using %s in place of %s in the recipe, and hoping no one notices." % (real.name,
            # fake.name))
            # return
        # do rolls for our crafting. determine quality level, handle forgery stuff
        if "finish" in self.switches:
            if not proj[1]:
                caller.msg("You must give it a name first.")
                return
            if not proj[2]:
                caller.msg("You must write a description first.")
                return
            invest = 0
            action_points = 0
            if self.lhs:
                try:
                    invest = int(self.lhslist[0])
                    if len(self.lhslist) > 1:
                        action_points = int(self.lhslist[1])
                except ValueError:
                    caller.msg("Silver/Action Points to invest must be a number.")
                    return
                if invest < 0 or action_points < 0:
                    caller.msg("Silver/Action Points cannot be a negative number.")
                    return
            # first, check if we have all the materials required
            mats = {}
            try:
                recipe = recipes.get(id=proj[0])
            except CraftingRecipe.DoesNotExist:
                caller.msg("You lack the ability to finish that recipe.")
                return
            for mat in recipe.materials.all():
                mats[mat.id] = mats.get(mat.id, 0) + mat.amount
            for adorn in proj[3]:
                mats[adorn] = mats.get(adorn, 0) + proj[3][adorn]
            # replace with forgeries
            for rep in proj[4].keys():
                # rep is ID to replace
                forg = proj[4][rep]
                if rep in mats:
                    amt = mats[rep]
                    del mats[rep]
                    mats[forg] = amt
            # check silver cost
            try:
                price = self.get_recipe_price(recipe)
            except ValueError:
                caller.msg("That recipe does not have a price defined.")
                return
            cost = recipe.additional_cost + invest + price
            if cost < 0 or price < 0:
                errmsg = "For %s at %s, recipe %s, cost %s, price %s" % (caller, caller.location, recipe.id, cost,
                                                                         price)
                raise ValueError(errmsg)
            if caller.db.currency < cost:
                caller.msg("The recipe costs %s on its own, and you are trying to spend an additional %s." %
                           (recipe.additional_cost, invest))
                if price:
                    caller.msg("The additional price charged by the crafter for this recipe is %s." % price)
                caller.msg("You need %s silver total, and have only %s." % (cost, caller.db.currency))
                return
            pmats = caller.player.Dominion.assets.materials
            # add up the total cost of the materials we're using for later
            realvalue = 0
            for mat in mats:
                try:
                    c_mat = CraftingMaterialType.objects.get(id=mat)
                except CraftingMaterialType.DoesNotExist:
                    inform_staff("Attempted to craft using material %s which does not exist." % mat)
                    self.msg("One of the materials required no longer seems to exist. Informing staff.")
                    return
                try:
                    pmat = pmats.get(type=c_mat)
                    if pmat.amount < mats[mat]:
                        caller.msg("You need %s of %s, and only have %s." % (mats[mat], c_mat.name, pmat.amount))
                        return
                    realvalue += c_mat.value * mats[mat]
                except CraftingMaterials.DoesNotExist:
                    caller.msg("You do not have any of the material %s." % c_mat.name)
                    return
            # check if they have enough action points
            if not caller.db.player_ob.pay_action_points(2 + action_points):
                self.msg("You do not have enough action points left to craft that.")
                return
            # we're still here, so we have enough materials. spend em all
            for mat in mats:
                cmat = CraftingMaterialType.objects.get(id=mat)
                pmat = pmats.get(type=cmat)
                pmat.amount -= mats[mat]
                pmat.save()
            # determine difficulty modifier if we tossed in more money
            diffmod = get_difficulty_mod(recipe, invest, action_points)
            # do crafting roll
            roll = do_crafting_roll(crafter, recipe, diffmod, room=caller.location)
            # get type from recipe
            otype = recipe.type
            # create object
            if otype == "wieldable":
                obj, quality = create_weapon(recipe, roll, proj, caller)
            elif otype == "wearable":
                obj, quality = create_wearable(recipe, roll, proj, caller)
            elif otype == "place":
                obj, quality = create_place(recipe, roll, proj, caller)
            elif otype == "book":
                obj, quality = create_book(recipe, roll, proj, caller)
            elif otype == "container":
                obj, quality = create_container(recipe, roll, proj, caller)
            elif otype == "decorative_weapon":
                obj, quality = create_decorative_weapon(recipe, roll, proj, caller)
            elif otype == "wearable_container":
                obj, quality = create_wearable_container(recipe, roll, proj, caller)
            elif otype == "perfume":
                obj, quality = create_consumable(recipe, roll, proj, caller, PERFUME)
            else:
                obj, quality = create_generic(recipe, roll, proj, caller)
            # finish stuff universal to all crafted objects
            obj.desc = proj[2]
            obj.save()
            obj.db.materials = mats
            obj.db.recipe = recipe.id
            obj.db.adorns = proj[3]
            obj.db.crafted_by = crafter
            obj.db.volume = int(recipe.resultsdict.get('volume', 0))
            caller.pay_money(cost)
            self.pay_owner(price, "%s has crafted '%s', a %s, at your shop and you earn %s silver." % (caller, obj,
                                                                                                       recipe.name,
                                                                                                       price))
            if proj[4]:
                obj.db.forgeries = proj[4]
                obj.db.forgery_roll = do_crafting_roll(caller, recipe, room=caller.location)
                # forgery penalty will be used to degrade weapons/armor
                obj.db.forgery_penalty = (recipe.value/realvalue) + 1
            cnoun = "You" if caller == crafter else crafter
            caller.msg("%s created %s." % (cnoun, obj.name))
            quality = QUALITY_LEVELS[quality]
            caller.msg("It is of %s quality." % quality)
            caller.db.crafting_project = None
            return


class CmdRecipes(MuxCommand):
    """
    recipes
    Usage:
        recipes
        recipes/learn <recipe name>
        recipes/info <recipe name>
        recipes/teach <character>=<recipe name>
        recipes/cost

    Check, learn, or teach recipes. Without an argument, recipes
    lists all recipes you know or can learn. Without any switches,
    recipes lists the requirements of a recipe for crafting. Learning
    a recipe may or may not be free - cost lets you see the cost of
    a recipe beforehand.
    """
    key = "recipes"
    locks = "cmd:all()"
    aliases = ["recipe"]
    help_category = "Crafting"

    def display_recipes(self, recipes):
        known_list = CraftingRecipe.objects.filter(known_by__player__player=self.caller.player)
        table = PrettyTable(["{wKnown{n", "{wName{n", "{wAbility{n",
                             "{wDifficulty{n", "{wCost{n"])
        for recipe in recipes:
            known = "{wX{n" if recipe in known_list else ""
            table.add_row([known, recipe.name, recipe.ability,
                           recipe.difficulty, recipe.additional_cost])
        return table

    def func(self):
        """Implement the command"""
        caller = self.caller
        recipes = list(CraftingRecipe.objects.filter(known_by__player__player=caller.player))
        unknown = CraftingRecipe.objects.exclude(known_by__player__player=caller.player).order_by("additional_cost")
        can_learn = [ob for ob in unknown if ob.access(caller, 'learn')]
        try:
            dompc = PlayerOrNpc.objects.get(player=caller.player)
        except PlayerOrNpc.DoesNotExist:
            dompc = setup_dom_for_char(caller)
        if not self.args and not self.switches:
            caller.msg("Recipes you know or can learn:")
            visible = recipes + can_learn
            from operator import attrgetter
            visible = sorted(visible, key=attrgetter('ability', 'difficulty',
                                                     'name'))
            caller.msg(self.display_recipes(visible))
            return
        if not self.switches:
            try:
                recipe = CraftingRecipe.objects.get(known_by=dompc.assets, name=self.lhs)
            except CraftingRecipe.DoesNotExist:
                caller.msg("You don't know a recipe by %s." % self.lhs)
                return
            caller.msg("Requirements for %s:" % recipe.name)
            caller.msg(recipe.display_reqs(dompc, full=True), options={'box': True})
            return
        if 'learn' in self.switches:
            match = None
            if self.args:
                match = [ob for ob in can_learn if ob.name.lower() == self.args.lower()]
            if not match:
                caller.msg("No recipe by that name.")
                caller.msg("\nRecipes you can learn:")
                caller.msg(self.display_recipes(can_learn))
                return
            match = match[0]

            cost = match.additional_cost
            if cost > caller.db.currency:
                caller.msg("It costs %s to learn %s, and you only have %s." % (cost, match.name, caller.db.currency))
                return
            caller.pay_money(cost)
            dompc.assets.recipes.add(match)
            if cost:
                coststr = " for %s silver" % cost
            else:
                coststr = ""
            caller.msg("You have learned %s%s." % (match.name, coststr))
            return
        if 'info' in self.switches:
            match = None
            info = list(can_learn) + list(recipes)
            if self.args:
                match = [ob for ob in info if ob.name.lower() == self.args.lower()]
            if not match:
                caller.msg("No recipe by that name.")
                caller.msg("Recipes you can get /info on:")
                caller.msg(self.display_recipes(info))
                return
            match = match[0]
            display = match.display_reqs(dompc, full=True)
            caller.msg(display, options={'box': True})
            return
        if 'teach' in self.switches:
            match = None
            can_teach = [ob for ob in recipes if ob.access(caller, 'teach')]
            if self.rhs:
                match = [ob for ob in can_teach if ob.name.lower() == self.rhs.lower()]
            if not match:
                caller.msg("Recipes you can teach:")
                caller.msg(self.display_recipes(can_teach))
                if self.rhs:
                    caller.msg("You entered: %s." % self.rhs)
                return
            recipe = match[0]
            character = caller.search(self.lhs)
            if not character:
                return
            if not recipe.access(character, 'learn'):
                caller.msg("They cannot learn %s." % recipe.name)
                return
            try:
                dompc = PlayerOrNpc.objects.get(player=character.player)
            except PlayerOrNpc.DoesNotExist:
                dompc = setup_dom_for_char(character)
            if recipe in dompc.assets.recipes.all():
                caller.msg("They already know %s." % recipe.name)
                return
            dompc.assets.recipes.add(recipe)
            caller.msg("Taught %s %s." % (character, recipe.name))


class CmdJunk(MuxCommand):
    """
    +junk

    Usage:
        +junk <object>

    Destroys an object, retrieving a portion of the materials
    used to craft it.
    """
    key = "+junk"
    aliases = ["@junk"]
    locks = "cmd:all()"
    help_category = "Crafting"

    def func(self):
        """Implement the command"""
        caller = self.caller
        pmats = caller.player.Dominion.assets.materials
        obj = caller.search(self.args, use_nicks=True, quiet=True)
        if not obj:
            AT_SEARCH_RESULT(obj, caller, self.args, False)
            return
        else:
            if len(make_iter(obj)) > 1:
                AT_SEARCH_RESULT(obj, caller, self.args, False)
                return
            obj = make_iter(obj)[0]
        if obj.location != caller:
            caller.msg("You can only +junk objects you are holding.")
            return
        if obj.db.player_ob or obj.player:
            caller.msg("You cannot +junk a character.")
            return
        if obj.contents:
            self.msg("It contains objects that must first be removed.")
            return
        if obj.db.destroyable:
            caller.msg("You have destroyed %s." % obj)
            obj.softdelete()
            return
        recipe = obj.db.recipe
        if not recipe:
            caller.msg("You may only +junk crafted objects.")
            return
        if "plot" in obj.tags.all():
            self.msg("This object cannot be destroyed.")
            return
        mats = obj.db.materials
        adorns = obj.db.adorns or {}
        refunded = []
        for mat in adorns:
            cmat = CraftingMaterialType.objects.get(id=mat)
            try:
                pmat = pmats.get(type=cmat)
            except CraftingMaterials.DoesNotExist:
                pmat = pmats.create(type=cmat)
            amount = adorns[mat]
            pmat.amount += amount
            pmat.save()
            refunded.append("%s %s" % (amount, cmat.name))
        for mat in mats:
            if mat in adorns:
                amount = (mats[mat] - adorns[mat])/2
            else:
                amount = mats[mat]/2
            if amount <= 0:
                continue
            cmat = CraftingMaterialType.objects.get(id=mat)
            try:
                pmat = pmats.get(type=cmat)
            except CraftingMaterials.DoesNotExist:
                pmat = pmats.create(type=cmat)
            pmat.amount += amount
            pmat.save()            
            refunded.append("%s %s" % (amount, cmat.name))
        caller.msg("By destroying %s, you have received: %s" % (obj, ", ".join(refunded)))
        obj.softdelete()
