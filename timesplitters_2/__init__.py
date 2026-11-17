"""
Archipelago world for TimeSplitters 2.
Locations: Bronze, Silver, Gold and Platinum trophies on the 45 Arcade League missions and 21
Challenges, story level completions per difficulty and story objectives. Items: the missions, the 10 story
levels, the 126 characters, 9 cheats, 5 Silly Hats, 16 arcade maps, 16 game modes and 26 weapons.
"""
from typing import Any

from dataclasses import dataclass

from BaseClasses import Item, ItemClassification, Location, LocationProgressType, Region, Tutorial
from Options import Choice, DeathLink, DefaultOnToggle, OptionGroup, OptionSet, PerGameCommonOptions, Range, Toggle
from worlds.AutoWorld import WebWorld, World
from worlds.generic.Rules import set_rule
from worlds.LauncherComponents import Component, components, icon_paths, launch_subprocess

from . import game_data


class Ts2Item(Item):
    game = game_data.GAME_NAME


class Ts2Location(Location):
    game = game_data.GAME_NAME


class StartingItem(Choice):
    """
    What you start with (as well as one random character and one random weapon).
    Random Arcade Or Challenge Mission: Arcade League missions and Challenges.
    Random Arcade Mission: Arcade League missions.
    Random Challenge Mission: Challenges.
    Random Story Mission: one story level, never 2401 Space Station.
    Random Any Mission: from all three pools (never 2401 Space Station). If the first one is a story
    level, it is the only one.
    Siberia: 1990 Siberia.
    With Progressive Story Level, a story start is always 1990 Siberia (one Progressive Story Level).
    With Trophy Hunt and Exclude Story Mode, story starts become Random Arcade Or Challenge Mission.
    """
    display_name = "Starting Mission"
    option_random_arcade_or_challenge_mission = 0
    option_random_arcade_mission = 1
    option_random_challenge_mission = 2
    option_random_story_mission = 3
    option_random_any_mission = 4
    option_siberia = 5
    default = 0


class StartingMissionCount(Range):
    """
    How many Arcade League missions or Challenges you start with. Only applies to the Random Arcade Or
    Challenge, Random Arcade, Random Challenge and Random Any options (with Random Any, a story level
    rolled first is the only starting mission).
    """
    display_name = "How Many Starting Arcade/Challenge Missions"
    range_start = 1
    range_end = 5
    default = 1


class StoryMode(Choice):
    """
    Individual Items: every story level is its own item. Finding "1932 Chicago" unlocks that level.
    Progressive Story Level: story levels unlock in order, one more for each Progressive Story Level you have.
    """
    display_name = "Story Mode Status"
    option_individual_items = game_data.STORY_INDIVIDUAL
    option_progressive_story_level = game_data.STORY_PROGRESSIVE
    default = game_data.STORY_INDIVIDUAL


class Goal(Choice):
    """
    2401 Space Station: complete 2401 Space Station (on any difficulty). Its extra requirements are
    under "Goal Options - 2401 Space Station".
    Trophy Hunt: earn trophies on Arcade League missions and/or Challenges, as set under
    "Goal Options - Trophy Hunt".
    """
    display_name = "Goal"
    option_space_station = game_data.GOAL_SPACE_STATION
    option_trophy_hunt = game_data.GOAL_ALL_TROPHIES
    alias_all_trophies = game_data.GOAL_ALL_TROPHIES
    default = game_data.GOAL_SPACE_STATION


class StoryLevelsRequired(Range):
    """
    Only used when the goal is 2401 Space Station. How many of the other 9 story levels you must
    have completed (on any difficulty) before 2401 Space Station opens (you also need its item, or
    all 10 Progressive Story Levels).
    """
    display_name = "Story Levels Required To Access Goal"
    range_start = 0
    range_end = game_data.FINAL_STORY_LEVEL
    default = game_data.FINAL_STORY_LEVEL


class TrophiesRequired(Range):
    """
    Only used when the goal is 2401 Space Station. How many Arcade League missions and Challenges
    you must have beaten (with at least the grade below) before 2401 Space Station opens.
    0 = none needed.
    """
    display_name = "How Many Trophies Required To Access Goal"
    range_start = 0
    range_end = len(game_data.MISSIONS)
    default = 0


class TrophiesRequiredGrade(Choice):
    """
    Only used when the goal is 2401 Space Station. The lowest trophy that counts towards
    "How Many Trophies Required To Access Goal".
    """
    display_name = "Minimum Grade Of Trophy To Count"
    option_bronze = 1
    option_silver = 2
    option_gold = 3
    option_platinum = 4
    default = 1


class TrophyHuntSetting(Choice):
    """
    Only used when the goal is Trophy Hunt. Which missions you need a trophy on.
    All Arcade Missions: the 45 Arcade League missions.
    All Challenges: the 21 Challenges.
    All Trophies: all 66.
    """
    display_name = "Trophy Hunt Goal Setting"
    option_all_arcade_missions = game_data.HUNT_ARCADE
    option_all_challenges = game_data.HUNT_CHALLENGES
    option_all_trophies = game_data.HUNT_ALL
    default = game_data.HUNT_ALL


class TrophyGrade(Choice):
    """Only used when the goal is Trophy Hunt. The lowest trophy you need on each of those missions."""
    display_name = "Trophy Grade Required For Goal"
    option_bronze = 1
    option_silver = 2
    option_gold = 3
    option_platinum = 4
    default = 1


