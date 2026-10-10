"""
Reading and writing the game's memory.

Every function takes `mem`, an object with read_byte(address), read_bytes(address, n),
write_word(address, value) and write_bytes(address, data). In the real client that is the
dolphin_memory_engine module. Keeping Dolphin out of this file means the logic can be tested
without Dolphin running.
"""
import struct

from . import game_data


def _read_word(mem, address: int) -> int:
    return struct.unpack(">I", mem.read_bytes(address, 4))[0]


def _set_word(mem, address: int, value: int) -> None:
    if _read_word(mem, address) != value:
        mem.write_word(address, value)


# ---- Checks ----

def read_trophy_levels(mem) -> dict[str, int] | None:
    """Best trophy per mission: 0 = none, 1 = Bronze ... 4 = Platinum. None when no profile is loaded."""
    profile = _read_word(mem, game_data.PROFILE_POINTER)
    if not 0x80000000 <= profile < 0x81800000 - 0x1000:
        return None
    grades = [
        struct.unpack(">3I", mem.read_bytes(
            profile + game_data.TROPHY_FLAGS_OFFSET + game_data.TROPHY_GRADE_STRIDE * grade, 12))
        for grade in range(len(game_data.TIERS))
    ]
    levels: dict[str, int] = {}
    for mission in game_data.MISSIONS:
        word, bit = divmod(mission.number, 32)
        best = 0
        for grade in range(len(game_data.TIERS)):
            if grades[grade][word] >> bit & 1:
                best = grade + 1
        levels[mission.item_name] = best
    return levels


def earned_location_ids(levels: dict[str, int]) -> set[int]:
    """A Silver also counts as the Bronze, a Platinum as all four, and so on."""
    found: set[int] = set()
    for mission in game_data.MISSIONS:
        for tier in range(1, levels.get(mission.item_name, 0) + 1):
            found.add(game_data.location_id(mission.number, tier))
    return found


def milestone_location_ids(levels: dict[str, int]) -> set[int]:
    """Group and league milestones: a Bronze or better on every one of their missions."""
    return {
        location_id for _name, location_id, missions, _kind in game_data.MILESTONES
        if all(levels.get(m.item_name, 0) >= game_data.MILESTONE_TROPHY for m in missions)
    }


def trophy_goal_reached(levels: dict[str, int], grade: int, hunt: int = game_data.HUNT_ALL) -> bool:
    """Trophy Hunt goal: at least `grade` (1 Bronze ... 4 Platinum) on every hunted mission."""
    return all(levels.get(m.item_name, 0) >= grade for m in game_data.hunted_missions(hunt))


def trophies_at_grade(levels: dict[str, int] | None, grade: int) -> int:
    """How many missions have at least `grade`."""
    if levels is None:
        return 0
    return sum(1 for m in game_data.MISSIONS if levels.get(m.item_name, 0) >= grade)


# ---- Unlocks ----

