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


# ---- Damage resistances ----

def resistance_levels(received_items: list[int]) -> dict[str, int]:
    """Group -> copies that count (0 to RESISTANCE_COPIES)."""
    return {group: min(received_items.count(game_data.ITEM_NAME_TO_ID[game_data.resistance_item_name(group)]),
                       game_data.RESISTANCE_COPIES)
            for group, _types in game_data.RESISTANCES}


def resistance_factors(levels: dict[str, int]) -> list[float]:
    """The damage multiplier for each damage type."""
    factors = [1.0] * game_data.DAMAGE_TYPE_COUNT
    for group, types in game_data.RESISTANCES:
        for t in types:
            factors[t] = round(1.0 - game_data.RESISTANCE_STEP * levels.get(group, 0), 4)
    return factors


def enforce_resistances(mem, levels: dict[str, int], frame_hook_ready: bool) -> str:
    """
    Install the damage resistance hook (see game_data) and keep its numbers in step with the
    items. Returns 'installed', 'waiting' (the once-a-frame hook it needs is not in place yet),
    'busy' (memory in use, usually by cheat codes) or 'unknown' (the game's code is not what we
    expect).
    """
    hook = _read_word(mem, game_data.RESISTANCE_HOOK)
    if hook not in (game_data.RESISTANCE_HOOK_ORIGINAL, game_data.RESISTANCE_HOOK_BRANCH):
        return "unknown"
    code = game_data.RESISTANCE_CAVE_CODE
    ours = _words(mem, game_data.RESISTANCE_CAVE, len(code)) == code
    if not ours and hook != game_data.RESISTANCE_HOOK_ORIGINAL:   # never jump into code that isn't there
        mem.write_word(game_data.RESISTANCE_HOOK, game_data.RESISTANCE_HOOK_ORIGINAL)
        hook = game_data.RESISTANCE_HOOK_ORIGINAL
    if not frame_hook_ready:
        return "waiting"
    table_size = 4 * game_data.DAMAGE_TYPE_COUNT
    wanted = struct.pack(f">{game_data.DAMAGE_TYPE_COUNT}f", *resistance_factors(levels))
    if not ours:
        if any(mem.read_bytes(game_data.RESISTANCE_CAVE, 4 * len(code))) \
                or any(mem.read_bytes(game_data.RESISTANCE_TABLE, table_size)):
            return "busy"
    current = mem.read_bytes(game_data.RESISTANCE_TABLE, table_size)
    if current != wanted:
        for k in range(game_data.DAMAGE_TYPE_COUNT):
            if current[4 * k:4 * k + 4] != wanted[4 * k:4 * k + 4]:
                mem.write_word(game_data.RESISTANCE_TABLE + 4 * k, struct.unpack_from(">I", wanted, 4 * k)[0])
    if not ours:
        for k, value in enumerate(code):
            mem.write_word(game_data.RESISTANCE_CAVE + 4 * k, value)
    if hook != game_data.RESISTANCE_HOOK_BRANCH:
        mem.write_word(game_data.RESISTANCE_HOOK, game_data.RESISTANCE_HOOK_BRANCH)
        mem.write_word(game_data.RESISTANCE_FLUSHED, 0)     # Dolphin's copy is cleared on the next playing frame
    return "installed"


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

def current_mission(mem):
    """("story", level index) or ("mission", Mission) for what is being played, or None outside a
    level (or in a level the client doesn't know, such as Arcade Custom)."""
    if _read_word(mem, game_data.SETUP_IN_LEVEL) == 0:
        return None
    story = _read_word(mem, game_data.SETUP_STORY_LEVEL)
    if 1 <= story <= len(game_data.STORY_LEVELS):
        return ("story", story - 1)
    if 1 <= story <= game_data.SETUP_STORY_LEVEL_MAX:
        return None
    mission = game_data.MISSION_BY_NUMBER.get(_read_word(mem, game_data.SETUP_MISSION_NUMBER))
    return ("mission", mission) if mission is not None else None


