"""
Archipelago client for TimeSplitters 2 running in Dolphin.

Every 0.25 s it:
  1. reads the loaded profile's trophies and story completions and reports new ones as checks, and
  2. makes the game's story levels, playable missions, characters and cheats match the items the
     player has received.
"""
import asyncio
import time
import traceback
from typing import Any, Optional

import Utils
from CommonClient import get_base_parser, gui_enabled, logger, server_loop
from NetUtils import ClientStatus

import dolphin_memory_engine as dolphin

from . import game_data, game_state

# Universal Tracker, when it is installed, provides the tracker tab and in-logic checks. Its
# context is a drop-in replacement for the normal one.
tracker_loaded = False
try:
    from worlds.tracker.TrackerClient import TrackerGameContext as CommonContext
    tracker_loaded = True
except ImportError:
    from CommonClient import CommonContext

CONNECTED = "Dolphin connected successfully."
NOT_CONNECTED = "Dolphin connection has not been initiated."
LOST = "Dolphin connection was lost. Start Dolphin and the game, then wait."
WRONG_GAME = "Dolphin is running a different game. Load TimeSplitters 2."


class Ts2Context(CommonContext):
    game = game_data.GAME_NAME
    items_handling = 0b111  # the server sends us every item, including our own

    def __init__(self, server_address: Optional[str], password: Optional[str]) -> None:
        super().__init__(server_address, password)
        self.dolphin_status: str = NOT_CONNECTED
        self.dolphin_sync_task: Optional[asyncio.Task] = None
        self.reported_locations: set[int] = set()  # sent already, server may not have confirmed yet
        self.items_synced: bool = False             # True once the server has sent our item list
        self.connected_at: Optional[float] = None   # when the server accepted our login
        self.victory_sent: bool = False
        self.data_ok: bool = False                  # group table checked for this game session
        self.lock_logged: str = ""                  # last mission lock state written to the log
        self.story_logged: str = ""                 # last story lock state written to the log
        self.assault_logged: str = ""               # last Training Ground (Assault) state logged
        self.score_logged: str = ""                 # last score multiplier patch state logged
        self.multipliers_on: bool = False           # either multiplier is in this game (slot data)
        self.starting_armour = game_state.StartingArmour()
        self.multiplier_logged: int = 1             # Behead The Undead multiplier last written to the log
        self.armour_logged: int = 0                 # starting armour level last written to the log
        self.buffs_shown: Optional[list] = None     # weapon buffs last shown in the Weapon Buffs tab
        self.buffs_skipped: list[str] = []          # weapon buffs last reported as not applied
        # Cheat traps: how many of the trap items received have already been run is kept in the
        # server's data storage, so a trap is never run twice (even after reconnecting).
        self.cheat_traps = game_state.CheatTraps()
        self.trap_duration: float = 30.0
        self.traps_applied: Optional[int] = None    # None until the server has told us
        self.last_poll: Optional[float] = None
        self.mission_failure = game_state.MissionFailure()
        self.death_pending: bool = False            # a Death Link has arrived and not been dealt with
        self.death_hook_logged: str = ""
        self.easier_trophies: dict[str, bool] = {}  # from slot_data
        self.easier_logged: dict[str, str] = {}
        self.death_waiting: bool = False             # a received death is waiting for a cutscene to end
        self.anaconda_checks: int = 0               # Temporal Uplink options (slot data)
        self.retroracer_checks: bool = False
        self.astrolander_checks: int = 0
        # Completed objectives are remembered until the server has them (and forgotten when a
        # different game is connected).
        self.objectives_found: set[int] = set()
        self.objectives_seed: Optional[str] = None
        self.final_level_logged: Optional[bool] = None    # last "Space Station open?" written to the log
        # From slot_data:
        self.goal: int = game_data.GOAL_SPACE_STATION
        self.story_mode: int = game_data.STORY_INDIVIDUAL
        self.story_levels_required: int = 0
        self.trophy_grade: int = 1
        self.trophies_required: int = 0
        self.trophies_required_grade: int = 1
        self.trophy_hunt_setting: int = game_data.HUNT_ALL

    def make_gui(self):
        """The normal client window (or Universal Tracker's), plus a Weapon Buffs tab."""
        base = super().make_gui()
        try:
            from . import gui
            return gui.make_gui(base)
        except Exception:
            logger.warning("Could not add the Weapon Buffs tab; the rest of the client is unaffected.")
            logger.debug(traceback.format_exc())
            return base

    def items_ready(self) -> bool:
        """
        True once it is safe to touch the game. The server only sends a
        ReceivedItems packet when we own at least one item, so a player with no
        items yet would wait forever. If none arrives within 3 seconds of
        logging in, we assume there are none.
        """
        if self.items_synced:
            return True
        return self.connected_at is not None and time.monotonic() - self.connected_at >= 3.0

    def reset_server_state(self) -> None:
        self.reported_locations = set()
        self.items_synced = False
        self.connected_at = None
        self.victory_sent = False
        self.multiplier_logged, self.armour_logged = 1, 0    # say the current levels again
        self.traps_applied = None
        super().reset_server_state()

    async def server_auth(self, password_requested: bool = False) -> None:
        if password_requested and not self.password:
            await super().server_auth(password_requested)
        await self.get_username()
        await self.send_connect()

    def on_deathlink(self, data: dict[str, Any]) -> None:
        super().on_deathlink(data)
        self.death_pending = True

    def on_package(self, cmd: str, args: dict[str, Any]) -> None:
        if cmd == "Connected":
            self.connected_at = time.monotonic()
            slot_data = args.get("slot_data", {})
            self.goal = int(slot_data.get("goal", game_data.GOAL_SPACE_STATION))
            self.story_mode = int(slot_data.get("story_mode", game_data.STORY_INDIVIDUAL))
            self.story_levels_required = int(slot_data.get("story_levels_required", 0))
            self.trophy_grade = int(slot_data.get("trophy_grade", 1))
            self.trophies_required = int(slot_data.get("trophies_required", 0))
            self.trophies_required_grade = int(slot_data.get("trophies_required_grade", 1))
            self.trophy_hunt_setting = int(slot_data.get("trophy_hunt_setting", game_data.HUNT_ALL))
            self.multipliers_on = bool(slot_data.get("behead_multiplier", 0))
            self.anaconda_checks = int(slot_data.get("anaconda_checks", 0))
            self.buffs_shown = None
            self.retroracer_checks = bool(slot_data.get("retroracer_checks", 0))
            self.astrolander_checks = int(slot_data.get("astrolander_checks", 0))
            self.easier_trophies = {option: bool(slot_data.get(option, 0)) for option in game_data.EASIER_TROPHIES}
            self.trap_duration = float(slot_data.get("trap_duration", 30))
            self.traps_applied = None
            Utils.async_start(self.update_death_link(bool(slot_data.get("death_link", 0))))
            Utils.async_start(self.send_msgs([{"cmd": "Get", "keys": [self.traps_key]}]))
            self.final_level_logged = None
            seed = f"{self.seed_name}/{self.slot}"
            if self.objectives_seed not in (None, seed):   # a different game: forget the old one's objectives
                self.objectives_found = set()
            self.objectives_seed = seed
            seed_version = str(slot_data.get("world_version", "unknown"))
            if seed_version == game_data.WORLD_VERSION:
                logger.info(f"This game was generated with apworld {seed_version}, the same as this client.")
            else:
                logger.warning(f"This game was generated with apworld {seed_version}, but this client is "
                               f"{game_data.WORLD_VERSION}.")
        elif cmd == "ReceivedItems":
            self.items_synced = True
        elif cmd == "Retrieved" and self.traps_key in args.get("keys", {}):
            self.traps_applied = int(args["keys"][self.traps_key] or 0)
        super().on_package(cmd, args)

    @property
    def traps_key(self) -> str:
        return f"ts2_traps_applied_{self.team}_{self.slot}"      # Universal Tracker listens to the same messages