def check_game_data(mem) -> list[str]:
    """
    Make sure the group table in this copy of the game is the one this client was written for,
    before anything is written. Returns a list of problems (empty = all good).
    """
    problems = []
    for g, (_prefix, group, missions) in enumerate(game_data.GROUPS):
        base = game_data.GROUP_TABLE + game_data.GROUP_STRIDE * g
        count = _read_word(mem, base + game_data.GROUP_COUNT_OFFSET)
        numbers = [_read_word(mem, base + game_data.GROUP_MISSIONS_OFFSET + 4 * i) for i in range(len(missions))]
        if count != len(missions) or numbers != [number for _name, number in missions]:
            problems.append(f"{group}: group record at {base:08X} is not as expected")
        elif _read_word(mem, game_data.group_condition_address(g)) > game_data.CONDITION_MAX:
            problems.append(f"{group}: no condition at {game_data.group_condition_address(g):08X}")
    for entry, (name, number) in enumerate(game_data.CHARACTER_ENTRIES):
        base = game_data.CHARACTER_TABLE + game_data.CHARACTER_STRIDE * entry
        if (_read_word(mem, base) != number
                or _read_word(mem, base + game_data.CHARACTER_CONDITION_OFFSET) > game_data.CONDITION_MAX):
            problems.append(f"{name}: character entry at {base:08X} is not as expected")
    for name, entry, text_id in game_data.CHEAT_ENTRIES:
        base = game_data.CHEAT_TABLE + game_data.CHEAT_STRIDE * entry
        if (_read_word(mem, base) >> 16 != text_id
                or _read_word(mem, base + game_data.CHEAT_CONDITION_OFFSET) > game_data.CONDITION_MAX):
            problems.append(f"{name}: cheat entry at {base:08X} is not as expected")
    for name, address, text_id in game_data.LOCKED_CHEATS:
        if (_read_word(mem, address - game_data.CHEAT_CONDITION_OFFSET) >> 16 != text_id
                or _read_word(mem, address) > game_data.CONDITION_MAX):
            problems.append(f"{name}: cheat entry before {address:08X} is not as expected")
    for name, entry, text_id in game_data.MAP_ENTRIES:
        base = game_data.MAP_TABLE + game_data.MAP_STRIDE * entry
        if (_read_word(mem, base) != text_id
                or _read_word(mem, base + game_data.MAP_CONDITION_OFFSET) > game_data.CONDITION_MAX):
            problems.append(f"{name}: map entry at {base:08X} is not as expected")
    for name, number, text_id in game_data.MODE_ENTRIES:
        record = game_data.MODE_TABLE + game_data.MODE_STRIDE * number
        address = game_data.MODE_CONDITIONS + game_data.MODE_CONDITION_STRIDE * number
        if _read_word(mem, record + 0x14) >> 16 != text_id or _read_word(mem, address) > game_data.CONDITION_MAX:
            problems.append(f"{name}: mode entry for {address:08X} is not as expected")
    for name, entry, double, text_id in game_data.WEAPON_ENTRIES:
        for k in (entry, double):
            if k is None:
                continue
            definition = game_data.WEAPON_DEFINITIONS + game_data.WEAPON_DEFINITION_STRIDE * k
            if (k == entry and _read_word(mem, definition) != text_id) \
                    or _read_word(mem, game_data.weapon_condition_address(k)) > game_data.CONDITION_MAX:
                problems.append(f"{name}: weapon entry {k} is not as expected")
    for name, address in [(h[0], h[1]) for h in game_data.HATS] + list(game_data.ASSAULT_MAPS):
        if _read_word(mem, address) > game_data.CONDITION_MAX:
            problems.append(f"{name} Hat: no condition at {address:08X}")
    for level, _record, address, text_id, name, _roles in game_data.STORY_OBJECTIVES:
        if _read_word(mem, address) != text_id:
            problems.append(f"{game_data.STORY_LEVELS[level]} - {name}: objective record at {address:08X} "
                            "is not as expected")
    if _read_word(mem, game_data.JUMP_ENTRY) not in (game_data.JUMP_NORMAL, game_data.ROUTINE):
        problems.append(f"condition jump table entry at {game_data.JUMP_ENTRY:08X} is not as expected")
    return problems


def lock_state(mem) -> str:
    """
    'installed' (our routine is in use), 'ready' (not installed, memory is free), 'busy' (the
    memory the routine needs is in use, usually by Dolphin's cheat codes) or 'unknown'.
    """
    entry = _read_word(mem, game_data.JUMP_ENTRY)
    code = tuple(_read_word(mem, game_data.ROUTINE + 4 * k) for k in range(len(game_data.ROUTINE_CODE)))
    if entry == game_data.ROUTINE:
        return "installed" if code == game_data.ROUTINE_CODE else "unknown"
    if entry != game_data.JUMP_NORMAL:
        return "unknown"
    if any(mem.read_bytes(game_data.ROUTINE, game_data.ROUTINE_AREA)):
        return "busy"
    return "ready"


def _write_missions(mem, owned_numbers: set[int]) -> None:
    table = bytes(1 if number in owned_numbers else 0 for number in range(game_data.MISSION_COUNT))
    if mem.read_bytes(game_data.MISSION_TABLE, game_data.MISSION_COUNT) != table:
        mem.write_bytes(game_data.MISSION_TABLE, table)
    for g, (_prefix, _group, missions) in enumerate(game_data.GROUPS):
        address = game_data.group_condition_address(g)
        if _read_word(mem, address) > game_data.CONDITION_MAX:
            continue                             # not a condition any more: leave it alone
        # A group is open when at least one of its missions is owned. Word 1 first, so the
        # group never reads as open for a moment by accident.
        _set_word(mem, address + 4, 1 if any(number in owned_numbers for _name, number in missions) else 0)
        _set_word(mem, address, game_data.CONDITION_HOOKED)


def _lock(mem, address: int) -> None:
    """Lock a character or cheat with the never-met condition (its entry stays in the game's lists)."""
    kind, mission, grade = game_data.NEVER_MET
    _set_word(mem, address + 4, mission)         # the details first, the type last
    _set_word(mem, address + 8, grade)
    _set_word(mem, address, kind)