def current_mission_name(mem) -> str | None:
    """The story level or Arcade League / Challenge mission being played, or None outside a level."""
    if _read_word(mem, game_data.SETUP_IN_LEVEL) == 0:
        return None
    playing = current_mission(mem)
    if playing is None:
        story = _read_word(mem, game_data.SETUP_STORY_LEVEL)
        return "a story level" if 1 <= story <= game_data.SETUP_STORY_LEVEL_MAX else "a mission"
    kind, what = playing
    return game_data.STORY_LEVELS[what] if kind == "story" else what.name


def _words(mem, address: int, count: int) -> tuple[int, ...]:
    return struct.unpack(f">{count}I", mem.read_bytes(address, 4 * count))


def ensure_frame_hook(mem) -> str:
    """
    Install the once-a-frame hook used by damage resistances, in-game announcements and Death
    Link: the level-state table's entry for playing points at the routine that clears Dolphin's
    copy of the resistance hook, which carries on into the message code, then the Death Link code,
    then the game's own. Returns 'ready', 'busy' (the memory it needs is in
    use, e.g. by Dolphin's cheat codes) or 'unknown' (the game's data is not what we expect).
    Nothing is changed unless the result is 'ready', except taking the entry back to the game's own.
    """
    entry = _read_word(mem, game_data.STATE_TABLE_PLAYING)
    if entry not in (game_data.STATE_PLAYING_HANDLER, game_data.DEATH_CAVE, game_data.MESSAGE_CAVE,
                     game_data.RESISTANCE_FLUSH):
        return "unknown"
    caves = ((game_data.DEATH_CAVE, game_data.DEATH_CAVE_CODE, game_data.DEATH_TRIGGER, (0, 1, 2),
              game_data.OLD_DEATH_CAVE_CODE),
             (game_data.MESSAGE_CAVE, game_data.MESSAGE_CAVE_CODE, game_data.MESSAGE_STYLE, tuple(range(7)), ()),
             (game_data.RESISTANCE_FLUSH, game_data.RESISTANCE_FLUSH_CODE, game_data.RESISTANCE_FLUSHED, (0, 1), ()))
    states = []
    for address, code, flag, flag_ok, old in caves:
        current = _words(mem, address, len(code))
        flag_value = _read_word(mem, flag)
        if current == code and flag_value in flag_ok:
            states.append("ours")
        elif not any(current) and not flag_value:
            states.append("empty")
        elif old and current[:len(old)] == old and not any(current[len(old):]) and flag_value in (0, 1):
            states.append("empty")                  # an older client's code: replaced
            mem.write_word(flag, 0)
        else:
            states.append("busy")
    if states == ["ours"] * len(caves):
        if entry != game_data.RESISTANCE_FLUSH:
            mem.write_word(game_data.STATE_TABLE_PLAYING, game_data.RESISTANCE_FLUSH)
        return "ready"
    if entry != game_data.STATE_PLAYING_HANDLER:    # never leave the game pointed at something else
        mem.write_word(game_data.STATE_TABLE_PLAYING, game_data.STATE_PLAYING_HANDLER)
    if "busy" in states:
        return "busy"
    mem.write_word(game_data.MESSAGE_DELAY, 0)
    mem.write_word(game_data.MESSAGE_COOLDOWN, 0)
    for (address, code, _flag, _ok, _old), state in zip(caves, states):
        if state == "empty":
            for k, value in enumerate(code):
                mem.write_word(address + 4 * k, value)
    mem.write_word(game_data.STATE_TABLE_PLAYING, game_data.RESISTANCE_FLUSH)
    return "ready"


ensure_death_hook = ensure_frame_hook          # the name older code used


# ---- In-game announcements ----

def encode_message(text: str) -> bytes:
    """Plain ASCII the game's font can show, cut to fit, ending in a zero byte."""
    clean = "".join(ch if " " <= ch <= "~" else "?" for ch in text)
    if len(clean) > game_data.MESSAGE_TEXT_MAX:
        clean = clean[:game_data.MESSAGE_TEXT_MAX - 3] + "..."
    return clean.encode("ascii") + b"\0"


