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
from CommonClient import ClientCommandProcessor, get_base_parser, gui_enabled, logger, server_loop
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

ANNOUNCE_SETTINGS = ("received", "sent", "found", "deathlink", "traps", "filler")
ANNOUNCE_DEFAULTS = {"on": True, **{name: True for name in ANNOUNCE_SETTINGS}}
SETTINGS_KEY = "timesplitters_2"


class Ts2CommandProcessor(getattr(CommonContext, "command_processor", ClientCommandProcessor)):
    def _cmd_announce(self, setting: str = "", value: str = "") -> bool:
        """In-game announcements. /announce shows the settings. /announce on or /announce off switches
        them all. /announce received|sent|found|deathlink|traps|filler on|off switches one
        kind (traps: a trap's name in big text when it starts; filler: announcements of filler items)."""
        ctx = self.ctx
        setting, value = setting.lower(), value.lower()
        if setting in ("on", "off") and not value:
            setting, value = "on", setting
        if setting and (setting not in ("on",) + ANNOUNCE_SETTINGS or value not in ("on", "off")):
            self.output("Use /announce on|off, or /announce received|sent|found|deathlink|traps|filler on|off.")
            return False
        if setting:
            ctx.announce[setting] = value == "on"
            try:
                Utils.persistent_store(SETTINGS_KEY, "announce", dict(ctx.announce))
            except Exception:
                pass
        self.output("In-game announcements: " + ("ON" if ctx.announce["on"] else "OFF") + " ("
                    + ", ".join(f"{name} {'on' if ctx.announce[name] else 'off'}" for name in ANNOUNCE_SETTINGS)
                    + ")")
        return True