def enforce_unlocks(mem, received_item_ids: set[int]) -> None:
    """
    Every character, cheat, Silly Hat, arcade map, game mode and weapon is unlocked exactly when its
    item has been received. Unlocked is condition type 1. Characters, cheats, maps, modes and weapons are
    locked with a condition that can never be met (type 0 would remove characters and cheats
    from the game's lists, and is avoided for the others to be safe); hats are locked with type 0.
    The save is never touched. Safe to call many times a second: it only writes when something
    needs to change.
    """
    def owned(item_name: str) -> bool:
        return game_data.ITEM_NAME_TO_ID[item_name] in received_item_ids

    def is_condition(address: int) -> bool:
        return _read_word(mem, address) <= game_data.CONDITION_MAX

    listed = [(address, game_data.character_item_name(name)) for name, address, _n in game_data.CHARACTERS]
    listed += [(address, game_data.cheat_item_name(name)) for name, address, _n in game_data.CHEATS]
    listed += [(address, game_data.map_item_name(name)) for name, address, _n in game_data.MAPS]
    listed += [(address, game_data.map_item_name(name)) for name, address in game_data.ASSAULT_MAPS]
    listed += [(address, game_data.mode_item_name(name)) for name, address, _n in game_data.MODES]
    for name, entry, double, _text in game_data.WEAPON_ENTRIES:
        # The (x2) version comes with the weapon.
        listed += [(game_data.weapon_condition_address(k), game_data.weapon_item_name(name))
                   for k in (entry, double) if k is not None]
    for address, item_name in listed:
        if not is_condition(address):
            continue                             # not a condition any more: leave it alone
        if owned(item_name):
            _set_word(mem, address, game_data.CONDITION_UNLOCKED)
        else:
            _lock(mem, address)
    for _name, address, _text_id in game_data.LOCKED_CHEATS:
        if is_condition(address):
            _lock(mem, address)
    for name, address, _number in game_data.HATS:
        if is_condition(address):
            _set_word(mem, address, game_data.CONDITION_UNLOCKED
                      if owned(game_data.hat_item_name(name)) else game_data.CONDITION_LOCKED)


def enforce_default_characters(mem, received_item_ids: set[int]) -> None:
    """
    Keep the game's four default characters set to characters the player owns (the first four
    in the game's own order, repeated if there are fewer). Does nothing while none are owned.
    """
    owned = [number for name, _address, number in game_data.CHARACTERS
             if game_data.ITEM_NAME_TO_ID[game_data.character_item_name(name)] in received_item_ids]
    if not owned:
        return
    for k in range(game_data.DEFAULT_CHARACTER_COUNT):
        address = game_data.DEFAULT_CHARACTERS + 4 * k
        if _read_word(mem, address) < game_data.CHARACTER_NUMBER_LIMIT:   # still a character number
            _set_word(mem, address, owned[k % len(owned)])


def enforce_missions(mem, received_item_ids: set[int]) -> str:
    """
    Every mission is playable exactly when its item has been received, and a group is open when
    one of its missions is. Safe to call many times a second: it only writes when something
    needs to change. Returns lock_state() after the call. Call enforce_unlocks() first: it
    replaces the one other type 5 condition in the game (the Paintball cheat).
    """
    owned = {m.number for m in game_data.MISSIONS
             if game_data.ITEM_NAME_TO_ID[m.item_name] in received_item_ids}
    state = lock_state(mem)
    if state == "ready":
        for k, word in enumerate(game_data.ROUTINE_CODE):
            mem.write_word(game_data.ROUTINE + 4 * k, word)
        _write_missions(mem, owned)
        mem.write_word(game_data.JUMP_ENTRY, game_data.ROUTINE)   # last: everything it uses is in place
        return "installed"
    if state == "installed":
        _write_missions(mem, owned)
    return state


# ---- Story Mode ----

def _story_words(mem) -> tuple[int, ...] | None:
    """The three single-player completion words (Easy, Normal, Hard), or None with no profile."""
    profile = _read_word(mem, game_data.PROFILE_POINTER)
    if not 0x80000000 <= profile < 0x81800000 - 0x1000:
        return None
    return struct.unpack(">3I", mem.read_bytes(profile + game_data.STORY_FLAGS_OFFSET, 12))


def story_location_ids(mem) -> set[int]:
    """Story levels completed in single player, per difficulty (read from the profile)."""
    words = _story_words(mem)
    found: set[int] = set()
    if words is None:
        return found
    for d, bits in enumerate(words):
        for level in range(len(game_data.STORY_LEVELS)):
            if bits >> level & 1:
                found.add(game_data.story_location_id(level, d))
    return found


def story_levels_beaten(mem) -> int:
    """How many story levels other than the last are complete (on any difficulty)."""
    words = _story_words(mem)
    if words is None:
        return 0
    return bin(words[0] & ((1 << game_data.FINAL_STORY_LEVEL) - 1)).count("1")   # Easy is set by every difficulty


def story_goal_reached(mem) -> bool:
    """The last story level is complete on any difficulty."""
    words = _story_words(mem)
    return words is not None and bool(words[0] >> game_data.FINAL_STORY_LEVEL & 1)