class ExcludeStoryMode(Toggle):
    """
    Only used when the goal is Trophy Hunt. Story Mode locations never hold anything required to
    win (only useful and filler items).
    """
    display_name = "Exclude Story Mode"


class ExcludeHardStory(DefaultOnToggle):
    """Never put anything important on completing a story level on Hard."""
    display_name = "Exclude Hard Story Locations"


class ExcludeAllPlatinum(Toggle):
    """Never put anything important on a Platinum trophy."""
    display_name = "Exclude All Platinum Trophies"


class ExcludePlatinumTrophies(OptionSet):
    """
    Missions whose Platinum trophy only ever gives a filler or useful item, never one needed for
    progression. Use the mission's own name, for example ["Dam Bursters", "Pane in the Neck"].
    """
    display_name = "Exclude Specific Platinum Trophies"
    valid_keys = frozenset(name.casefold() for name in (m.name for m in game_data.MISSIONS))
    valid_keys_casefold = True


class Ts2DeathLink(DeathLink):
    """
    When you fail a mission, everyone else with Death Link on dies; when they die, the story level
    you are playing fails, or you die in an Arcade League mission or Challenge. Failing means dying in a Story level, failing a Story objective, or failing
    an Arcade League mission or Challenge (finishing below the trophy you need counts). In Arcade
    League missions where you respawn, deaths are counted with Death Link Amnesty instead.
    """
    display_name = "Death Link"


class DeathLinkAmnesty(Range):
    """
    Arcade League missions only: how many times you can die in one mission before a Death Link is
    sent (1 = every death). The count starts again with every mission, including a restart.
    Story Mode and Challenges are not affected: there a death fails the mission, and a failed
    mission always sends a Death Link. Does nothing unless Death Link is on.
    """
    display_name = "Death Link Amnesty (Arcade League)"
    range_start = 1
    range_end = 5
    default = 3


class EasierTopShot(DefaultOnToggle):
    """Easier Platinum time for Top Shot: come 1st within 2:00 (normally 1:10). Silver 4:00 and Gold
    3:00 stay the same."""
    display_name = "Easier Top Shot"


class ArcadeGroupMilestones(DefaultOnToggle):
    """
    Adds a location for each Arcade League group, such as "AL - Beginners Series - Group Completed".
    Each needs at least a Bronze trophy on every mission of its group.
    """
    display_name = "Arcade League Group Milestones"


class ChallengeGroupMilestones(DefaultOnToggle):
    """
    Adds a location for each Challenge group, such as "Challenge - Behead The Undead - Group
    Completed". Each needs at least a Bronze trophy on every mission of its group.
    """
    display_name = "Challenge Group Milestones"


class LeagueMilestones(DefaultOnToggle):
    """
    Adds "Amateur League Completed", "Honorary League Completed" and "Elite League Completed".
    Each needs at least a Bronze trophy on every mission of that league.
    """
    display_name = "Complete Arcade League Milestones"


class AllChallengesMilestone(DefaultOnToggle):
    """Adds "All Challenges Completed". It needs at least a Bronze trophy on every Challenge."""
    display_name = "Complete All Challenges Milestone"


class BeheadMultiplier(Choice):
    """
    Progressive Behead The Undead Score Multiplier: each one you have multiplies your points in
    Fight Off The Living Dead, Day of the Dammed and Sergio's Last Stand (x2, x3, then x4 with all
    three): every kill scores more, and so does the combo bonus.
    Off: there are none; points are normal.
    Start With One: you start with one (x2) and the other two are shuffled.
    Shuffle All: all three are shuffled.
    """
    display_name = "Progressive Behead The Undead Score Multipliers"
    option_off = 0
    option_start_with_one = 1
    option_shuffle_all = 2
    default = 2


class EarlyBeheadMultiplier(Toggle):
    """
    Makes one of the shuffled Progressive Behead The Undead Score Multipliers an early item, even if
    you already start with one. Does nothing when the multiplier is Off.
    """
    display_name = "Early Behead The Undead Score Multiplier"



class StartingArmour(Choice):
    """
    Progressive Starting Armour: four items. Each one you have raises the armour you get when you
    start a mission, restart it, retry after dying or respawn: 25%, 50%, 75%, then a full bar.
    It applies in Story, every Arcade League mission, Behead The Undead, Banana Chomp and
    TimeSplitters 'Story' Classic.
    Off: there are none.
    Start With One: you start with one (25%) and the other three are shuffled.
    Shuffle All: all four are shuffled.
    """
    display_name = "Progressive Starting Armour"
    option_off = 0
    option_start_with_one = 1
    option_shuffle_all = 2
    default = 2



class IncludeWeaponBuffs(DefaultOnToggle):
    """
    Adds weapon buffs (bigger clips, more reserve ammo) to the item pool. They fill whatever
    locations are left after every other item, so a game holds a random selection of them.
    When off, those locations hold "Nothing" instead.
    """
    display_name = "Include Weapon Buffs"


class IncludeDamageResistances(DefaultOnToggle):
    """
    Adds damage resistances: Progressive Bullet, Explosive, Fire, Plasma and Melee Damage
    Resistance, six of each. Every copy takes 10% off that kind of damage you take (up to 60%);
    enemies are not affected. They fill the locations left after every other item together with
    the weapon buffs, each resistance twice as likely to be picked as a weapon buff.
    """
    display_name = "Include Damage Resistances"