class Ts2Context(CommonContext):
    game = game_data.GAME_NAME
    items_handling = 0b111  # the server sends us every item, including our own
    command_processor = Ts2CommandProcessor

    def __init__(self, server_address: Optional[str], password: Optional[str]) -> None:
        super().__init__(server_address, password)
        self.dolphin_status: str = NOT_CONNECTED
        self.announcer = game_state.Announcer()
        self.announce: dict[str, bool] = dict(ANNOUNCE_DEFAULTS)
        try:
            saved = Utils.persistent_load().get(SETTINGS_KEY, {}).get("announce", {})
            self.announce.update({k: bool(v) for k, v in saved.items() if k in ANNOUNCE_DEFAULTS})
        except Exception:
            pass
        self.frame_hook_logged: str = ""
        self.award_screen = game_state.AwardScreen()
        self.award_hook_logged: str = ""
        self.award_items_seen: Optional[int] = None         # items_received already looked at
        self.last_played = None                             # ("mission", Mission) / ("story", level)
        self.arcade_deaths = game_state.ArcadeDeaths()
        self.death_link_amnesty: int = 0                    # 0 = Arcade League deaths don't count
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
        self.resistances_on: bool = False           # damage resistances are in this game (slot data)
        self.skip_easy_objectives: bool = False     # Easy-only objectives checked by Normal/Hard (slot data)
        # Archipelago Shop (slot data, and the server's data storage for kills and points spent)
        self.shop_size: int = 0
        self.shop_prices: list[int] = []
        self.shop_kills: Optional[int] = None       # None until the server has told us
        self.shop_spent: Optional[int] = None
        self.shop_kills_pending: int = 0            # kills not yet added on the server
        self.shop_bought: set[int] = set()          # bought here, perhaps not yet confirmed by the server
        self.shop_hinted: set[int] = set()
        self.shop_award_hidden: set[int] = set()    # own items bought in the shop: kept off the award screen
        self.shop_hints: int = game_data.SHOP_HINTS_PROGRESSION
        self.shop_hint_rows: set[int] = set()       # rows to hint once their item is what they show
        self.shop_menu = game_state.ShopMenu()
        self.kill_counter = game_state.KillCounter()
        self.shop_state_logged: str = ""
        self.shop_earned: dict[str, int] = {"trophies": 0, "story": 0}   # last read from the profile
        self.resistance_state_logged: str = ""      # last damage resistance hook state logged
        self.resistance_logged: dict = {}           # resistance levels last written to the log
        self.starting_armour = game_state.StartingArmour()
        self.multiplier_logged: int = 1             # Behead The Undead multiplier last written to the log
        self.armour_logged: int = 0                 # starting armour level last written to the log
        self.buffs_shown: Optional[str] = None      # what the Inventory tab last showed
        self.shop_list: tuple = (None, [])          # the shop's points and rows, for the Inventory tab
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
        """The normal client window (or Universal Tracker's), plus an Inventory tab."""
        base = super().make_gui()
        try:
            from . import gui
            return gui.make_gui(base)
        except Exception:
            logger.warning("Could not add the Inventory tab; the rest of the client is unaffected.")
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
        self.resistance_logged = {}
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
        if self.announce["on"] and self.announce["deathlink"]:
            cause = str(data.get("cause") or "") or f"Death Link from {data.get('source', 'someone')}"
            self.announcer.add(cause, game_data.MESSAGE_STYLE_BIG)

    def announce_item_send(self, args: dict[str, Any]) -> None:
        """Queue an in-game line for an item that concerns us (received, sent or found)."""
        if not self.announce["on"] or self.slot is None:
            return
        item, receiving = args.get("item"), args.get("receiving")
        if item is None or receiving is None:
            return
        if isinstance(item, dict):
            item_id, sender, flags = item.get("item"), item.get("player"), item.get("flags", 0)
        else:
            item_id, sender, flags = item.item, item.player, item.flags
        if not flags and not self.announce["filler"]:
            return
        try:
            name = self.item_names.lookup_in_slot(item_id, receiving)
        except Exception:
            name = f"item {item_id}"
        players = self.player_names
        if receiving == self.slot and sender == self.slot:
            kind, text = "found", f"Found {name}"
        elif receiving == self.slot:
            kind, text = "received", f"Received {name} from {players.get(sender, 'someone')}"
        elif sender == self.slot:
            kind, text = "sent", f"Sent {name} to {players.get(receiving, 'someone')}"
        else:
            return
        if self.announce[kind]:
            self.announcer.add(text, game_data.MESSAGE_STYLE_LINE)

    def on_package(self, cmd: str, args: dict[str, Any]) -> None:
        if cmd == "Connected":
            self.connected_at = time.monotonic()
            self.award_items_seen = None       # items already received are not news
            slot_data = args.get("slot_data", {})
            self.goal = int(slot_data.get("goal", game_data.GOAL_SPACE_STATION))
            self.story_mode = int(slot_data.get("story_mode", game_data.STORY_INDIVIDUAL))
            self.story_levels_required = int(slot_data.get("story_levels_required", 0))
            self.trophy_grade = int(slot_data.get("trophy_grade", 1))
            self.trophies_required = int(slot_data.get("trophies_required", 0))
            self.trophies_required_grade = int(slot_data.get("trophies_required_grade", 1))
            self.trophy_hunt_setting = int(slot_data.get("trophy_hunt_setting", game_data.HUNT_ALL))
            self.multipliers_on = bool(slot_data.get("behead_multiplier", 0))
            self.resistances_on = bool(slot_data.get("include_damage_resistances", 0))
            self.skip_easy_objectives = bool(slot_data.get("skip_easy_objectives", 0))
            self.shop_size = int(slot_data.get("shop_locations", 0)) if slot_data.get("include_archipelago_shop") else 0
            self.shop_prices = list(slot_data.get("shop_prices", []))
            self.shop_hints = int(slot_data.get("shop_hints", game_data.SHOP_HINTS_ALL))
            self.shop_kills = self.shop_spent = None
            self.shop_hinted = set()
            if self.shop_size:
                Utils.async_start(self.send_msgs([{"cmd": "Get", "keys": [self.shop_kills_key, self.shop_spent_key]}]))
            self.anaconda_checks = int(slot_data.get("anaconda_checks", 0))
            self.buffs_shown = None
            self.retroracer_checks = bool(slot_data.get("retroracer_checks", 0))
            self.astrolander_checks = int(slot_data.get("astrolander_checks", 0))
            self.easier_trophies = {option: bool(slot_data.get(option, 0)) for option in game_data.EASIER_TROPHIES}
            self.trap_duration = float(slot_data.get("trap_duration", 30))
            self.traps_applied = None
            Utils.async_start(self.update_death_link(bool(slot_data.get("death_link", 0))))
            self.death_link_amnesty = int(slot_data.get("death_link_amnesty", 0))   # 0: seeds before 1.1.0
            logger.info("In-game announcements are " + ("on" if self.announce["on"] else "off")
                        + ". Type /announce to see or change them.")
            # What is at each of our locations, so the award screen can name what was just found.
            missing = sorted(args.get("missing_locations", []))
            if missing:
                Utils.async_start(self.send_msgs([{"cmd": "LocationScouts", "locations": missing,
                                                   "create_as_hint": 0}]))
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
        elif cmd == "PrintJSON" and args.get("type") in ("ItemSend", "ItemCheat"):
            self.announce_item_send(args)
        elif cmd == "Retrieved":
            keys = args.get("keys", {})
            if self.traps_key in keys:
                self.traps_applied = int(keys[self.traps_key] or 0)
            if self.shop_kills_key in keys:
                self.shop_kills = int(keys[self.shop_kills_key] or 0)
            if self.shop_spent_key in keys:
                self.shop_spent = int(keys[self.shop_spent_key] or 0)
        super().on_package(cmd, args)

    @property
    def shop_kills_key(self) -> str:
        return f"ts2_shop_kills_{self.team}_{self.slot}"

    @property
    def shop_spent_key(self) -> str:
        return f"ts2_shop_spent_{self.team}_{self.slot}"

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
            if ctx.announce["on"] and ctx.announce["traps"]:
                ctx.announcer.add(game_data.trap_item_name(names[entry]).upper(), game_data.MESSAGE_STYLE_BIG)
        else:
            logger.info(f"{names[entry]} Trap is over.")