TRAP_IDS = {game_data.ITEM_NAME_TO_ID[game_data.trap_item_name(name)]: (name, entry) for name, entry in game_data.TRAPS}


def run_traps(ctx: Ts2Context) -> None:
    """Queue newly received trap items, and let the running traps tick."""
    now = time.monotonic()
    elapsed = 0.0 if ctx.last_poll is None else min(now - ctx.last_poll, 1.0)
    ctx.last_poll = now
    if ctx.traps_applied is not None:
        traps = [item.item for item in ctx.items_received if item.item in TRAP_IDS]
        if len(traps) > ctx.traps_applied:
            for item_id in traps[ctx.traps_applied:]:
                name, entry = TRAP_IDS[item_id]
                ctx.cheat_traps.add(entry)
                logger.info(f"{name} Trap received: it starts as soon as you are playing a level.")
            ctx.traps_applied = len(traps)
            Utils.async_start(ctx.send_msgs([{"cmd": "Set", "key": ctx.traps_key, "default": 0, "want_reply": False,
                                              "operations": [{"operation": "replace", "value": ctx.traps_applied}]}]))
    names = {entry: name for name, entry in game_data.TRAPS}
    for event, entry in ctx.cheat_traps.poll(dolphin, ctx.trap_duration, elapsed):
        if event == "start":
            logger.info(f"{names[entry]} Trap! ({ctx.trap_duration:g} seconds)")
        else:
            logger.info(f"{names[entry]} Trap is over.")