class IncludeArchipelagoShop(DefaultOnToggle):
    """
    Turns Options > View Cutscenes into the Archipelago Shop ("Options & Shop" > "Archipelago
    Shop"), where you buy locations with points. Points come from trophies (Bronze 10, Silver 20,
    Gold 30, Platinum 40, a better trophy counting the ones below it), story levels finished
    (Easy 15, Normal 35, Hard 50, likewise), every kill (1) and Bronze/Silver/Gold/Platinum Trophy
    items. Prices: 1-15 points for filler and traps, 5-75 for useful items, 15-200 for progression,
    85-200 for story levels. Cutscenes can't be watched from that menu.
    """
    display_name = "Include Archipelago Shop"


class ShopLocations(Choice):
    """
    How many shop locations there are. The shop shows 13 at a time; every 13 after the first
    needs one more Progressive Shop Restock item (one for 26 ... four for 65).
    """
    display_name = "How Many Shop Locations"
    option_13 = 13
    option_26 = 26
    option_39 = 39
    option_52 = 52
    option_65 = 65
    default = 13


class ShopHints(Choice):
    """
    Which shop items are hinted to their owners when you open the shop: none, all of them, or only
    progression items.
    """
    display_name = "Shop Hints"
    option_none = game_data.SHOP_HINTS_NONE
    option_all = game_data.SHOP_HINTS_ALL
    option_progression_only = game_data.SHOP_HINTS_PROGRESSION
    default = game_data.SHOP_HINTS_PROGRESSION


class IncludeCheatTraps(Toggle):
    """
    Adds cheat traps: Big Heads, Small Heads, Big Hands, Fat Characters, Cardboard Characters,
    Rotating Heads, All Characters Cloaked and Slow Motion Deaths, at most three of each. Each
    switches its cheat on for a while (see Cheat Trap Duration) as soon as you are playing a level.
    They take the place of "Nothing" items first; when there are none left, they are shuffled in
    with the weapon buffs.
    """
    display_name = "Include Cheat Traps"


class CheatTrapDuration(Range):
    """How long a cheat trap lasts, in seconds of play (time in menus and loading does not count)."""
    display_name = "Cheat Trap Duration"
    range_start = 10
    range_end = 120
    default = 30


class AnacondaChecks(Range):
    """
    How many Anaconda (the Temporal Uplink's snake game) locations there are: one per 500 points
    scored in a single game. 0 = none, 1 = 500 points, 2 = 500 and 1000 points ... 20 = every
    500 points up to 10,000.
    The Temporal Uplink's games need their cartridge item and at least one story level, since
    they can only be played during Story.
    """
    display_name = "How many Anaconda Checks?"
    range_start = 0
    range_end = game_data.ANACONDA_MAX_STEPS
    default = 0


class RetroRacerChecks(Toggle):
    """
    Adds six RetroRacer locations: one for each of the five laps you finish, and one for
    completing the race.
    """
    display_name = "Include RetroRacer Checks?"


class AstroLanderChecks(Range):
    """
    How many AstroLander locations there are: one per level completed. 0 = none, 1 = Level 1,
    2 = Levels 1 and 2 ... 11 = all eleven levels.
    """
    display_name = "How many AstroLander Checks?"
    range_start = 0
    range_end = game_data.ASTROLANDER_LEVEL_COUNT
    default = 0


@dataclass
class Ts2Options(PerGameCommonOptions):
    starting_item: StartingItem
    starting_mission_count: StartingMissionCount
    story_mode: StoryMode
    goal: Goal
    death_link: Ts2DeathLink
    death_link_amnesty: DeathLinkAmnesty
    story_levels_required: StoryLevelsRequired
    trophies_required: TrophiesRequired
    trophies_required_grade: TrophiesRequiredGrade
    trophy_hunt_setting: TrophyHuntSetting
    trophy_grade: TrophyGrade
    exclude_story_mode: ExcludeStoryMode
    exclude_hard_story: ExcludeHardStory
    exclude_all_platinum: ExcludeAllPlatinum
    exclude_platinum_trophies: ExcludePlatinumTrophies
    easier_top_shot: EasierTopShot
    arcade_group_milestones: ArcadeGroupMilestones
    challenge_group_milestones: ChallengeGroupMilestones
    league_milestones: LeagueMilestones
    all_challenges_milestone: AllChallengesMilestone
    behead_multiplier: BeheadMultiplier
    early_behead_multiplier: EarlyBeheadMultiplier
    starting_armour: StartingArmour
    include_weapon_buffs: IncludeWeaponBuffs
    include_damage_resistances: IncludeDamageResistances
    include_archipelago_shop: IncludeArchipelagoShop
    shop_locations: ShopLocations
    shop_hints: ShopHints
    include_cheat_traps: IncludeCheatTraps
    cheat_trap_duration: CheatTrapDuration
    anaconda_checks: AnacondaChecks
    retroracer_checks: RetroRacerChecks
    astrolander_checks: AstroLanderChecks