def show_weapon_buffs(ctx: Ts2Context, item_list: list[int]) -> None:
    """Keep the Inventory tab showing the shop's points and rows, the damage resistances and the
    weapon buffs received so far."""
    from . import gui
    shop = ctx.shop_list if ctx.shop_size else None
    resistances = [(group, have, game_data.RESISTANCE_COPIES, round(have * game_data.RESISTANCE_STEP * 100))
                   for group, have in game_state.resistance_levels(item_list).items() if have]
    buffs = []
    for weapon, stat, _addresses, normal, change, copies, _always in sorted(game_data.WEAPON_BUFFS):
        have = min(item_list.count(game_data.ITEM_NAME_TO_ID[game_data.weapon_buff_item_name(weapon, stat, change)]),
                   copies)
        if have:
            buffs.append((weapon, stat, round(change * have * 100), normal,
                          game_data.weapon_buff_value(normal, change, have), have, copies))
    multipliers = []
    for name, display in game_data.AWARD_MULTIPLIER_NAMES.items():
        have = min(item_list.count(game_data.ITEM_NAME_TO_ID[name]), game_data.MULTIPLIER_COPIES)
        if have:
            multipliers.append((display, game_state.multiplier_level(item_list, name), have,
                                game_data.MULTIPLIER_COPIES))
    other = []
    armour = game_state.starting_armour_level(item_list)
    if armour:
        other.append(("Starting Armour", armour * 100 // game_data.STARTING_ARMOUR_COPIES, armour,
                      game_data.STARTING_ARMOUR_COPIES))
    text = gui.inventory_text(shop, resistances, buffs, multipliers, other)
    if text == ctx.buffs_shown:
        return
    ctx.buffs_shown = text
    if ctx.ui and hasattr(ctx.ui, "update_inventory"):
        ctx.ui.update_inventory(text)


_SHOP_RESTOCK_ID = game_data.ITEM_NAME_TO_ID[game_data.SHOP_RESTOCK_ITEM_NAME]
_TROPHY_FILLER_POINTS = {game_data.ITEM_NAME_TO_ID[name]: points
                         for name, points in game_data.TROPHY_FILLER_POINTS.items()}


def shop_points(ctx: Ts2Context) -> Optional[int]:
    """Points to spend, or None until the server has said how many were earned by kills and spent."""
    if ctx.shop_kills is None or ctx.shop_spent is None:
        return None
    filler = sum(_TROPHY_FILLER_POINTS.get(item.item, 0) for item in ctx.items_received)
    return (ctx.shop_earned["trophies"] + ctx.shop_earned["story"] + ctx.shop_kills + ctx.shop_kills_pending
            + filler - ctx.shop_spent)


_SHORT_NAME_GAMES = (game_data.GAME_NAME, game_data.TSFP_GAME_NAME)


def short_item_name(name: str, game: Optional[str]) -> str:
    """An item of TimeSplitters 2 or TimeSplitters: Future Perfect as the shop and award screen show
    it; other games' items as they are."""
    if game == game_data.GAME_NAME:
        return shop_display_name(name)
    if game == game_data.TSFP_GAME_NAME:
        return game_data.tsfp_short_item_name(name)
    return name


def _game_of(ctx, player: int) -> Optional[str]:
    if player == ctx.slot:
        return game_data.GAME_NAME
    return getattr(getattr(ctx, "slot_info", {}).get(player), "game", None)