def message_on_screen(mem, style: int) -> bool:
    """True while a message of this style (ours or the game's) is still being shown."""
    size = game_data.MESSAGE_ENTRY_SIZE
    data = mem.read_bytes(game_data.MESSAGE_QUEUE, size * game_data.MESSAGE_QUEUE_ENTRIES)
    for k in range(game_data.MESSAGE_QUEUE_ENTRIES):
        entry = data[k * size:(k + 1) * size]
        if struct.unpack_from(">I", entry, 0)[0] != style:
            continue
        timer, stage_1, stage_2 = (struct.unpack_from(">f", entry, offset)[0] for offset in (
            game_data.MESSAGE_ENTRY_TIMER, game_data.MESSAGE_ENTRY_STAGE_1, game_data.MESSAGE_ENTRY_STAGE_2))
        lasts = stage_1 + stage_2
        if not (-60.0 < timer < 1e6 and 0.0 < lasts < 60.0):     # not a sane entry: ignore it
            continue
        if timer < lasts + game_data.MESSAGE_SPARE_SECONDS:
            return True
    return False


def in_story_cutscene(mem) -> bool:
    return in_story_level(mem) and _read_word(mem, game_data.STORY_CONTROL_FLAG) == 0


class Announcer:
    """
    Shows messages in game, one at a time, while you are playing. Messages that arrive while you
    are not in a level (menus, loading) are dropped; while the game is paused, a level is
    restarting or a story cutscene plays, they wait.
    """

    def __init__(self) -> None:
        from collections import deque
        self.queue = deque(maxlen=30)

    def add(self, text: str, style: int = game_data.MESSAGE_STYLE_LINE) -> None:
        self.queue.append((text, style))

    def poll(self, mem, hook_ready: bool) -> None:
        if _read_word(mem, game_data.SETUP_IN_LEVEL) == 0:
            self.queue.clear()
            if hook_ready and _read_word(mem, game_data.MESSAGE_STYLE):
                mem.write_word(game_data.MESSAGE_STYLE, 0)
            return
        if not hook_ready or not self.queue or _read_word(mem, game_data.MESSAGE_STYLE):
            return                                   # the game hasn't taken the last one yet
        if _read_word(mem, game_data.LEVEL_STATE) != game_data.LEVEL_STATE_PLAYING or in_story_cutscene(mem):
            return
        text, style = self.queue[0]
        if message_on_screen(mem, style):
            return                                   # wait for it to finish
        self.queue.popleft()
        mem.write_bytes(game_data.MESSAGE_TEXT, encode_message(text))
        mem.write_word(game_data.MESSAGE_STYLE, style)


# ---- Award screen ----

def ensure_award_hook(mem) -> str:
    """
    Make the award screen's list builder end in the client's code (see game_data). Returns
    'ready', 'busy' (the memory is in use, e.g. by Dolphin's cheats) or 'unknown' (the game's code
    is not what we expect).
    """
    now = _read_word(mem, game_data.AWARD_HOOK)
    pointer = _read_word(mem, game_data.AWARD_MENU_POINTER)
    if now not in (game_data.AWARD_HOOK_ORIGINAL, game_data.AWARD_HOOK_BRANCH) \
            or pointer not in (game_data.AWARD_MENU_NORMAL, game_data.AWARD_MENU_ROUTINE):
        return "unknown"
    caves = ((game_data.AWARD_CAVE, game_data.AWARD_CAVE_CODE),
             (game_data.AWARD_MENU_ROUTINE, game_data.AWARD_MENU_ROUTINE_CODE))
    ours = all(_words(mem, address, len(code)) == code for address, code in caves)
    if ours and now == game_data.AWARD_HOOK_BRANCH and pointer == game_data.AWARD_MENU_ROUTINE:
        return "ready"
    if not ours:
        if now != game_data.AWARD_HOOK_ORIGINAL:      # never jump into code that isn't there
            mem.write_word(game_data.AWARD_HOOK, game_data.AWARD_HOOK_ORIGINAL)
        if pointer != game_data.AWARD_MENU_NORMAL:
            mem.write_word(game_data.AWARD_MENU_POINTER, game_data.AWARD_MENU_NORMAL)
        if any(mem.read_bytes(game_data.AWARD_CAVE, game_data.AWARD_END - game_data.AWARD_CAVE)) or any(
                mem.read_bytes(game_data.AWARD_HEADING_TEXT, game_data.AWARD_TEXT_END - game_data.AWARD_HEADING_TEXT)):
            return "busy"
        for address, code in caves:
            for k, value in enumerate(code):
                mem.write_word(address + 4 * k, value)
    mem.write_word(game_data.AWARD_HOOK, game_data.AWARD_HOOK_BRANCH)
    mem.write_word(game_data.AWARD_MENU_POINTER, game_data.AWARD_MENU_ROUTINE)
    return "ready"