def show_weapon_buffs(ctx: Ts2Context, item_list: list[int]) -> None:
    """Keep the Weapon Buffs tab showing the buffs received so far."""
    levels = game_state.weapon_buff_levels(item_list)
    if levels == ctx.buffs_shown:
        return
    ctx.buffs_shown = levels
    if ctx.ui and hasattr(ctx.ui, "update_weapon_buffs"):
        ctx.ui.update_weapon_buffs(levels)


async def death_link(ctx: Ts2Context) -> None:
    """Send a Death Link when a mission fails; fail the mission being played when one arrives."""
    failed = ctx.mission_failure.poll(dolphin)
    enabled = ctx.slot is not None and "DeathLink" in ctx.tags
    if not enabled:
        ctx.death_pending = ctx.death_waiting = False
        return
    state = game_state.ensure_death_hook(dolphin)
    if state != ctx.death_hook_logged:
        ctx.death_hook_logged = state
        if state == "busy":
            logger.error("Death Link can be sent but NOT received: the memory it needs is in use. Turn off "
                         "cheat codes in Dolphin (Config > General > Enable Cheats) and restart the game.")
        elif state == "unknown":
            logger.error("Death Link can be sent but NOT received: the game's data is not what the client expects.")
    if failed:
        name = ctx.player_names.get(ctx.slot, "A player")
        logger.info(f"You failed {failed}: Death Link sent.")
        await ctx.send_death(f"{name} failed {failed}.")
    if ctx.death_pending:
        if ctx.mission_failure.in_cutscene(dolphin):    # failing a level in a cutscene crashes the game
            if not ctx.death_waiting:
                ctx.death_waiting = True
                logger.info("Death Link received: it will land as soon as the cutscene is over.")
            return
        ctx.death_pending = ctx.death_waiting = False
        target = ctx.mission_failure.fail(dolphin)
        logger.info(f"Death Link received: {target} failed." if target
                    else "Death Link received, but you are not in a mission, so nothing happened.")