def story_mask(received_items: list[int], final_open: bool, progressive: bool = False) -> int:
    """
    Bit N set = story level N is open: the levels owned, the last one only when final_open.
    received_items is the full list of received item IDs (with repeats, which is what makes
    Progressive Story Level work: N copies open the first N levels).
    """
    if progressive:
        count = received_items.count(game_data.ITEM_NAME_TO_ID[game_data.PROGRESSIVE_STORY_ITEM_NAME])
        mask = (1 << min(count, len(game_data.STORY_LEVELS))) - 1
    else:
        owned = set(received_items)
        mask = 0
        for level in range(len(game_data.STORY_LEVELS)):
            if game_data.ITEM_NAME_TO_ID[game_data.story_item_name(level)] in owned:
                mask |= 1 << level
    if not final_open:
        mask &= ~(1 << game_data.FINAL_STORY_LEVEL)
    return mask


def story_state(mem) -> str:
    """
    'installed', 'ready' (the game's own code is there and the memory we need is free), 'busy'
    (that memory is in use, usually by Dolphin's cheat codes) or 'unknown' (not the code we
    expect: leave it alone).
    """
    def words(address: int, count: int) -> tuple[int, ...]:
        return struct.unpack(f">{count}I", mem.read_bytes(address, 4 * count))

    code = words(game_data.STORY_FUNCTION, len(game_data.STORY_PATCH))
    routines = words(game_data.STORY_ROUTINES, len(game_data.STORY_ROUTINE_CODE))
    pointers = [_read_word(mem, address) for address, _normal, _ours in game_data.STORY_MENU_POINTERS]
    ours = [routine for _address, _normal, routine in game_data.STORY_MENU_POINTERS]
    normal = [value for _address, value, _routine in game_data.STORY_MENU_POINTERS]
    if code == game_data.STORY_PATCH and routines == game_data.STORY_ROUTINE_CODE and pointers == ours:
        return "installed"
    if code != game_data.STORY_ORIGINAL or pointers != normal:
        return "unknown"
    area = mem.read_bytes(game_data.STORY_ROUTINES, game_data.STORY_AREA_END - game_data.STORY_ROUTINES)
    return "busy" if any(area) else "ready"


def enforce_story(mem, mask: int) -> str:
    """
    Story levels are open exactly as `mask` says. Installs the story patch the first time and
    afterwards only updates the mask. Returns story_state() after the call.
    """
    state = story_state(mem)
    if state == "ready":
        mem.write_word(game_data.STORY_MASK_ADDRESS, mask)
        for k, word in enumerate(game_data.STORY_ROUTINE_CODE):
            mem.write_word(game_data.STORY_ROUTINES + 4 * k, word)
        # The function last to first, so it only changes behaviour when its first instruction
        # (the entry point) is replaced.
        for k in reversed(range(len(game_data.STORY_PATCH))):
            mem.write_word(game_data.STORY_FUNCTION + 4 * k, game_data.STORY_PATCH[k])
        for address, _normal, routine in game_data.STORY_MENU_POINTERS:
            mem.write_word(address, routine)
        return "installed"
    if state == "installed":
        _set_word(mem, game_data.STORY_MASK_ADDRESS, mask)
    return state


def completed_objective_ids(mem) -> set[int]:
    """
    Story objectives the game currently shows as completed. The records keep their state until
    the level is loaded again, but the client remembers what it has seen anyway.
    """
    found: set[int] = set()
    for level, record, address, _text_id, _name, _roles in game_data.STORY_OBJECTIVES:
        if _read_word(mem, address + game_data.OBJECTIVE_STATE_OFFSET) == game_data.OBJECTIVE_COMPLETED:
            found.add(game_data.objective_location_id(level, record))
    return found


# ---- Training Ground (Assault) ----

def training_ground_state(mem) -> str:
    """'installed', 'ready', 'busy' (memory in use, usually by cheat codes) or 'unknown'."""
    code = struct.unpack(f">{len(game_data.MAP_MENU_ROUTINE_CODE)}I",
                         mem.read_bytes(game_data.MAP_MENU_ROUTINE, 4 * len(game_data.MAP_MENU_ROUTINE_CODE)))
    pointer = _read_word(mem, game_data.MAP_MENU_POINTER)
    check = _read_word(mem, game_data.TRAINING_GROUND_ASSAULT_CHECK)
    if check not in (game_data.TRAINING_GROUND_OPEN, game_data.TRAINING_GROUND_SHUT):
        return "unknown"
    if pointer == game_data.MAP_MENU_ROUTINE and code == game_data.MAP_MENU_ROUTINE_CODE:
        return "installed"
    if pointer != game_data.MAP_MENU_NORMAL or check != game_data.TRAINING_GROUND_OPEN:
        return "unknown"
    area = mem.read_bytes(game_data.MAP_MENU_ROUTINE, game_data.MAP_MENU_AREA_END - game_data.MAP_MENU_ROUTINE)
    return "busy" if any(area) else "ready"