def ensure_award_heading_fixes(mem) -> int:
    """Point the game's three award headings without a "!" at copies that have one (see
    game_data.AWARD_HEADING_FIXES). Returns how many are in place. Leaves alone anything that is not
    what we expect, and does nothing until the game's text table is loaded."""
    table = _read_word(mem, game_data.AWARD_TEXT_TABLE)
    if not 0x80000000 <= table < 0x81800000 or table % 4:
        return 0
    done = 0
    for text_id, original, fixed, address in game_data.AWARD_HEADING_FIXES:
        entry = table + 4 * text_id
        pointer = _read_word(mem, entry)
        wanted = fixed.encode("ascii") + b"\0"
        size = game_data.AWARD_HEADING_FIX_SIZE
        if pointer == address:
            if mem.read_bytes(address, size)[:len(wanted)] != wanted:
                mem.write_bytes(address, wanted)
            done += 1
            continue
        if not 0x80000000 <= pointer < 0x81800000:
            continue
        if mem.read_bytes(pointer, len(original) + 1) != original.encode("ascii") + b"\0":
            continue                                     # not the text we expect
        here = mem.read_bytes(address, size)
        if any(here) and here[:len(wanted)] != wanted:
            continue                                     # the memory is in use
        mem.write_bytes(address, wanted)
        mem.write_word(entry, address)
        done += 1
    return done


def _award_text(text: str, limit: int) -> bytes:
    raw = "".join(c if 32 <= ord(c) < 127 else "?" for c in text)
    if len(raw) > limit:
        raw = raw[:limit - 3] + "..."
    return raw.encode("ascii") + b"\0"