class Ts2WebWorld(WebWorld):
    tutorials = [
        Tutorial(
            tutorial_name="Setup Guide",
            description="A guide to setting up TimeSplitters 2 for Archipelago.",
            language="English",
            file_name="en_Setup.md",
            link="setup/en",
            authors=["CaptPurpleHeart"],
        )
    ]
    option_groups = [
        OptionGroup("Game Options", [StartingItem, StartingMissionCount, StoryMode, Goal, Ts2DeathLink,
                                     DeathLinkAmnesty]),
        OptionGroup("Goal Options - 2401 Space Station", [StoryLevelsRequired, TrophiesRequired,
                                                          TrophiesRequiredGrade]),
        OptionGroup("Goal Options - Trophy Hunt", [TrophyHuntSetting, TrophyGrade, ExcludeStoryMode]),
        OptionGroup("Difficulty Settings", [ExcludeHardStory, ExcludeAllPlatinum, ExcludePlatinumTrophies,
                                            EasierTopShot]),
        OptionGroup("Milestone Locations", [ArcadeGroupMilestones, ChallengeGroupMilestones, LeagueMilestones,
                                            AllChallengesMilestone]),
        OptionGroup("Temporal Uplink Settings", [AnacondaChecks, RetroRacerChecks, AstroLanderChecks]),
        OptionGroup("Bonus Items", [BeheadMultiplier, EarlyBeheadMultiplier, StartingArmour,
                                    IncludeWeaponBuffs, IncludeDamageResistances]),
        OptionGroup("Archipelago Shop", [IncludeArchipelagoShop, ShopLocations, ShopHints]),
        OptionGroup("Traps", [IncludeCheatTraps, CheatTrapDuration]),
    ]