async def check_locations(ctx: Ts2Context, levels: dict[str, int]) -> None:
    found = (game_state.earned_location_ids(levels) | game_state.milestone_location_ids(levels)
             | game_state.story_location_ids(dolphin)
             | ctx.objectives_found)
    found &= set(ctx.server_locations)       # only locations that exist in this seed
    new = found - set(ctx.checked_locations) - ctx.reported_locations
    if new:
        ctx.reported_locations |= new
        await ctx.send_msgs([{"cmd": "LocationChecks", "locations": sorted(new)}])
    if ctx.goal == game_data.GOAL_ALL_TROPHIES:
        goal = game_state.trophy_goal_reached(levels, ctx.trophy_grade, ctx.trophy_hunt_setting)
    else:
        goal = game_state.story_goal_reached(dolphin)
    if not ctx.victory_sent and goal:
        await ctx.send_msgs([{"cmd": "StatusUpdate", "status": ClientStatus.CLIENT_GOAL}])
        ctx.victory_sent = True


def log_lock_state(ctx: Ts2Context, state: str) -> None:
    """Say what the mission lock is doing, once, when it changes."""
    if state == ctx.lock_logged:
        return
    ctx.lock_logged = state
    if state == "installed":
        logger.info("Mission lock installed. Missions, characters, cheats, maps, game modes and weapons are now controlled by your items.")
    elif state == "busy":
        logger.error("Missions are NOT locked: the memory the client needs is in use. Turn off Gecko/cheat "
                     "codes in Dolphin (Config > General > Enable Cheats) and restart the game.")
    elif state == "unknown":
        logger.error("Missions are NOT locked: the game's data is not what the client expects "
                     "(trophy checks still work).")


def story_mask_for(ctx: Ts2Context) -> int:
    """Which story levels are open right now: your items, plus the 2401 Space Station requirements."""
    final_open = True
    if ctx.goal == game_data.GOAL_SPACE_STATION and (ctx.story_levels_required or ctx.trophies_required):
        levels_ok = game_state.story_levels_beaten(dolphin) >= ctx.story_levels_required
        trophies = game_state.trophies_at_grade(game_state.read_trophy_levels(dolphin), ctx.trophies_required_grade)
        trophies_ok = trophies >= ctx.trophies_required
        final_open = levels_ok and trophies_ok
        if final_open != ctx.final_level_logged:
            ctx.final_level_logged = final_open
            name = game_data.STORY_LEVELS[game_data.FINAL_STORY_LEVEL]
            needs = []
            if ctx.story_levels_required:
                needs.append(f"{ctx.story_levels_required} other story levels beaten")
            if ctx.trophies_required:
                grade = game_data.TIERS[ctx.trophies_required_grade - 1]
                needs.append(f"{ctx.trophies_required} Arcade League missions or Challenges with {grade} or better")
            if final_open:
                logger.info(f"Requirements met: {name} opens once you have it.")
            else:
                logger.info(f"{name} needs " + " and ".join(needs) + ".")
    received = [item.item for item in ctx.items_received]
    return game_state.story_mask(received, final_open, ctx.story_mode == game_data.STORY_PROGRESSIVE)


def log_story_state(ctx: Ts2Context, state: str) -> None:
    """Say what the story lock is doing, once, when it changes."""
    if state == ctx.story_logged:
        return
    ctx.story_logged = state
    if state == "installed":
        logger.info("Story lock installed. Story levels are now controlled by your items.")
    elif state == "busy":
        logger.error("Story levels are NOT locked: the memory the client needs is in use. Turn off Gecko/cheat "
                     "codes in Dolphin (Config > General > Enable Cheats) and restart the game.")
    elif state == "unknown":
        logger.error("Story levels are NOT locked: the game's code is not what the client expects "
                     "(story checks still work).")