class AwardScreen:
    """
    The entries the client adds to the award screen after a mission. Everything found or received
    is kept until an award screen has shown it; what that screen showed is cleared when the next
    level starts. Things that arrive after it (e.g. in the menus) wait for the next one.
    A line is (heading, name), each either text or one of the game's own text IDs.
    """

    def __init__(self) -> None:
        # In the order they happened: location IDs we checked, and NetworkItems other players sent us.
        self.found: list = []
        self.written: tuple = ()
        self.was_playing = False
        self.in_memory: list = []      # the found list that the entries in the game's memory came from
        self.shown: list = []          # what the last award screen showed

    def poll(self, mem, hook_ready: bool, front: list, back: list) -> None:
        """front: (heading, name) lines shown before the game's own entries; back: after them."""
        if not hook_ready:
            self.written = ()
            return
        if _read_word(mem, game_data.AWARD_SHOWN):       # the game built its list since the last look
            mem.write_word(game_data.AWARD_SHOWN, 0)
            self.shown = self.in_memory
        playing = (_read_word(mem, game_data.SETUP_IN_LEVEL) != 0
                   and _read_word(mem, game_data.LEVEL_STATE) == game_data.LEVEL_STATE_PLAYING)
        if playing and not self.was_playing and self.shown:
            remaining = list(self.found)                 # a new level: forget what was shown
            for item in self.shown:
                if item in remaining:
                    remaining.remove(item)
            self.found, self.shown = remaining, []
            self.written = ()
            self.in_memory = []
            front, back = [], []                         # the client works out the rest next time
        else:
            self.in_memory = list(self.found)
        self.was_playing = playing
        front = front[:game_data.AWARD_MAX]
        back = back[:game_data.AWARD_MAX - len(front)]
        table = _read_word(mem, game_data.AWARD_TEXT_TABLE)
        if not 0x80000000 <= table < 0x81800000 or table % 4:
            front, back = [], []
        entries = front + back
        wanted = (table, tuple(front), tuple(back))
        if wanted == self.written and _read_word(mem, game_data.AWARD_COUNT) == len(entries):
            return
        mem.write_word(game_data.AWARD_COUNT, 0)
        for k, line in enumerate(entries):
            ids = []
            for part, (text_area, limit, pointer) in zip(line, (
                    (game_data.AWARD_HEADING_TEXT + 32 * k, game_data.AWARD_HEADING_MAX, game_data.AWARD_POINTERS + 8 * k),
                    (game_data.AWARD_NAME_TEXT + 64 * k, game_data.AWARD_NAME_MAX, game_data.AWARD_POINTERS + 8 * k + 4))):
                if isinstance(part, int):                # one of the game's own texts
                    ids.append(part)
                    continue
                mem.write_bytes(text_area, _award_text(part, limit))
                mem.write_word(pointer, text_area)
                ids.append(game_data.award_text_id(table, pointer))
            mem.write_word(game_data.AWARD_ENTRIES + 8 * k, ids[0])
            mem.write_word(game_data.AWARD_ENTRIES + 8 * k + 4, ids[1])
        mem.write_word(game_data.AWARD_FRONT_COUNT, len(front))
        mem.write_word(game_data.AWARD_COUNT, len(entries))
        self.written = wanted


class MissionFailure:
    """Notices the game failing a mission, and can make it fail the one being played."""

    def __init__(self) -> None:
        self.armed = False        # a mission is being played and has not failed yet
        self.caused = False       # the next failure is one we asked for
        self.waiting = 0          # polls left for the game to act on our request
        self.kill_window = 0      # polls left in which a failure came from a kill we asked for
        self.control = 0          # polls in a row with control of the player in a story level

    def poll(self, mem) -> str | None:
        """Call every 0.25 s. Returns the mission's name when it has just failed by itself."""
        if self.waiting:
            self.waiting -= 1
            if not self.waiting and _read_word(mem, game_data.DEATH_TRIGGER):   # the game never took it
                mem.write_word(game_data.DEATH_TRIGGER, 0)
                self.caused = False
                self.kill_window = 0
        if self.kill_window:
            self.kill_window -= 1
            if not self.kill_window:
                self.caused = False         # the kill didn't fail the mission: later failures are real
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

    def fail(self, mem):
        """
        Make a received death land. In a story level the level fails; in an Arcade League mission
        or Challenge the player is killed, and the game decides what that costs. Returns
        ("failed" or "killed", name), or None when there is nothing to do it to.
        """
        name = current_mission_name(mem)
        if (name is None or not self.armed or self.caused or self.in_cutscene(mem)
                or _read_word(mem, game_data.LEVEL_STATE) != game_data.LEVEL_STATE_PLAYING
                or ensure_frame_hook(mem) != "ready"):
            return None
        playing = current_mission(mem)
        kill = playing is not None and playing[0] == "mission"
        if kill and (player_state(mem) is None or player_state(mem)[3] <= 0.0):
            return None                             # already dead
        mem.write_word(game_data.DEATH_TRIGGER, game_data.DEATH_TRIGGER_KILL if kill else game_data.DEATH_TRIGGER_FAIL)
        self.caused = True
        self.waiting = game_data.DEATH_TRIGGER_POLLS
        self.kill_window = game_data.DEATH_KILL_POLLS if kill else 0
        return ("killed" if kill else "failed"), name