def shop_display_name(name: str) -> str:
    """A TimeSplitters 2 item as the shop shows it, as on the award screen: a mission or story level
    by its own name, a weapon buff as "<weapon> <buff>" (e.g. "Pistols +25% Reserve Ammo")."""
    if name in _MISSIONS_BY_ITEM:
        return _MISSIONS_BY_ITEM[name].name
    if name in game_data.STORY_ITEM_NAMES:
        return game_data.STORY_LEVELS[game_data.STORY_ITEM_NAMES.index(name)]
    if name in _CARTRIDGES_BY_ITEM:
        return f"{_CARTRIDGES_BY_ITEM[name]} Cartridge"
    if name in game_data.WEAPON_BUFF_ITEM_NAMES:
        return name.removeprefix("Weapon Buff - ").replace(" - ", " ")
    return name


def _shop_item_text(ctx: Ts2Context, location: int, price: int) -> Optional[str]:
    info = ctx.locations_info.get(location)
    if info is None:
        return None
    try:
        name = ctx.item_names.lookup_in_slot(info.item, info.player)
    except Exception:
        name = "Unknown item"
    name = short_item_name(name, _game_of(ctx, info.player))
    owner = "You" if info.player == ctx.slot else ctx.player_names.get(info.player, "Someone")
    return f"{name} ({owner}) - {price} Points"


def shop_rows(ctx: Ts2Context, points: Optional[int]) -> tuple[list, list]:
    """What each row shows, what buying it switches it to and whether it can be bought now, and
    the location each row is selling (None when it shows "Purchased")."""
    size = ctx.shop_size
    total = size // game_data.SHOP_ROWS
    restocks = sum(1 for item in ctx.items_received if item.item == _SHOP_RESTOCK_ID)
    batches = min(restocks + 1, total)
    done = set(ctx.checked_locations) | ctx.shop_bought
    rows, selling = [], []
    for k in range(game_data.SHOP_ROWS):
        def location(batch: int) -> int:
            return game_data.shop_location_id(batch * game_data.SHOP_ROWS + k)

        def price(batch: int) -> int:
            index = batch * game_data.SHOP_ROWS + k
            return ctx.shop_prices[index] if index < len(ctx.shop_prices) else 0

        def text(batch: int) -> str:
            if batch >= batches:
                return "Purchased"
            return _shop_item_text(ctx, location(batch), price(batch)) or "Loading..."

        c = 0
        while c < total and location(c) in done:
            c += 1
        can_buy = (c < batches and points is not None and price(c) <= points and ctx.server is not None
                   and location(c) in ctx.locations_info)
        rows.append((text(c), text(c + 1), can_buy))
        selling.append(location(c) if c < batches else None)
    return rows, selling