async def dolphin_sync_task(ctx: Ts2Context) -> None:
    logger.info("Starting Dolphin connector.")
    while not ctx.exit_event.is_set():
        try:
            if dolphin.is_hooked() and ctx.dolphin_status == CONNECTED:
                # Watch objectives even while the server connection is down; they are sent as
                # soon as it is back.
                if ctx.data_ok:
                    ctx.objectives_found |= game_state.completed_objective_ids(dolphin)
                    # A cartridge reads 1 only until the client next sets it to 0 or 2, so it is
                    # noted here, before that happens, and remembered like the objectives.
                    ctx.objectives_found |= game_state.found_cartridge_ids(dolphin)
                    ctx.objectives_found |= game_state.uplink_location_ids(
                        dolphin, ctx.anaconda_checks, ctx.retroracer_checks, ctx.astrolander_checks)
                await death_link(ctx)
                # Only act once we are logged in AND our item list has had time to
                # arrive, otherwise we'd briefly relock things the player really owns.
                if ctx.slot is not None and ctx.items_ready():
                    easier = game_state.enforce_easier_trophies(dolphin, ctx.easier_trophies)
                    if easier != ctx.easier_logged:
                        for option, state in easier.items():
                            if state == ctx.easier_logged.get(option):
                                continue
                            name = game_data.EASIER_TROPHY_NAMES[option]
                            if state == "easier":
                                logger.info(f"{name}: easier trophy requirements are active.")
                            elif state == "unknown" and ctx.easier_trophies.get(option):
                                logger.error(f"{name}: easier trophy requirements are NOT active (the game's "
                                             "values are not what the client expects).")
                        ctx.easier_logged = easier
                    levels = game_state.read_trophy_levels(dolphin)
                    if levels is not None:               # None = no profile loaded yet
                        await check_locations(ctx, levels)
                    if ctx.data_ok:
                        received = {item.item for item in ctx.items_received}
                        run_traps(ctx)
                        # A running trap unlocks its cheat for as long as it lasts.
                        trap_cheats = {game_data.ITEM_NAME_TO_ID[game_data.cheat_item_name(name)]
                                       for name, entry in game_data.TRAPS
                                       if entry in ctx.cheat_traps.unlocked_entries()}
                        game_state.enforce_unlocks(dolphin, received | trap_cheats)
                        game_state.enforce_default_characters(dolphin, received)
                        log_lock_state(ctx, game_state.enforce_missions(dolphin, received))
                        log_story_state(ctx, game_state.enforce_story(dolphin, story_mask_for(ctx)))
                        if ctx.multipliers_on:
                            item_list = [item.item for item in ctx.items_received]
                            factors = {name: game_state.multiplier_level(item_list, name)
                                       for name in game_data.MULTIPLIER_ITEM_NAMES}
                            score = game_state.enforce_score_multipliers(dolphin, factors)
                            if score != ctx.score_logged:      # said once, when it changes
                                ctx.score_logged = score
                                if score in ("busy", "unknown"):
                                    logger.warning(f"The Behead The Undead score multiplier could not be set up ({score}); "
                                                   "points stay normal. Make sure Dolphin's cheats are off.")
                            multiplier = factors[game_data.BEHEAD_MULTIPLIER_ITEM_NAME]
                            if multiplier != ctx.multiplier_logged and score == "installed":
                                ctx.multiplier_logged = multiplier
                                logger.info(f"Behead The Undead points are now x{multiplier}.")
                        armour_level = game_state.starting_armour_level([item.item for item in ctx.items_received])
                        if armour_level != ctx.armour_logged:  # said once, when the amount changes
                            ctx.armour_logged = armour_level
                            if armour_level:
                                logger.info(f"Starting armour is now {armour_level * 25}% "
                                            f"({armour_level} of {game_data.STARTING_ARMOUR_COPIES}).")
                        given = ctx.starting_armour.poll(dolphin, armour_level)
                        if given is not None:
                            logger.debug(f"Starting armour: {given:g}")
                        game_state.enforce_cartridges(dolphin, received)
                        item_list = [item.item for item in ctx.items_received]
                        skipped = game_state.enforce_weapon_buffs(dolphin, item_list)
                        if skipped != ctx.buffs_skipped:
                            ctx.buffs_skipped = skipped
                            if skipped:
                                logger.warning("These weapon buffs are NOT applied because the game's value is not "
                                               "one the client recognises (restart the game to reset it): "
                                               + ", ".join(skipped))
                        show_weapon_buffs(ctx, item_list)
                        assault = game_state.enforce_training_ground(dolphin, received)
                        if assault != ctx.assault_logged:      # said once, when it changes
                            ctx.assault_logged = assault
                            if assault in ("busy", "unknown"):
                                logger.warning("Training Ground's Assault version could not be locked "
                                               f"({assault}); it stays available.")
                await asyncio.sleep(0.25)
            else:
                if ctx.dolphin_status == CONNECTED:
                    logger.warning(LOST)
                    ctx.dolphin_status = LOST
                logger.info("Attempting to connect to Dolphin...")
                dolphin.hook()
                if dolphin.is_hooked():
                    game_id = dolphin.read_bytes(game_data.GAME_ID_ADDRESS, 6)
                    if game_data.GAME_ID is not None and game_id != game_data.GAME_ID:
                        logger.info(f"{WRONG_GAME} (found {game_id!r})")
                        ctx.dolphin_status = WRONG_GAME
                        dolphin.un_hook()
                        await asyncio.sleep(5)
                    else:
                        logger.info(f"{CONNECTED} Game ID: {game_id!r}")
                        problems = game_state.check_game_data(dolphin)
                        ctx.data_ok = not problems
                        ctx.lock_logged = ""
                        ctx.story_logged = ""
                        ctx.score_logged = ""
                        ctx.death_hook_logged = ""
                        ctx.easier_logged = {}
                        if problems:
                            logger.error("Unlock data does not look right, so nothing will be locked or "
                                         "unlocked (checks still work). First problems: " + "; ".join(problems[:3]))
                        else:
                            # Lock everything straight away; what you own opens once the server
                            # has sent your items.
                            game_state.enforce_unlocks(dolphin, set())
                            log_lock_state(ctx, game_state.enforce_missions(dolphin, set()))
                            log_story_state(ctx, game_state.enforce_story(dolphin, 0))
                        ctx.dolphin_status = CONNECTED
                else:
                    logger.info("Dolphin not found, trying again in 5 seconds...")
                    ctx.dolphin_status = LOST
                    await asyncio.sleep(5)
        except Exception:
            dolphin.un_hook()
            logger.warning("Lost connection to Dolphin or hit an error; retrying in 5 seconds.")
            logger.debug(traceback.format_exc())
            ctx.dolphin_status = LOST
            await asyncio.sleep(5)