class Ts2World(World):
    """
    TimeSplitters 2 is a time-travelling first person shooter.
    Story levels, Arcade League missions and Challenges are unlocked by items; trophies and
    story level completions are the checks.
    """
    game = game_data.GAME_NAME
    web = Ts2WebWorld()

    options_dataclass = Ts2Options
    options: Ts2Options

    item_name_to_id = game_data.ITEM_NAME_TO_ID
    location_name_to_id = game_data.LOCATION_NAME_TO_ID
    item_name_groups = {
        "Story Levels": set(game_data.STORY_ITEM_NAMES) | {game_data.PROGRESSIVE_STORY_ITEM_NAME},
        "Arcade Missions": set(game_data.ARCADE_ITEM_NAMES),
        "Challenges": set(game_data.CHALLENGE_ITEM_NAMES),
        "Characters": set(game_data.CHARACTER_ITEM_NAMES),
        "Cheats": set(game_data.CHEAT_ITEM_NAMES),
        "Silly Hats": set(game_data.HAT_ITEM_NAMES),
        "Arcade Maps": set(game_data.MAP_ITEM_NAMES),
        "Game Modes": set(game_data.MODE_ITEM_NAMES),
        "Weapons": set(game_data.WEAPON_ITEM_NAMES),
        "Multipliers": set(game_data.MULTIPLIER_ITEM_NAMES),
        "Cartridges": set(game_data.CARTRIDGE_ITEM_NAMES),
        "Weapon Buffs": set(game_data.WEAPON_BUFF_ITEM_NAMES),
        "Damage Resistances": set(game_data.RESISTANCE_ITEM_NAMES),
        "Trophy Points": set(game_data.TROPHY_FILLER_ITEM_NAMES),
        "Traps": set(game_data.TRAP_ITEM_NAMES),
        "Bonus Items": set(game_data.MULTIPLIER_ITEM_NAMES) | {game_data.STARTING_ARMOUR_ITEM_NAME},
    }

    # Universal Tracker: it can rebuild this world from slot data alone (see interpret_slot_data).
    ut_can_gen_without_yaml = True

    starting_missions: list[str]
    starting_character: str = ""
    starting_weapon: str = ""

    @property
    def shop_size(self) -> int:
        return int(self.options.shop_locations.value) if self.options.include_archipelago_shop else 0

    @property
    def progressive(self) -> bool:
        return self.options.story_mode == game_data.STORY_PROGRESSIVE

    @property
    def story_goal(self) -> bool:
        return self.options.goal == game_data.GOAL_SPACE_STATION

    @property
    def story_excluded(self) -> bool:
        return not self.story_goal and bool(self.options.exclude_story_mode)

    @property
    def hunted(self) -> set[str]:
        """Item names of the missions on the goal path (empty for the 2401 Space Station goal)."""
        if self.story_goal:
            return set()
        return {m.item_name for m in game_data.hunted_missions(self.options.trophy_hunt_setting.value)}

    def choose_starting_missions(self) -> list[str]:
        """The starting mission(s), following the Starting Mission and count options."""
        stories = list(game_data.STORY_ITEM_NAMES[:game_data.FINAL_STORY_LEVEL])   # never Space Station
        choice = self.options.starting_item.value
        if self.story_excluded and choice in (StartingItem.option_random_story_mission,
                                              StartingItem.option_siberia):
            choice = StartingItem.option_random_arcade_or_challenge_mission
        if choice == StartingItem.option_random_story_mission:
            return [self.random.choice(stories)]
        if choice == StartingItem.option_siberia:
            return [game_data.STORY_ITEM_NAMES[0]]
        if choice == StartingItem.option_random_arcade_mission:
            pool = list(game_data.ARCADE_ITEM_NAMES)
        elif choice == StartingItem.option_random_challenge_mission:
            pool = list(game_data.CHALLENGE_ITEM_NAMES)
        else:
            pool = list(game_data.MISSION_ITEM_NAMES)
        if choice == StartingItem.option_random_any_mission and not self.story_excluded:
            first = self.random.choice(pool + stories)
            if first in stories:
                return [first]
        count = min(self.options.starting_mission_count.value, len(pool))
        return self.random.sample(pool, count)

    def generate_early(self) -> None:
        # Universal Tracker rebuilds the world from the slot data of the game you connected to.
        passthrough = getattr(self.multiworld, "re_gen_passthrough", {}).get(self.game)
        if passthrough:
            self.options.goal.value = passthrough["goal"]
            self.options.story_mode.value = passthrough.get("story_mode", game_data.STORY_INDIVIDUAL)
            for option in ("arcade_group_milestones", "challenge_group_milestones", "league_milestones",
                           "all_challenges_milestone"):
                getattr(self.options, option).value = passthrough.get(option, 1)
            self.options.story_levels_required.value = passthrough["story_levels_required"]
            self.options.exclude_hard_story.value = passthrough["exclude_hard_story"]
            self.options.trophy_grade.value = passthrough["trophy_grade"]
            self.options.trophies_required.value = passthrough.get("trophies_required", 0)
            self.options.trophies_required_grade.value = passthrough.get("trophies_required_grade", 1)
            self.options.trophy_hunt_setting.value = passthrough.get("trophy_hunt_setting", game_data.HUNT_ALL)
            self.options.exclude_story_mode.value = passthrough.get("exclude_story_mode", 0)
            self.options.exclude_all_platinum.value = passthrough["exclude_all_platinum"]
            self.options.exclude_platinum_trophies.value = set(passthrough.get("exclude_platinum_trophies", []))
            self.starting_missions = list(passthrough.get("starting_missions", [passthrough.get("starting_mission")]))
            self.starting_character = passthrough["starting_character"]
            self.starting_weapon = passthrough["starting_weapon"]
            self.options.behead_multiplier.value = passthrough.get("behead_multiplier", 0)
            self.options.starting_armour.value = passthrough.get("starting_armour", 0)
            self.options.include_weapon_buffs.value = passthrough.get("include_weapon_buffs", 0)
            self.options.include_damage_resistances.value = passthrough.get("include_damage_resistances", 0)
            self.options.include_archipelago_shop.value = passthrough.get("include_archipelago_shop", 0)
            self.options.shop_locations.value = passthrough.get("shop_locations", 13)
            self.options.shop_hints.value = passthrough.get("shop_hints", game_data.SHOP_HINTS_ALL)
            self.options.include_cheat_traps.value = passthrough.get("include_cheat_traps", 0)
            self.options.anaconda_checks.value = passthrough.get("anaconda_checks", 0)
            self.options.retroracer_checks.value = passthrough.get("retroracer_checks", 0)
            self.options.astrolander_checks.value = passthrough.get("astrolander_checks", 0)
        else:
            self.starting_missions = self.choose_starting_missions()
            if self.progressive and self.starting_missions[0] in game_data.STORY_ITEM_NAMES:
                # Progressive levels open in order, so a story start is always the first level.
                self.starting_missions = [game_data.PROGRESSIVE_STORY_ITEM_NAME]
            self.starting_character = self.random.choice(game_data.CHARACTER_ITEM_NAMES)
            # One weapon, so the custom weapon set editor always has something to offer.
            self.starting_weapon = self.random.choice(game_data.WEAPON_ITEM_NAMES)
        for name in (*self.starting_missions, self.starting_character, self.starting_weapon):
            self.multiworld.push_precollected(self.create_item(name))
        for name, (setting, early) in self.multiplier_options().items():
            if setting == BeheadMultiplier.option_start_with_one:
                self.multiworld.push_precollected(self.create_item(name))
            if setting != BeheadMultiplier.option_off and early:
                self.multiworld.early_items[self.player][name] = 1
        if self.options.starting_armour == StartingArmour.option_start_with_one:
            self.multiworld.push_precollected(self.create_item(game_data.STARTING_ARMOUR_ITEM_NAME))

    def multiplier_options(self) -> dict[str, tuple[int, bool]]:
        """Per multiplier item: (Off / Start With One / Shuffle All, Early)."""
        return {
            game_data.BEHEAD_MULTIPLIER_ITEM_NAME: (int(self.options.behead_multiplier.value),
                                                    bool(self.options.early_behead_multiplier)),
        }

    def shuffled_multipliers(self) -> list[str]:
        names = []
        for name, (setting, _early) in self.multiplier_options().items():
            if setting == BeheadMultiplier.option_shuffle_all:
                names += [name] * game_data.MULTIPLIER_COPIES
            elif setting == BeheadMultiplier.option_start_with_one:
                names += [name] * (game_data.MULTIPLIER_COPIES - 1)
        armour = self.options.starting_armour.value
        if armour == StartingArmour.option_shuffle_all:
            names += [game_data.STARTING_ARMOUR_ITEM_NAME] * game_data.STARTING_ARMOUR_COPIES
        elif armour == StartingArmour.option_start_with_one:
            names += [game_data.STARTING_ARMOUR_ITEM_NAME] * (game_data.STARTING_ARMOUR_COPIES - 1)
        return names

    def has_story_level(self, state, level: int) -> bool:
        if self.progressive:
            if not state.has(game_data.PROGRESSIVE_STORY_ITEM_NAME, self.player, level + 1):
                return False
        elif not state.has(game_data.story_item_name(level), self.player):
            return False
        if level == game_data.FINAL_STORY_LEVEL and self.story_goal:
            # Space Station also waits for N other levels to be beaten (with progressive items,
            # owning Space Station already means owning all 9 others) and N missions.
            others = game_data.STORY_ITEM_NAMES[:game_data.FINAL_STORY_LEVEL]
            if not self.progressive and not state.has_from_list_unique(
                    others, self.player, self.options.story_levels_required.value):
                return False
            needed = self.options.trophies_required.value
            if needed and sum(1 for m in game_data.MISSIONS if state.has(m.item_name, self.player)) < needed:
                return False
        return True

    def create_regions(self) -> None:
        menu = Region("Menu", self.player, self.multiworld)
        self.multiworld.regions.append(menu)
        platinum = len(game_data.TIERS)
        excluded_platinum = {name.casefold() for name in self.options.exclude_platinum_trophies.value}

        for mission in game_data.MISSIONS:
            region = Region(mission.item_name, self.player, self.multiworld)
            region.add_locations(
                {
                    game_data.location_name(mission, tier): game_data.location_id(mission.number, tier)
                    for tier in range(1, platinum + 1)
                },
                Ts2Location,
            )
            self.multiworld.regions.append(region)
            if self.options.exclude_all_platinum or mission.name.casefold() in excluded_platinum:
                self.get_location(game_data.location_name(mission, platinum)).progress_type = \
                    LocationProgressType.EXCLUDED
            # Every mission needs only its own item: the client opens its group with it.
            entrance = menu.connect(region)
            set_rule(entrance, lambda state, name=mission.item_name: state.has(name, self.player))

        # Milestones: every mission of a group, a league or all Challenges, with a Bronze or better.
        milestones_on = {
            game_data.MILESTONE_ARCADE_GROUPS: self.options.arcade_group_milestones,
            game_data.MILESTONE_CHALLENGE_GROUPS: self.options.challenge_group_milestones,
            game_data.MILESTONE_LEAGUES: self.options.league_milestones,
            game_data.MILESTONE_ALL_CHALLENGES: self.options.all_challenges_milestone,
        }
        for name, location_id, missions, kind in game_data.MILESTONES:
            if not milestones_on[kind]:
                continue
            menu.add_locations({name: location_id}, Ts2Location)
            needed = tuple(m.item_name for m in missions)
            set_rule(self.get_location(name), lambda state, needed=needed: state.has_all(needed, self.player))

        hard = len(game_data.STORY_DIFFICULTIES) - 1
        for level in range(len(game_data.STORY_LEVELS)):
            region = Region(f"Story: {game_data.STORY_LEVELS[level]}", self.player, self.multiworld)
            locations: dict[str, int | None] = {
                game_data.objective_location_name(level, name): game_data.objective_location_id(level, record)
                for lvl, record, _address, _text, name, _roles in game_data.STORY_OBJECTIVES if lvl == level
            }
            cartridges = {game_data.cartridge_location_name(game, lvl): game_data.cartridge_location_id(k)
                          for k, (game, lvl, _o, _h) in enumerate(game_data.CARTRIDGES) if lvl == level}
            locations.update(cartridges)
            if level == game_data.FINAL_STORY_LEVEL and self.story_goal:
                # Space Station is the goal: one "Completed" event instead of the three checks.
                locations[game_data.STORY_GOAL_LOCATION_NAME] = None
            else:
                for d in range(len(game_data.STORY_DIFFICULTIES)):
                    locations[game_data.story_location_name(level, d)] = game_data.story_location_id(level, d)
            region.add_locations(locations, Ts2Location)
            self.multiworld.regions.append(region)
            if self.options.exclude_hard_story and game_data.story_location_name(level, hard) in locations:
                self.get_location(game_data.story_location_name(level, hard)).progress_type = \
                    LocationProgressType.EXCLUDED
            for game, lvl, _o, hard_only in game_data.CARTRIDGES:
                if lvl == level and hard_only and self.options.exclude_hard_story:
                    # Only reachable on Hard, so it follows Exclude Hard Story like "Hard Completed".
                    self.get_location(game_data.cartridge_location_name(game, lvl)).progress_type = \
                        LocationProgressType.EXCLUDED
            if self.story_excluded:
                # Exclude Story Mode: anything but progression (useful items are still allowed).
                for name, address in locations.items():
                    if address is not None:
                        self.get_location(name).item_rule = lambda item: not item.advancement
            entrance = menu.connect(region)
            set_rule(entrance, lambda state, k=level: self.has_story_level(state, k))

        # Temporal Uplink games: playable during any story level once you have the cartridge.
        step = game_data.ANACONDA_STEP
        games = {
            "Anaconda": {game_data.anaconda_location_name(k * step): game_data.anaconda_location_id(k * step)
                         for k in range(1, self.options.anaconda_checks.value + 1)},
            "RetroRacer": {name: game_data.retroracer_location_id(k)
                           for k, name in enumerate(game_data.retroracer_location_names())}
            if self.options.retroracer_checks else {},
            "AstroLander": {game_data.astrolander_location_name(k): game_data.astrolander_location_id(k)
                            for k in range(1, self.options.astrolander_checks.value + 1)},
        }
        for game, locations in games.items():
            if not locations:
                continue
            region = Region(f"Temporal Uplink: {game}", self.player, self.multiworld)
            region.add_locations(locations, Ts2Location)
            self.multiworld.regions.append(region)
            if self.story_excluded:
                for location in region.locations:
                    location.item_rule = lambda item: not item.advancement
            entrance = menu.connect(region)
            cartridge = game_data.cartridge_item_name(game)
            set_rule(entrance, lambda state, cartridge=cartridge: state.has(cartridge, self.player) and any(
                self.has_story_level(state, k) for k in range(len(game_data.STORY_LEVELS))))

        # The Archipelago Shop: batch b (13 locations) needs b Progressive Shop Restocks. Points can
        # always be earned (every kill counts), so nothing else is needed.
        if self.options.include_archipelago_shop:
            region = Region("Archipelago Shop", self.player, self.multiworld)
            region.add_locations({game_data.shop_location_name(k): game_data.shop_location_id(k)
                                  for k in range(self.shop_size)}, Ts2Location)
            self.multiworld.regions.append(region)
            menu.connect(region)
            for k in range(game_data.SHOP_ROWS, self.shop_size):
                batch = k // game_data.SHOP_ROWS
                set_rule(self.get_location(game_data.shop_location_name(k)),
                         lambda state, batch=batch: state.has(game_data.SHOP_RESTOCK_ITEM_NAME, self.player, batch))

        # Goal: an event location holding a locked "Victory" item.
        if self.story_goal:
            victory = self.get_location(game_data.STORY_GOAL_LOCATION_NAME)
        else:
            menu.add_locations({game_data.TROPHY_GOAL_LOCATION_NAME: None}, Ts2Location)
            victory = self.get_location(game_data.TROPHY_GOAL_LOCATION_NAME)
            hunted = tuple(self.hunted)
            set_rule(victory, lambda state: state.has_all(hunted, self.player))
        victory.place_locked_item(self.create_item(game_data.VICTORY_ITEM_NAME))

    def create_items(self) -> None:
        names = list(game_data.MISSION_ITEM_NAMES)
        if self.progressive:
            names += [game_data.PROGRESSIVE_STORY_ITEM_NAME] * len(game_data.STORY_LEVELS)
        else:
            names += list(game_data.STORY_ITEM_NAMES)
        for name in self.starting_missions:
            names.remove(name)
        # Multipliers come first of the bonus items, so they are never the ones left out.
        names += self.shuffled_multipliers()
        # Cheats and hats go in before characters, so they are the last to be left out if room
        # runs short.
        names += list(game_data.CARTRIDGE_ITEM_NAMES)
        names += [game_data.SHOP_RESTOCK_ITEM_NAME] * (self.shop_size // game_data.SHOP_ROWS - 1 if self.shop_size else 0)
        names += list(game_data.CHEAT_ITEM_NAMES) + list(game_data.HAT_ITEM_NAMES)
        names += list(game_data.MAP_ITEM_NAMES) + list(game_data.MODE_ITEM_NAMES)
        names += [name for name in game_data.WEAPON_ITEM_NAMES if name != self.starting_weapon]
        names += [name for name in game_data.CHARACTER_ITEM_NAMES if name != self.starting_character]
        location_count = sum(1 for loc in self.multiworld.get_locations(self.player) if loc.address is not None)
        names = names[:location_count]
        # Whatever room is left goes to weapon buffs and damage resistances when they are switched
        # on: first every copy of the buffs marked "always in the pool", then a weighted random
        # pick from all the other copies (a resistance counts RESISTANCE_WEIGHT times as much as a
        # buff, as there are far fewer of them). "Nothing" only if they run out.
        # Cheat traps (at most three of each) join the random pick, so they take "Nothing" slots
        # first and are only mixed in with the buffs when there are no "Nothing" slots left.
        always, others = [], []
        if self.options.include_weapon_buffs:
            for name, buff in zip(game_data.WEAPON_BUFF_ITEM_NAMES, game_data.WEAPON_BUFFS):
                if buff[6]:
                    always.extend([name] * buff[5])
                else:
                    others.extend([(name, 1.0)] * buff[5])
        if self.options.include_damage_resistances:
            for name in game_data.RESISTANCE_ITEM_NAMES:
                others.extend([(name, game_data.RESISTANCE_WEIGHT)] * game_data.RESISTANCE_COPIES)
        if self.options.include_cheat_traps:
            others += [(name, 1.0) for name in game_data.TRAP_ITEM_NAMES for _ in range(game_data.TRAP_COPIES)]
        if self.shop_size:
            # Trophy items (points for the shop) join the pick too, and take every "Nothing" slot.
            others += [(self.random_trophy_filler(), game_data.TROPHY_FILLER_WEIGHT)
                       for _ in range(game_data.TROPHY_FILLER_COPIES)]
        room = max(0, location_count - len(names) - len(always))
        if len(others) <= room:
            picked = [name for name, _weight in others]
        else:
            # Weighted pick without replacement: each copy gets the key random() ** (1 / weight);
            # the highest keys win.
            keyed = sorted(((self.random.random() ** (1.0 / weight), name) for name, weight in others),
                           reverse=True)
            picked = [name for _key, name in keyed[:room]]
        names += always[:max(0, location_count - len(names))]
        names += picked
        if self.shop_size:
            names += [self.random_trophy_filler() for _ in range(location_count - len(names))]
        names += [game_data.FILLER_ITEM_NAME] * (location_count - len(names))
        self.multiworld.itempool += [self.create_item(name) for name in names]

    def random_trophy_filler(self) -> str:
        grades = [t[0] for t in game_data.TROPHY_FILLERS]
        weights = [t[2] for t in game_data.TROPHY_FILLERS]
        return game_data.trophy_filler_item_name(self.random.choices(grades, weights)[0])

    def create_item(self, name: str) -> Ts2Item:
        if name == game_data.VICTORY_ITEM_NAME:
            return Ts2Item(name, ItemClassification.progression, None, self.player)
        if name in game_data.STORY_ITEM_NAMES or name == game_data.PROGRESSIVE_STORY_ITEM_NAME:
            # On the goal path for 2401 Space Station; for Trophy Hunt they only open more checks.
            # (They stay progression even with Exclude Story Mode: logic needs them to reach those
            # checks, which then only hold useful and filler items.)
            classification = (ItemClassification.progression if self.story_goal
                              else ItemClassification.progression_skip_balancing)
        elif name in game_data.TRAP_ITEM_NAMES:
            classification = ItemClassification.trap
        elif name == game_data.SHOP_RESTOCK_ITEM_NAME:
            classification = ItemClassification.progression_skip_balancing
        elif name in game_data.CARTRIDGE_ITEM_NAMES:
            classification = ItemClassification.progression_skip_balancing
        elif name in game_data.MISSION_ITEM_NAMES:
            classification = (ItemClassification.progression if name in self.hunted
                              else ItemClassification.progression_skip_balancing)
        elif (name in game_data.CHEAT_ITEM_NAMES or name in game_data.HAT_ITEM_NAMES
              or name in game_data.MULTIPLIER_ITEM_NAMES or name == game_data.STARTING_ARMOUR_ITEM_NAME
              or name in game_data.WEAPON_BUFF_ITEM_NAMES or name in game_data.RESISTANCE_ITEM_NAMES):
            classification = ItemClassification.useful
        else:
            classification = ItemClassification.filler   # characters, maps, modes, weapons and "Nothing"
        return Ts2Item(name, classification, game_data.ITEM_NAME_TO_ID[name], self.player)

    def get_filler_item_name(self) -> str:
        if self.shop_size:
            return self.random_trophy_filler()
        return game_data.FILLER_ITEM_NAME

    @staticmethod
    def is_story_level_item(item) -> bool:
        """A story level of this game or of TimeSplitters: Future Perfect (priced 85 or more)."""
        if item.game == game_data.GAME_NAME:
            return item.name in game_data.STORY_ITEM_NAMES or item.name == game_data.PROGRESSIVE_STORY_ITEM_NAME
        return item.game == game_data.TSFP_GAME_NAME and item.name in game_data.TSFP_STORY_ITEM_NAMES

    def shop_prices(self) -> list[int]:
        """The price of each shop location, by what ended up there (after the fill)."""
        import random
        rng = random.Random(f"{self.multiworld.seed}-{self.player}-shop")
        prices = []
        for k in range(self.shop_size):
            item = self.get_location(game_data.shop_location_name(k)).item
            if item is None:
                kind = "filler"
            elif item.advancement:
                kind = "progression"
            elif item.useful:
                kind = "useful"
            else:
                kind = "filler"
            low, high = game_data.SHOP_PRICES[kind]
            if item is not None and self.is_story_level_item(item):
                low, high = game_data.SHOP_STORY_PRICES
            prices.append(rng.randint(low, high))
        return prices

    def set_rules(self) -> None:
        self.multiworld.completion_condition[self.player] = lambda state: state.has(
            game_data.VICTORY_ITEM_NAME, self.player
        )

    def fill_slot_data(self) -> dict[str, Any]:
        return {
            "world_version": game_data.WORLD_VERSION,
            "starting_mission": self.starting_missions[0],
            "starting_missions": list(self.starting_missions),
            "trophies_required": int(self.options.trophies_required.value),
            "trophies_required_grade": int(self.options.trophies_required_grade.value),
            "trophy_hunt_setting": int(self.options.trophy_hunt_setting.value),
            "exclude_story_mode": int(bool(self.options.exclude_story_mode)),
            "starting_character": self.starting_character,
            "starting_weapon": self.starting_weapon,
            "goal": int(self.options.goal.value),
            "story_mode": int(self.options.story_mode.value),
            "arcade_group_milestones": int(bool(self.options.arcade_group_milestones)),
            "challenge_group_milestones": int(bool(self.options.challenge_group_milestones)),
            "league_milestones": int(bool(self.options.league_milestones)),
            "all_challenges_milestone": int(bool(self.options.all_challenges_milestone)),
            "story_levels_required": int(self.options.story_levels_required.value),
            "exclude_hard_story": int(bool(self.options.exclude_hard_story)),
            "trophy_grade": int(self.options.trophy_grade.value),
            "exclude_all_platinum": int(bool(self.options.exclude_all_platinum)),
            "exclude_platinum_trophies": sorted(self.options.exclude_platinum_trophies.value),
            "behead_multiplier": int(self.options.behead_multiplier.value),
            "starting_armour": int(self.options.starting_armour.value),
            "include_weapon_buffs": int(bool(self.options.include_weapon_buffs)),
            "include_damage_resistances": int(bool(self.options.include_damage_resistances)),
            "include_archipelago_shop": int(bool(self.options.include_archipelago_shop)),
            "shop_locations": self.shop_size,
            "shop_prices": self.shop_prices(),
            "shop_hints": int(self.options.shop_hints.value),
            "include_cheat_traps": int(bool(self.options.include_cheat_traps)),
            "trap_duration": int(self.options.cheat_trap_duration.value),
            "death_link": int(bool(self.options.death_link)),
            "death_link_amnesty": int(self.options.death_link_amnesty.value),
            "easier_top_shot": int(bool(self.options.easier_top_shot)),
            "anaconda_checks": int(self.options.anaconda_checks.value),
            "retroracer_checks": int(bool(self.options.retroracer_checks)),
            "astrolander_checks": int(self.options.astrolander_checks.value),
        }

    @staticmethod
    def interpret_slot_data(slot_data: dict[str, Any]) -> dict[str, Any]:
        """Universal Tracker: hand the slot data back to generate_early (as re_gen_passthrough)."""
        return slot_data


def launch_client(*args):
    from .ts2_client import main
    launch_subprocess(main, name="TS2 Client", args=args)


icon_paths["TS2"] = f"ap:{__name__}/images/icon.png"

components.append(
    Component(
        "TimeSplitters 2 Client",
        func=launch_client,
        game_name=game_data.GAME_NAME,
        icon="TS2",
        supports_uri=True,
    )
)