async def run_shop(ctx: Ts2Context, levels: Optional[dict[str, int]]) -> None:
    """Count kills, keep the shop menu up to date and handle what is bought there."""
    new = ctx.kill_counter.poll(dolphin)
    if new:
        ctx.shop_kills_pending += new
    if ctx.shop_kills_pending and ctx.shop_kills is not None and ctx.server is not None:
        added, ctx.shop_kills_pending = ctx.shop_kills_pending, 0
        ctx.shop_kills += added
        await ctx.send_msgs([{"cmd": "Set", "key": ctx.shop_kills_key, "default": 0, "want_reply": False,
                              "operations": [{"operation": "add", "value": added}]}])
    if levels is not None:
        ctx.shop_earned["trophies"] = game_state.trophy_points(levels)
    story = game_state.story_points(dolphin)
    if story is not None:
        ctx.shop_earned["story"] = story
    state = ctx.shop_menu.install(dolphin)
    if state != ctx.shop_state_logged:
        ctx.shop_state_logged = state
        if state == "installed":
            logger.info("The Archipelago Shop is in Options & Shop > Archipelago Shop (the old View Cutscenes).")
        elif state == "busy":
            logger.error("The Archipelago Shop is NOT available: the memory it needs is in use. Turn off cheat "
                         "codes in Dolphin (Config > General > Enable Cheats) and restart the game.")
        elif state == "unknown":
            logger.error("The Archipelago Shop is NOT available: the game's code is not what the client expects.")
    if state != "installed":
        return
    points = shop_points(ctx)
    title = "Archipelago Shop - connecting..." if points is None else f"Archipelago Shop - {points} Points"
    rows, selling = shop_rows(ctx, points)
    ctx.shop_list = (points, [now for now, _after, _can_buy in rows])
    # Seeing an item in the shop sends a hint for it: the rows shown when the shop is opened, and a
    # row's next item once buying it brings that up.
    if ctx.server is not None and ctx.shop_hint_rows:
        unhinted = sorted({selling[k] for k in ctx.shop_hint_rows} - {None} - ctx.shop_hinted
                          - set(ctx.checked_locations))
        ctx.shop_hint_rows = set()
        if ctx.shop_hints == game_data.SHOP_HINTS_NONE:
            unhinted = []
        elif ctx.shop_hints == game_data.SHOP_HINTS_PROGRESSION:
            unhinted = [location for location in unhinted
                        if ctx.locations_info.get(location) is not None and ctx.locations_info[location].flags & 0b001]
        if unhinted:
            ctx.shop_hinted.update(unhinted)
            await ctx.send_msgs([{"cmd": "LocationScouts", "locations": unhinted, "create_as_hint": 2}])
    picks = ctx.shop_menu.update(dolphin, title, rows)
    if ctx.shop_menu.just_opened:
        ctx.shop_hint_rows = set(range(game_data.SHOP_ROWS))
    for k, bought in picks:
        location = selling[k]
        if location is None:
            continue
        index = location - game_data.shop_location_id(0)
        price = ctx.shop_prices[index] if index < len(ctx.shop_prices) else 0
        if not bought:
            continue
        ctx.shop_bought.add(location)
        ctx.shop_hint_rows.add(k)                  # its next item, if a restock has brought one
        ctx.shop_spent = (ctx.shop_spent or 0) + price
        # Bought in the shop: never on the award screen (the game's own list included).
        info = ctx.locations_info.get(location)
        if info is not None and info.player == ctx.slot:
            ctx.shop_award_hidden.add(info.item)
        await ctx.send_msgs([{"cmd": "Set", "key": ctx.shop_spent_key, "default": 0, "want_reply": False,
                              "operations": [{"operation": "add", "value": price}]},
                             {"cmd": "LocationChecks", "locations": [location]}])


def frame_hook(ctx: Ts2Context) -> bool:
    """Install the once-a-frame hook (announcements and receiving Death Links); True when ready."""
    state = game_state.ensure_frame_hook(dolphin)
    if state != ctx.frame_hook_logged:
        ctx.frame_hook_logged = state
        if state == "busy":
            logger.error("In-game announcements and receiving Death Links are NOT available: the memory they "
                         "need is in use. Turn off cheat codes in Dolphin (Config > General > Enable Cheats) "
                         "and restart the game.")
        elif state == "unknown":
            logger.error("In-game announcements and receiving Death Links are NOT available: the game's data "
                         "is not what the client expects.")
    return state == "ready"


def enforce_resistances(ctx: Ts2Context, item_list: list[int], hook_ready: bool) -> None:
    """Keep the damage resistance numbers in step with the items, and say when they change."""
    levels = game_state.resistance_levels(item_list)
    state = game_state.enforce_resistances(dolphin, levels, hook_ready)
    if state != ctx.resistance_state_logged:
        ctx.resistance_state_logged = state
        if state == "busy":
            logger.error("Damage resistances are NOT applied: the memory they need is in use. Turn off cheat "
                         "codes in Dolphin (Config > General > Enable Cheats) and restart the game.")
        elif state == "unknown":
            logger.error("Damage resistances are NOT applied: the game's code is not what the client expects.")


async def death_link(ctx: Ts2Context, hook_ready: bool) -> None:
    """Send a Death Link when a mission fails (or after enough Arcade League deaths); fail the
    mission being played when one arrives."""
    failed = ctx.mission_failure.poll(dolphin)
    died = ctx.arcade_deaths.poll(dolphin)
    if ctx.death_link_amnesty <= 0 or ctx.mission_failure.caused or ctx.mission_failure.waiting:
        died = None                     # off for this seed, or the death came from a Death Link we received
    enabled = ctx.slot is not None and "DeathLink" in ctx.tags
    if not enabled:
        ctx.death_pending = ctx.death_waiting = False
        return
    if died and not failed and died[1] % ctx.death_link_amnesty == 0:
        mission, deaths = died
        name = ctx.player_names.get(ctx.slot, "A player")
        if ctx.death_link_amnesty == 1:
            logger.info(f"You died in {mission}: Death Link sent.")
            await ctx.send_death(f"{name} died in {mission}.")
        else:
            logger.info(f"You died {deaths} times in {mission}: Death Link sent.")
            await ctx.send_death(f"{name} died {deaths} times in {mission}.")
    elif died:
        left = ctx.death_link_amnesty - died[1] % ctx.death_link_amnesty
        logger.info(f"You died in {died[0]}: {left} more death{'s' if left != 1 else ''} until a Death Link is sent.")
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
        target = ctx.mission_failure.fail(dolphin) if hook_ready else None
        if target is None:
            logger.info("Death Link received, but you are not in a mission, so nothing happened.")
        elif target[0] == "killed":
            logger.info(f"Death Link received: you died in {target[1]}.")
        else:
            logger.info(f"Death Link received: {target[1]} failed.")