def enforce_training_ground(mem, received_item_ids: set[int]) -> str:
    """Training Ground's Assault version is open exactly when the Training Ground item is owned."""
    owned = game_data.ITEM_NAME_TO_ID[game_data.map_item_name("Training Ground")] in received_item_ids
    wanted = game_data.TRAINING_GROUND_OPEN if owned else game_data.TRAINING_GROUND_SHUT
    state = training_ground_state(mem)
    if state == "ready":
        for k, word in enumerate(game_data.MAP_MENU_ROUTINE_CODE):
            mem.write_word(game_data.MAP_MENU_ROUTINE + 4 * k, word)
        mem.write_word(game_data.TRAINING_GROUND_ASSAULT_CHECK, wanted)
        mem.write_word(game_data.MAP_MENU_POINTER, game_data.MAP_MENU_ROUTINE)
        return "installed"
    if state == "installed":
        _set_word(mem, game_data.TRAINING_GROUND_ASSAULT_CHECK, wanted)
    return state


# ---- Behead The Undead score multiplier ----

def multiplier_level(received_items: list[int], item_name: str) -> int:
    """1 (normal) to 4, from how many copies of a Progressive multiplier have been received."""
    count = received_items.count(game_data.ITEM_NAME_TO_ID[item_name])
    return 1 + min(count, game_data.MULTIPLIER_COPIES)


def score_state(mem) -> str:
    """'installed', 'ready', 'busy' (memory in use, usually by cheat codes) or 'unknown'."""
    def words(address: int, count: int) -> tuple[int, ...]:
        return struct.unpack(f">{count}I", mem.read_bytes(address, 4 * count))

    hooks = tuple(_read_word(mem, address) for address, _o, _r, _f in game_data.SCORE_HOOKS)
    routine = words(game_data.SCORE_MENU_ROUTINE, len(game_data.SCORE_MENU_ROUTINE_CODE))
    caves = words(game_data.SCORE_CAVES, len(game_data.SCORE_CAVE_CODE))
    pointer = _read_word(mem, game_data.SCORE_MENU_POINTER)
    if (hooks == game_data.SCORE_HOOK_BRANCHES and routine == game_data.SCORE_MENU_ROUTINE_CODE
            and caves == game_data.SCORE_CAVE_CODE and pointer == game_data.SCORE_MENU_ROUTINE):
        return "installed"
    if hooks != tuple(original for _a, original, _r, _f in game_data.SCORE_HOOKS) \
            or pointer != game_data.SCORE_MENU_NORMAL:
        return "unknown"
    area = mem.read_bytes(game_data.BEHEAD_FACTOR, game_data.SCORE_AREA_END - game_data.BEHEAD_FACTOR)
    return "busy" if any(area) else "ready"


def enforce_score_multipliers(mem, factors: dict[str, int]) -> str:
    """
    Points in Behead The Undead are multiplied by factors[item name] (1-4). Installs the
    patch the first time, afterwards only updates the number. Returns
    score_state() after the call.
    """
    state = score_state(mem)
    if state == "ready":
        for name, address in game_data.MULTIPLIER_FACTORS.items():
            mem.write_word(address, factors[name])
        for k, word in enumerate(game_data.SCORE_MENU_ROUTINE_CODE):
            mem.write_word(game_data.SCORE_MENU_ROUTINE + 4 * k, word)
        for k, word in enumerate(game_data.SCORE_CAVE_CODE):
            mem.write_word(game_data.SCORE_CAVES + 4 * k, word)
        for (address, _o, _r, _f), branch in zip(game_data.SCORE_HOOKS, game_data.SCORE_HOOK_BRANCHES):
            mem.write_word(address, branch)
        mem.write_word(game_data.SCORE_MENU_POINTER, game_data.SCORE_MENU_ROUTINE)
        return "installed"
    if state == "installed":
        for name, address in game_data.MULTIPLIER_FACTORS.items():
            _set_word(mem, address, factors[name])
    return state


# ---- Progressive Starting Armour ----

def starting_armour_level(received_items: list[int]) -> int:
    """0 to 4: how many Progressive Starting Armour items count."""
    count = received_items.count(game_data.ITEM_NAME_TO_ID[game_data.STARTING_ARMOUR_ITEM_NAME])
    return min(count, game_data.STARTING_ARMOUR_COPIES)


def in_story_level(mem) -> bool:
    """True while a story level is being played (any of them, not just Siberia)."""
    return 1 <= _read_word(mem, game_data.SETUP_STORY_LEVEL) <= game_data.SETUP_STORY_LEVEL_MAX


def starting_armour_applies(mem) -> bool:
    """Story, every Arcade League mission, Behead The Undead, Banana Chomp and 'Story' Classic."""
    if in_story_level(mem):
        return True
    mission = game_data.MISSION_BY_NUMBER.get(_read_word(mem, game_data.SETUP_MISSION_NUMBER))
    if mission is None:
        return False
    return mission.prefix != "Challenge" or mission.group in game_data.STARTING_ARMOUR_CHALLENGE_GROUPS


def _float(word: int) -> float:
    return struct.unpack(">f", struct.pack(">I", word))[0]


def _in_ram(address: int) -> bool:
    return 0x80000000 <= address < 0x81800000 - 0x2000