def main(*args) -> None:
    Utils.init_logging("TimeSplitters 2 Client")

    async def _main(connect: Optional[str], password: Optional[str]) -> None:
        ctx = Ts2Context(connect, password)
        ctx.server_task = asyncio.create_task(server_loop(ctx), name="ServerLoop")
        if tracker_loaded:
            ctx.run_generator()            # Universal Tracker's own copy of the world, for logic
            ctx.tags.remove("Tracker")     # this is a real game client, not a tracker-only one
        if gui_enabled:
            ctx.run_gui()
        ctx.run_cli()
        await asyncio.sleep(1)

        ctx.dolphin_sync_task = asyncio.create_task(dolphin_sync_task(ctx), name="DolphinSync")
        await ctx.exit_event.wait()
        ctx.server_address = None
        await ctx.shutdown()
        if ctx.dolphin_sync_task:
            await asyncio.sleep(3)
            await ctx.dolphin_sync_task

    parser = get_base_parser(description="TimeSplitters 2 Client.")
    parser.add_argument("--name", default=None, help="Slot name to connect as.")
    parser.add_argument("url", nargs="?", help="Archipelago connection url")
    parsed = parser.parse_args(args)

    from CommonClient import handle_url_arg
    parsed = handle_url_arg(parsed, parser=parser)

    import colorama
    colorama.init()
    asyncio.run(_main(parsed.connect, parsed.password))
    colorama.deinit()


if __name__ == "__main__":
    main()