_ITEM_ID_TO_NAME = {code: name for name, code in game_data.ITEM_NAME_TO_ID.items()}
_MISSIONS_BY_ITEM = {m.item_name: m for m in game_data.MISSIONS}
# Weapon buffs: (weapon, stat, change per copy, copies), shown as "<stat> Buff found!" / "<weapon> +50%".
_BUFFS_BY_ITEM = {game_data.weapon_buff_item_name(b[0], b[1], b[4]): (b[0], b[1], b[4], b[5])
                  for b in game_data.WEAPON_BUFFS}
# Weapons the game itself lists on the award screen when they unlock: only the Brick.
_NATIVE_WEAPONS = {game_data.weapon_item_name("Brick")}
_WEAPONS_BY_ITEM = {game_data.weapon_item_name(w[0]): w[3] for w in game_data.WEAPON_ENTRIES
                    if game_data.weapon_item_name(w[0]) not in _NATIVE_WEAPONS}
# Items the game lists itself once they unlock (and filler, which isn't listed at all).
_NATIVE_AWARDS = (set(game_data.CHARACTER_ITEM_NAMES) | set(game_data.CHEAT_ITEM_NAMES)
                  | set(game_data.HAT_ITEM_NAMES) | set(game_data.MAP_ITEM_NAMES)
                  | set(game_data.MODE_ITEM_NAMES) | _NATIVE_WEAPONS | {game_data.FILLER_ITEM_NAME}
                  | set(game_data.TRAP_ITEM_NAMES))       # traps: not listed at all

# Where each kind of entry goes on the award screen. The game's own entries (characters, cheats,
# maps, ...) come between the two groups.
_FRONT, _BACK = 0, 1
_STORY, _MISSION, _CHALLENGE, _CARTRIDGE = 0, 1, 2, 3   # order within the front group
_CARTRIDGES_BY_ITEM = {game_data.cartridge_item_name(c[0]): c[0] for c in game_data.CARTRIDGES}
_WEAPON, _MULTIPLIER, _ITEM, _RESISTANCE, _BUFF, _OTHER_PLAYER = 0, 1, 2, 3, 4, 5  # order within the back group
_RESISTANCES_BY_ITEM = {game_data.resistance_item_name(group): group for group, _types in game_data.RESISTANCES}


def _resistance_line(name: str, count: int):
    level = min(max(count, 1), game_data.RESISTANCE_COPIES)
    return (game_data.AWARD_RESISTANCE,
            f"{_RESISTANCES_BY_ITEM[name]} Damage {round(level * game_data.RESISTANCE_STEP * 100)}%")


def _story_line(ctx: Ts2Context, count: int):
    level = min(max(count - 1, 0), len(game_data.STORY_LEVELS) - 1)
    if ctx.last_played == ("story", level):
        return None                         # you have just played it, so you know you have it
    return game_data.AWARD_STORY, game_data.STORY_LEVELS[level]


def _multiplier_line(name: str, count: int):
    factor = 1 + min(max(count, 1), game_data.MULTIPLIER_COPIES)
    return game_data.AWARD_MULTIPLIER, f"{game_data.AWARD_MULTIPLIER_NAMES[name]} x{factor}"


def _armour_line(count: int):
    level = min(max(count, 1), game_data.STARTING_ARMOUR_COPIES)
    return game_data.AWARD_ITEM, f"{level * 100 // game_data.STARTING_ARMOUR_COPIES}% Starting Armour"


def _buff_line(name: str, count: int):
    weapon, stat, change, copies = _BUFFS_BY_ITEM[name]
    total = round(change * 100 * min(max(count, 1), copies))
    return game_data.AWARD_BUFF.format(stat=stat), f"{weapon} +{total}%"


def _other_player_rank(flags: int) -> int:
    """Progression, then useful, then traps, then filler."""
    if flags & 0b001:
        return 0
    if flags & 0b010:
        return 1
    if flags & 0b100:
        return 2
    return 3