def player_state(mem):
    """(object address, armour, full bar, health) while playing a level, else None."""
    if _read_word(mem, game_data.SETUP_IN_LEVEL) == 0:
        return None
    player = _read_word(mem, game_data.PLAYER_LIST)
    if not _in_ram(player):
        return None
    full = _float(_read_word(mem, player + game_data.PLAYER_FULL_BAR_OFFSET))
    armour = _float(_read_word(mem, player + game_data.PLAYER_ARMOUR_OFFSET))
    body = _read_word(mem, player + game_data.PLAYER_BODY_OFFSET)
    if not (0.0 < full <= 1000.0 and -1.0 <= armour <= 1000.0 and _in_ram(body)):
        return None
    health = _float(_read_word(mem, body + game_data.BODY_HEALTH_OFFSET))
    if not -10000.0 <= health <= 10000.0:
        return None
    return player, armour, full, health


class StartingArmour:
    """
    Gives armour once at the start of each life: a level that has just loaded, a restart or a
    retry (the level state passing through a reload state), or a respawn (health coming back
    above 0). It only ever raises armour, to a quarter of a full bar per item, and never during
    a life.
    """

    def __init__(self) -> None:
        self.player = 0           # player object last seen (0 = none)
        self.health = None        # health at the last poll
        self.reloading = False    # a reload state has been seen since armour was last given
        self.pending = 0          # polls left before armour is given; 0 = nothing to give

    def poll(self, mem, level: int):
        """Call every 0.25 s. Returns the armour written (a number) when it gives some, else None."""
        level_state = _read_word(mem, game_data.LEVEL_STATE)
        if level_state in game_data.LEVEL_STATE_RELOADING:
            self.reloading, self.pending = True, 0
        state = player_state(mem)
        if state is None:
            self.player, self.health, self.pending = 0, None, 0
            return None
        if level_state != game_data.LEVEL_STATE_PLAYING:
            return None
        player, armour, full, health = state
        respawned = self.health is not None and self.health <= 0.0 < health
        if player != self.player or self.reloading or respawned:
            self.reloading = False
            self.pending = game_data.STARTING_ARMOUR_SETTLE_POLLS
        self.player, self.health = player, health
        if not self.pending:
            return None
        self.pending -= 1
        if self.pending or level <= 0 or health <= 0.0 or not starting_armour_applies(mem):
            return None
        target = full * level / game_data.STARTING_ARMOUR_COPIES
        if not 0.0 <= armour < target:
            return None
        mem.write_word(player + game_data.PLAYER_ARMOUR_OFFSET, struct.unpack(">I", struct.pack(">f", target))[0])
        return target


# ---- Temporal Uplink cartridges ----

def _profile(mem) -> int | None:
    profile = _read_word(mem, game_data.PROFILE_POINTER)
    return profile if 0x80000000 <= profile < 0x81800000 - 0x2000 else None


def found_cartridge_ids(mem) -> set[int]:
    """Location IDs of the cartridges that have just been picked up (their word reads 1)."""
    profile = _profile(mem)
    if profile is None:
        return set()
    return {game_data.cartridge_location_id(k) for k, (_g, _l, offset, _h) in enumerate(game_data.CARTRIDGES)
            if _read_word(mem, profile + offset) == game_data.CARTRIDGE_PICKED_UP}


def enforce_cartridges(mem, received_item_ids: set[int]) -> None:
    """Keep each cartridge's word at 2 if you have its item, else 0. Read found_cartridge_ids first."""
    profile = _profile(mem)
    if profile is None:
        return
    for _game, _level, offset, _hard in game_data.CARTRIDGES:
        owned = game_data.ITEM_NAME_TO_ID[game_data.cartridge_item_name(_game)] in received_item_ids
        _set_word(mem, profile + offset, game_data.CARTRIDGE_OWNED if owned else 0)


# ---- Temporal Uplink games ----