class ArcadeDeaths:
    """
    Counts the player's deaths in the Arcade League mission being played. The count starts again
    with every mission, a restart included. A death is reported once the mission has carried on
    for DEATH_CONFIRM_POLLS without failing: a death that fails the mission is a failure instead.
    """

    def __init__(self) -> None:
        self.mission = None
        self.player = 0
        self.deaths = 0
        self.health = None
        self.confirming = 0        # polls left before the death just seen counts

    def _reset(self, mission=None, player: int = 0) -> None:
        self.mission, self.player, self.deaths, self.health, self.confirming = mission, player, 0, None, 0

    def poll(self, mem):
        """Call every 0.25 s. Returns (mission name, deaths so far) when a death counts, else None."""
        playing = current_mission(mem)
        level_state = _read_word(mem, game_data.LEVEL_STATE)
        if (playing is None or playing[0] != "mission" or playing[1].prefix == "Challenge"
                or level_state in game_data.LEVEL_STATE_RELOADING):
            self._reset()
            return None
        state = player_state(mem)
        if state is None:
            return None
        player, _armour, _full, health = state
        if playing[1] is not self.mission or player != self.player:
            self._reset(playing[1], player)
        if _read_word(mem, game_data.SETUP_FLAGS_5C) & game_data.SETUP_FAILED_FLAG:
            self.confirming = 0                    # the mission failed: that is sent as a failure
            self.health = health
            return None
        if self.health is not None and self.health > 0.0 >= health:
            self.confirming = game_data.DEATH_CONFIRM_POLLS
        self.health = health
        if not self.confirming:
            return None
        self.confirming -= 1
        if self.confirming:
            return None
        self.deaths += 1
        return playing[1].name, self.deaths


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


# ---- Archipelago Shop ----

def trophy_points(levels: dict[str, int]) -> int:
    """Points for the trophies held: a better trophy counts the ones below it too."""
    return sum(sum(game_data.TROPHY_POINTS[:level]) for level in levels.values())


def story_points(mem) -> int | None:
    """Points for story levels finished, per difficulty (finishing on Hard also sets the easier
    ones). None with no profile loaded."""
    words = _story_words(mem)
    if words is None:
        return None
    mask = (1 << len(game_data.STORY_LEVELS)) - 1
    return sum(bin(bits & mask).count("1") * points for bits, points in zip(words, game_data.STORY_POINTS))


class KillCounter:
    """Counts player 1's kills while a level is being played, from the match's own kill count
    (which starts again at 0 in every level, restart and retry)."""

    def __init__(self) -> None:
        self.last: int | None = None

    def poll(self, mem) -> int:
        """New kills since the last call."""
        playing = (_read_word(mem, game_data.SETUP_IN_LEVEL) != 0
                   and _read_word(mem, game_data.LEVEL_STATE) == game_data.LEVEL_STATE_PLAYING)
        if not playing:
            self.last = None
            return 0
        value = struct.unpack(">f", mem.read_bytes(game_data.PLAYER_KILLS, 4))[0]
        kills = int(value) if 0 <= value < 100000 else 0
        if self.last is None or kills < self.last:
            self.last = kills
            return 0
        new, self.last = kills - self.last, kills
        return new


def _shop_text(text: str, size: int) -> bytes:
    """Plain ASCII that fits; a text ending in " - N Points" keeps that ending, the name is cut."""
    clean = "".join(c if " " <= c <= "~" else "?" for c in text)
    if len(clean) > size - 1:
        cut = clean.rfind(" - ")
        tail = clean[cut:] if cut > 0 and clean.endswith(" Points") else ""
        clean = clean[:size - 1 - len(tail) - 3].rstrip() + "..." + tail
    return clean.encode("ascii") + b"\0"