def award_entries(ctx: Ts2Context) -> tuple[list, list]:
    """The award screen lines for the items found or received since the last award screen, as
    (lines before the game's own entries, lines after them). Characters, cheats, hats, maps and
    game modes are left out: the game lists those itself once they unlock."""
    entries: list = []                   # (line, sort key)
    # Progressive items say what you have now (the level opened, x3, 50%, ...): item name ->
    # (positions in entries, how to make the line from the number of copies received).
    progressive: dict[str, tuple[list[int], object]] = {}

    def add_progressive(item_name: str, make_line, key: tuple) -> None:
        progressive.setdefault(item_name, ([], make_line))[0].append(len(entries))
        entries.append((None, key + (0, order)))
    for order, found in enumerate(ctx.award_screen.found):
        if isinstance(found, int):          # one of our locations: what is there
            item = ctx.locations_info.get(found)
            if item is None:
                continue
            receiver = item.player          # a NetworkItem for a location names who it is for
        else:                               # an item another player sent us
            item, receiver = found, ctx.slot
        if receiver != ctx.slot:
            try:
                name = ctx.item_names.lookup_in_slot(item.item, item.player)
            except Exception:
                name = "Unknown item"
            player = ctx.player_names.get(item.player, "Someone")
            name = short_item_name(name, _game_of(ctx, item.player))
            entries.append(((game_data.AWARD_OTHER_PLAYER.format(player=player), name),
                            (_BACK, _OTHER_PLAYER, _other_player_rank(item.flags), order)))
            continue
        name = _ITEM_ID_TO_NAME.get(item.item, "")
        if not name or name in _NATIVE_AWARDS:
            continue
        if name in game_data.STORY_ITEM_NAMES:
            level = game_data.STORY_ITEM_NAMES.index(name)
            if ctx.last_played == ("story", level):
                continue                    # you have just played it, so you know you have it
            line, key = (game_data.AWARD_STORY, game_data.STORY_LEVELS[level]), (_FRONT, _STORY)
        elif name == game_data.PROGRESSIVE_STORY_ITEM_NAME:
            add_progressive(name, lambda count: _story_line(ctx, count), (_FRONT, _STORY))
            continue
        elif name in _MISSIONS_BY_ITEM:
            mission = _MISSIONS_BY_ITEM[name]
            if ctx.last_played == ("mission", mission):
                continue
            challenge = mission.prefix == "Challenge"
            line = (game_data.AWARD_CHALLENGE if challenge else game_data.AWARD_MISSION, mission.name)
            key = (_FRONT, _CHALLENGE if challenge else _MISSION)
        elif name in _CARTRIDGES_BY_ITEM:
            line, key = (game_data.AWARD_CARTRIDGE, _CARTRIDGES_BY_ITEM[name]), (_FRONT, _CARTRIDGE)
        elif name in _WEAPONS_BY_ITEM:
            line, key = (game_data.AWARD_WEAPON, _WEAPONS_BY_ITEM[name]), (_BACK, _WEAPON)
        elif name in game_data.AWARD_MULTIPLIER_NAMES:
            add_progressive(name, lambda count, n=name: _multiplier_line(n, count), (_BACK, _MULTIPLIER))
            continue
        elif name == game_data.STARTING_ARMOUR_ITEM_NAME:
            add_progressive(name, _armour_line, (_BACK, _ITEM))
            continue
        elif name in _RESISTANCES_BY_ITEM:
            add_progressive(name, lambda count, n=name: _resistance_line(n, count), (_BACK, _RESISTANCE))
            continue
        elif name in _BUFFS_BY_ITEM:
            add_progressive(name, lambda count, n=name: _buff_line(n, count), (_BACK, _BUFF))
            continue
        else:
            line, key = (game_data.AWARD_ITEM, name), (_BACK, _ITEM)
        entries.append((line, key + (0, order)))
    for item_name, (positions, make_line) in progressive.items():
        # What each copy brought: they are the last ones received, in order.
        item_id = game_data.ITEM_NAME_TO_ID[item_name]
        received = sum(1 for item in ctx.items_received if item.item == item_id)
        first = received - len(positions)
        for k, position in enumerate(positions):
            entries[position] = (make_line(first + k + 1), entries[position][1])
    entries = [entry for entry in entries if entry[0] is not None]
    entries.sort(key=lambda entry: entry[1])
    front = [line for line, key in entries if key[0] == _FRONT]
    back = [line for line, key in entries if key[0] == _BACK]
    return front, back