def uplink_location_ids(mem, anaconda_checks: int, retroracer: bool, astrolander_checks: int) -> set[int]:
    """Locations reached in the Temporal Uplink's games (only read during Story)."""
    if not in_story_level(mem):
        return set()
    found: set[int] = set()
    score = _read_word(mem, game_data.ANACONDA_SCORE)
    if score <= 1_000_000:
        for step in range(1, min(anaconda_checks, score // game_data.ANACONDA_STEP) + 1):
            found.add(game_data.anaconda_location_id(step * game_data.ANACONDA_STEP))
    if retroracer:
        laps = mem.read_byte(game_data.RETRORACER_LAPS)
        if laps <= game_data.RETRORACER_LAP_COUNT:
            found |= {game_data.retroracer_location_id(k) for k in range(laps)}
            if laps == game_data.RETRORACER_LAP_COUNT:
                found.add(game_data.retroracer_location_id(game_data.RETRORACER_LAP_COUNT))
    level = mem.read_byte(game_data.ASTROLANDER_LEVEL)
    if level <= game_data.ASTROLANDER_LEVEL_COUNT:
        found |= {game_data.astrolander_location_id(k) for k in range(1, min(level, astrolander_checks) + 1)}
    return found


# ---- Weapon buffs ----

def weapon_buff_levels(received_items: list[int]) -> list[tuple[str, int, int, int, int]]:
    """
    One entry per weapon buff you have at least one copy of, in alphabetical order:
    (item name, copies counted, most copies that count, normal value, value now).
    """
    rows = []
    for weapon, stat, _addresses, normal, change, copies, _priority in game_data.WEAPON_BUFFS:
        name = game_data.weapon_buff_item_name(weapon, stat, change)
        have = min(received_items.count(game_data.ITEM_NAME_TO_ID[name]), copies)
        if have:
            rows.append((name, have, copies, normal, game_data.weapon_buff_value(normal, change, have)))
    return sorted(rows)


def enforce_weapon_buffs(mem, received_items: list[int]) -> list[str]:
    """
    Make every buffed stat match the copies you have. A stat is only written while it holds its
    normal value or one of its own buff steps; anything else (another cheat, a different game
    version) is left alone and its item name is returned.
    """
    skipped = []
    for weapon, stat, addresses, normal, change, copies, _priority in game_data.WEAPON_BUFFS:
        name = game_data.weapon_buff_item_name(weapon, stat, change)
        have = min(received_items.count(game_data.ITEM_NAME_TO_ID[name]), copies)
        target = game_data.weapon_buff_value(normal, change, have)
        steps = {game_data.weapon_buff_value(normal, change, k) for k in range(copies + 1)}
        for address in addresses:
            current = _read_word(mem, address)
            if current == target:
                continue
            if current not in steps:
                if name not in skipped:
                    skipped.append(name)
                continue
            mem.write_word(address, target)
    return skipped


# ---- Cheat traps ----

class CheatTraps:
    """
    Runs the cheat traps received: each switches its cheat on for a number of seconds of play.
    Traps wait while you are in the menus and start the moment you are playing a level; their
    time only runs while the level state is "playing". A trap only ever takes back the cheat
    bits it added, so cheats you switched on yourself stay on.
    """

    def __init__(self) -> None:
        self.pending: list[int] = []            # cheat entries waiting for you to be playing
        self.active: dict[int, float] = {}      # cheat entry -> seconds left
        self.added_active = 0                   # bits this class set in CHEAT_ACTIVE
        self.added_allowed = 0                  # ... and in CHEAT_ALLOWED

    def add(self, entry: int) -> None:
        self.pending.append(entry)

    def unlocked_entries(self) -> set[int]:
        """Cheat entries to treat as unlocked right now (their trap is running)."""
        return set(self.active)

    def _bits(self) -> int:
        bits = 0
        for entry in self.active:
            bits |= 1 << entry
        return bits

    def _take_back(self, mem, bits: int) -> None:
        for address, attr in ((game_data.CHEAT_ACTIVE, "added_active"), (game_data.CHEAT_ALLOWED, "added_allowed")):
            ours = getattr(self, attr) & bits
            if ours:
                _set_word(mem, address, _read_word(mem, address) & ~ours)
                setattr(self, attr, getattr(self, attr) & ~ours)

    def poll(self, mem, duration: float, elapsed: float) -> list[tuple[str, int]]:
        """
        Call every poll with the trap length (seconds) and the time since the last call. Returns
        events for the log: ("start", entry) and ("end", entry).
        """
        events: list[tuple[str, int]] = []
        if player_state(mem) is None:                       # menus or loading: put things back
            self._take_back(mem, self.added_active | self.added_allowed)
            return events
        if _read_word(mem, game_data.LEVEL_STATE) == game_data.LEVEL_STATE_PLAYING:
            for entry in self.pending:
                self.active[entry] = self.active.get(entry, 0.0) + duration
                events.append(("start", entry))
            self.pending = []
            for entry in list(self.active):
                self.active[entry] -= elapsed
                if self.active[entry] <= 0:
                    del self.active[entry]
                    events.append(("end", entry))
        bits = self._bits()
        self._take_back(mem, (self.added_active | self.added_allowed) & ~bits)
        for address, attr in ((game_data.CHEAT_ACTIVE, "added_active"), (game_data.CHEAT_ALLOWED, "added_allowed")):
            current = _read_word(mem, address)
            missing = bits & ~current
            if missing:
                mem.write_word(address, current | missing)
                setattr(self, attr, getattr(self, attr) | missing)
        return events


# ---- Death Link ----

def current_mission_name(mem) -> str | None:
    """The story level or Arcade League / Challenge mission being played, or None outside a level."""
    if _read_word(mem, game_data.SETUP_IN_LEVEL) == 0:
        return None
    story = _read_word(mem, game_data.SETUP_STORY_LEVEL)
    if 1 <= story <= len(game_data.STORY_LEVELS):
        return game_data.STORY_LEVELS[story - 1]
    if 1 <= story <= game_data.SETUP_STORY_LEVEL_MAX:
        return "a story level"
    mission = game_data.MISSION_BY_NUMBER.get(_read_word(mem, game_data.SETUP_MISSION_NUMBER))
    return mission.name if mission is not None else "a mission"


def ensure_death_hook(mem) -> str:
    """
    Make the game able to fail the current mission on request. Returns 'ready', 'busy' (the
    memory it needs is in use, e.g. by Dolphin's cheat codes) or 'unknown' (the game's data is
    not what we expect). Nothing is changed unless the result is 'ready'.
    """
    code = game_data.DEATH_CAVE_CODE
    entry = _read_word(mem, game_data.STATE_TABLE_PLAYING)
    if entry not in (game_data.STATE_PLAYING_HANDLER, game_data.DEATH_CAVE):
        return "unknown"
    current = struct.unpack(f">{len(code)}I", mem.read_bytes(game_data.DEATH_CAVE, 4 * len(code)))
    trigger = _read_word(mem, game_data.DEATH_TRIGGER)
    if current == code and trigger in (0, 1):
        if entry != game_data.DEATH_CAVE:
            mem.write_word(game_data.STATE_TABLE_PLAYING, game_data.DEATH_CAVE)
        return "ready"
    if entry == game_data.DEATH_CAVE:              # never leave the game pointed at something else
        mem.write_word(game_data.STATE_TABLE_PLAYING, game_data.STATE_PLAYING_HANDLER)
    if any(current) or trigger:
        return "busy"
    for k, value in enumerate(code):
        mem.write_word(game_data.DEATH_CAVE + 4 * k, value)
    mem.write_word(game_data.STATE_TABLE_PLAYING, game_data.DEATH_CAVE)
    return "ready"


class MissionFailure:
    """Notices the game failing a mission, and can make it fail the one being played."""

    def __init__(self) -> None:
        self.armed = False        # a mission is being played and has not failed yet
        self.caused = False       # the next failure is one we asked for
        self.waiting = 0          # polls left for the game to act on our request
        self.control = 0          # polls in a row with control of the player in a story level

    def poll(self, mem) -> str | None:
        """Call every 0.25 s. Returns the mission's name when it has just failed by itself."""
        if self.waiting:
            self.waiting -= 1
            if not self.waiting and _read_word(mem, game_data.DEATH_TRIGGER):   # the game never took it
                mem.write_word(game_data.DEATH_TRIGGER, 0)
                self.caused = False
        name = current_mission_name(mem)
        if name is not None and in_story_level(mem) and _read_word(mem, game_data.STORY_CONTROL_FLAG) == 0:
            self.control = 0
        else:
            self.control += 1
        if name is None:
            self.armed = False
            return None
        failed = _read_word(mem, game_data.SETUP_FLAGS_5C) & game_data.SETUP_FAILED_FLAG
        if not failed:
            if _read_word(mem, game_data.LEVEL_STATE) == game_data.LEVEL_STATE_PLAYING:
                self.armed = True
            return None
        if not self.armed:
            return None
        self.armed = False
        if self.caused:
            self.caused = False
            return None
        return name

    def in_cutscene(self, mem) -> bool:
        """True during a story cutscene, and for a moment after it, while a level is being played."""
        return current_mission_name(mem) is not None and self.control <= game_data.CUTSCENE_SETTLE_POLLS

    def fail(self, mem) -> str | None:
        """Fail the mission being played. Returns its name, or None when there is nothing to fail."""
        name = current_mission_name(mem)
        if (name is None or not self.armed or self.caused or self.in_cutscene(mem)
                or _read_word(mem, game_data.LEVEL_STATE) != game_data.LEVEL_STATE_PLAYING
                or ensure_death_hook(mem) != "ready"):
            return None
        mem.write_word(game_data.DEATH_TRIGGER, 1)
        self.caused = True
        self.waiting = game_data.DEATH_TRIGGER_POLLS
        return name


# ---- Easier trophy requirements ----

def enforce_easier_trophies(mem, enabled: dict[str, bool]) -> dict[str, str]:
    """
    Set each mission's trophy requirements to the easier values (option on) or the normal ones.
    Returns, per option, 'easier', 'normal' or 'unknown' (a value is neither: nothing is changed
    for that mission).
    """
    result = {}
    for option, rules in game_data.EASIER_TROPHIES.items():
        on = bool(enabled.get(option))
        current = [_read_word(mem, address) for address, _normal, _easier in rules]
        if any(now not in (normal, easier) for now, (_a, normal, easier) in zip(current, rules)):
            result[option] = "unknown"
            continue
        for now, (address, normal, easier) in zip(current, rules):
            wanted = easier if on else normal
            if now != wanted:
                mem.write_word(address, wanted)
        result[option] = "easier" if on else "normal"
    return result