class ShopMenu:
    """
    The View Cutscenes menu as the shop (see game_data). The client says what each row should
    show and what buying it would switch it to (rows()); this keeps the game's memory in step
    and reports rows bought with A (poll()).

    Each row has two text buffers: `live` is the one the menu is showing (and the next opening
    will show), the other holds the text A switches the row to. A row whose text has to change
    while it is on screen gets the new text in its other buffer, which becomes the live one; the
    menu shows it from its next opening, and until then A does nothing on that row ("waiting").
    """

    def __init__(self) -> None:
        self.installed = False
        self.live = [2 * k for k in range(game_data.SHOP_ROWS)]
        self.live_text: list[str | None] = [None] * game_data.SHOP_ROWS
        self.other_text: list[str | None] = [None] * game_data.SHOP_ROWS
        self.waiting = [False] * game_data.SHOP_ROWS
        self.opened: int | None = None
        self.written: dict[int, bytes] = {}
        self.saved_entries: dict[int, int] = {}
        self.just_opened = False          # the menu was opened (built) since the last update()

    # -- memory --
    def _write_text(self, mem, n: int, text: str) -> None:
        data = _shop_text(text, game_data.shop_text_size(n))
        if self.written.get(n) != data:
            mem.write_bytes(game_data.shop_text_address(n), data)
            self.written[n] = data

    @staticmethod
    def _ours(mem) -> bool:
        return (_words(mem, game_data.SHOP_WRAPPER, len(game_data.SHOP_WRAPPER_CODE)) == game_data.SHOP_WRAPPER_CODE
                and _words(mem, game_data.SHOP_CALLBACK, len(game_data.SHOP_CALLBACK_CODE))
                == game_data.SHOP_CALLBACK_CODE)

    def install(self, mem) -> str:
        """'installed', 'waiting' (the game's text is not loaded yet), 'busy' or 'unknown'."""
        pointer = _read_word(mem, game_data.SHOP_MENU_POINTER)
        if pointer not in (game_data.SHOP_MENU_BUILDER, game_data.SHOP_WRAPPER):
            return "unknown"
        for address, game, ours in game_data.SHOP_CODE_CHANGES:
            if _read_word(mem, address) not in (game, ours):
                return "unknown"
        table = _read_word(mem, game_data.AWARD_TEXT_TABLE)
        if not 0x80000000 <= table < 0x81800000 or table % 4:
            return "waiting"
        ours = self._ours(mem)
        if self.installed and ours and pointer == game_data.SHOP_WRAPPER:
            self._keep_names(mem, table)
            return "installed"
        if not ours:
            if pointer == game_data.SHOP_WRAPPER:          # never start code that isn't there
                mem.write_word(game_data.SHOP_MENU_POINTER, game_data.SHOP_MENU_BUILDER)
            if any(mem.read_bytes(game_data.SHOP_WRAPPER, game_data.SHOP_AREA_END - game_data.SHOP_WRAPPER)):
                return "busy"
        self.__init__()                                    # a fresh start (e.g. the game was restarted)
        for address, code in ((game_data.SHOP_WRAPPER, game_data.SHOP_WRAPPER_CODE),
                              (game_data.SHOP_CALLBACK, game_data.SHOP_CALLBACK_CODE)):
            for k, value in enumerate(code):
                mem.write_word(address + 4 * k, value)
        mem.write_word(game_data.SHOP_PICK, 0)
        for k in range(game_data.SHOP_ROWS):
            mem.write_word(game_data.SHOP_AFFORD + 4 * k, 0)
            self._write_text(mem, self.live[k], "")
            mem.write_word(game_data.SHOP_SLOTS + 4 * k, game_data.shop_text_address(self.live[k]))
            mem.write_word(game_data.SHOP_NEXT_TEXT + 4 * k, game_data.shop_text_address(self.live[k] ^ 1))
        self._write_text(mem, game_data.SHOP_TITLE, "Archipelago Shop")
        self._write_text(mem, game_data.SHOP_MENU, game_data.SHOP_NEW_TEXT["menu"])
        self._write_text(mem, game_data.SHOP_OPTIONS, game_data.SHOP_NEW_TEXT["options"])
        for k, n in enumerate((game_data.SHOP_TITLE, game_data.SHOP_MENU, game_data.SHOP_OPTIONS)):
            mem.write_word(game_data.SHOP_SLOTS + 4 * (game_data.SHOP_ROWS + k), game_data.shop_text_address(n))
        for address, _game, value in game_data.SHOP_CODE_CHANGES:
            mem.write_word(address, value)
        for k in range(game_data.SHOP_ROWS):
            mem.write_word(game_data.SHOP_CUTSCENE_TABLE + 16 * k + 12,
                           game_data.award_text_id(table, game_data.SHOP_SLOTS + 4 * k))
        self._keep_names(mem, table)
        self.opened = _read_word(mem, game_data.SHOP_OPENED)
        mem.write_word(game_data.SHOP_MENU_POINTER, game_data.SHOP_WRAPPER)
        self.installed = True
        return "installed"

    def _keep_names(self, mem, table: int) -> None:
        """Point the title, "View Cutscenes" and "Options" at our texts (again if the game reloaded
        its text). Only an entry still holding the game's own text is changed."""
        for n, key in ((game_data.SHOP_TITLE, "title"), (game_data.SHOP_MENU, "menu"),
                       (game_data.SHOP_OPTIONS, "options")):
            entry = table + 4 * game_data.SHOP_TEXT_IDS[key]
            now = _read_word(mem, entry)
            ours = game_data.shop_text_address(n)
            if now == ours or not 0x80000000 <= now < 0x81800000:
                continue
            original = game_data.SHOP_ORIGINAL_TEXT[key].encode("ascii") + b"\0"
            if mem.read_bytes(now, len(original)) == original:
                mem.write_word(entry, ours)

    # -- rows --
    def update(self, mem, title: str, rows: list[tuple[str, str, bool]]) -> list[tuple[int, bool]]:
        """
        title: the menu's title. rows: for each row, (what it shows now, what buying it switches it
        to, whether A may buy it now). Returns the A presses since the last call as (row, bought).
        """
        if not self.installed:
            return []
        opened = _read_word(mem, game_data.SHOP_OPENED)
        self.just_opened = opened != self.opened
        if self.just_opened:                               # rebuilt from the live buffers
            self.opened = opened
            self.waiting = [False] * game_data.SHOP_ROWS
        picks = []
        picked = _read_word(mem, game_data.SHOP_PICK)
        if picked:
            mem.write_word(game_data.SHOP_PICK, 0)
            k = (picked & 0xFF) - 1
            if 0 <= k < game_data.SHOP_ROWS:
                bought = not picked & 0x100
                if bought:                                 # the game switched the row to its other buffer
                    self.live[k] ^= 1
                    self.live_text[k], self.other_text[k] = self.other_text[k], None
                picks.append((k, bought))
        self._write_text(mem, game_data.SHOP_TITLE, title)
        just_bought = {k for k, bought in picks if bought}
        for k, (now, after, can_buy) in enumerate(rows):
            if k in just_bought:                           # the rows given were worked out before it
                mem.write_word(game_data.SHOP_SLOTS + 4 * k, game_data.shop_text_address(self.live[k]))
                continue
            if now != self.live_text[k]:
                # It has to change on screen: from the next opening, and no buying until then.
                was_shown = self.live_text[k] is not None
                self.live[k] ^= 1
                self._write_text(mem, self.live[k], now)
                self.live_text[k], self.other_text[k] = now, None
                mem.write_word(game_data.SHOP_SLOTS + 4 * k, game_data.shop_text_address(self.live[k]))
                if was_shown:
                    self.waiting[k] = True
            other = self.live[k] ^ 1
            if not self.waiting[k] and self.other_text[k] != after:
                self._write_text(mem, other, after)
                self.other_text[k] = after
                mem.write_word(game_data.SHOP_NEXT_TEXT + 4 * k, game_data.shop_text_address(other))
            ok = int(can_buy and not self.waiting[k] and self.other_text[k] == after)
            if _read_word(mem, game_data.SHOP_AFFORD + 4 * k) != ok:
                mem.write_word(game_data.SHOP_AFFORD + 4 * k, ok)
        return picks


def hide_shop_awards(mem, item_names: set[str]) -> None:
    """Mark these items (owned, bought in the shop) as already unlocked in the award screen's
    snapshot, so the game doesn't list them as new (see game_data.NATIVE_AWARD_SLOTS)."""
    for name in item_names:
        for address in game_data.NATIVE_AWARD_SLOTS.get(name, ()):
            _set_word(mem, address, 1)