def note_received_items(ctx: Ts2Context) -> None:
    """Add items other players have sent since the last look to the award list. Items already
    received when the client connects are not listed; our own items come with our locations."""
    if ctx.slot is None or not ctx.items_ready():
        return
    count = len(ctx.items_received)
    if ctx.award_items_seen is None or count < ctx.award_items_seen:
        ctx.award_items_seen = count
        return
    for item in ctx.items_received[ctx.award_items_seen:]:
        if item.player != ctx.slot:
            ctx.award_screen.found.append(item)
    ctx.award_items_seen = count


def award_hook(ctx: Ts2Context) -> bool:
    """Install the award screen hook as early as possible; True when ready."""
    state = game_state.ensure_award_hook(dolphin)
    if state == "ready":
        game_state.ensure_award_heading_fixes(dolphin)
    if state != ctx.award_hook_logged:
        ctx.award_hook_logged = state
        if state == "busy":
            logger.error("Archipelago items will NOT show on the award screen: the memory they need is in "
                         "use. Turn off cheat codes in Dolphin (Config > General > Enable Cheats) and "
                         "restart the game.")
        elif state == "unknown":
            logger.error("Archipelago items will NOT show on the award screen: the game's code is not what "
                         "the client expects.")
    return state == "ready"


async def check_locations(ctx: Ts2Context, levels: dict[str, int]) -> None:
    found = (game_state.earned_location_ids(levels) | game_state.milestone_location_ids(levels)
             | game_state.story_location_ids(dolphin)
             | ctx.objectives_found)
    found &= set(ctx.server_locations)       # only locations that exist in this seed
    new = found - set(ctx.checked_locations) - ctx.reported_locations
    if new:
        ctx.reported_locations |= new
        ctx.award_screen.found.extend(sorted(new))
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
                    if ctx.skip_easy_objectives:
                        ctx.objectives_found |= game_state.easy_only_objective_ids(dolphin)
                    # A cartridge reads 1 only until the client next sets it to 0 or 2, so it is
                    # noted here, before that happens, and remembered like the objectives.
                    ctx.objectives_found |= game_state.found_cartridge_ids(dolphin)
                    ctx.objectives_found |= game_state.uplink_location_ids(
                        dolphin, ctx.anaconda_checks, ctx.retroracer_checks, ctx.astrolander_checks)
                hook_ready = ctx.slot is not None and frame_hook(ctx)
                ctx.announcer.poll(dolphin, hook_ready)
                note_received_items(ctx)
                if game_state._read_word(dolphin, game_data.LEVEL_STATE) == game_data.LEVEL_STATE_PLAYING:
                    ctx.last_played = game_state.current_mission(dolphin) or ctx.last_played
                ctx.award_screen.poll(dolphin, award_hook(ctx),
                                      *(award_entries(ctx) if ctx.slot is not None else ([], [])))
                await death_link(ctx, hook_ready)
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
                    if ctx.shop_size:
                        await run_shop(ctx, levels)
                    if ctx.data_ok:
                        received = {item.item for item in ctx.items_received}
                        run_traps(ctx)
                        # A running trap unlocks its cheat for as long as it lasts.
                        trap_cheats = {game_data.ITEM_NAME_TO_ID[game_data.cheat_item_name(name)]
                                       for name, entry in game_data.TRAPS
                                       if entry in ctx.cheat_traps.unlocked_entries()}
                        game_state.enforce_unlocks(dolphin, received | trap_cheats)
                        game_state.enforce_default_characters(dolphin, received)
                        if ctx.shop_award_hidden:
                            game_state.hide_shop_awards(dolphin, {_ITEM_ID_TO_NAME[i] for i in ctx.shop_award_hidden
                                                                  if i in received and i in _ITEM_ID_TO_NAME})
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
                        armour_level = game_state.starting_armour_level([item.item for item in ctx.items_received])
                        given = ctx.starting_armour.poll(dolphin, armour_level)
                        if given is not None:
                            logger.debug(f"Starting armour: {given:g}")
                        if ctx.resistances_on:
                            enforce_resistances(ctx, [item.item for item in ctx.items_received], hook_ready)
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
                        ctx.frame_hook_logged = ""
                        ctx.resistance_state_logged = ""
                        ctx.shop_state_logged = ""
                        ctx.award_hook_logged = ""
                        award_hook(ctx)        # as early as possible: it only works before that code first runs
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
