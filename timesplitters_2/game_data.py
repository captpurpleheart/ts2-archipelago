"""
Game facts for TimeSplitters 2 (GameCube, NTSC-U "GTSE4F", played through Dolphin).

Everything learned from the memory dumps and in-game tests goes in THIS file, so the world
(generation side) and the client (game side) always agree.

Scope: the 10 story levels and their objectives, the 45 Arcade League missions and 21 Challenges (66 in total), the
126 characters,
9 cheats, the 5 Silly Hats,
16 arcade maps, 16 arcade game modes
and 26 arcade weapons.

TROPHIES    The loaded profile (pointer at 0x80468DC8) holds one bit per mission for each of four
            trophy grades. A Platinum sets all four, so the best grade is the highest one set.

UNLOCKS     The game decides whether something is unlocked by evaluating a 5-word "condition".
            Word 0 is the type and the game jumps to the code for that type through a table.
            The client points type 5 at a small routine of its own and gives every group a type 5
            condition. The routine answers "is this mission playable?" from a list of 66 bytes,
            and "is this group open?" from word 1 of the group's condition. No existing game code
            is changed and nothing is written to the save.
"""
from dataclasses import dataclass

GAME_NAME = "TimeSplitters 2"
WORLD_VERSION = "1.2.1"     # keep in step with archipelago.json

GAME_ID_ADDRESS = 0x80000000
GAME_ID: bytes | None = b"GTSE4F"

# Archipelago item/location IDs must be unique within this game. IDs come from the game's own
# mission numbers, so they stay the same if GROUPS is ever reordered.
BASE_ID = 7_720_000

TIERS = ("Bronze", "Silver", "Gold", "Platinum")   # trophy grades 1-4

# (prefix, group, ((mission, the game's mission number), ...)) in the game's menu order.
# Group number = position in this list (the game's own group numbers 0-21).
GROUPS: tuple[tuple[str, str, tuple[tuple[str, int], ...]], ...] = (
    ('Challenge', 'Glass Smash', (('Pane in the Neck', 0), ('Bricking it', 1), ('Stain Removal', 2))),
    ('Challenge', 'Behead The Undead', (('Fight Off The Living Dead', 15), ("Sergio's Last Stand", 17), ('Day of the Dammed', 16))),
    ('Challenge', 'Infiltration', (('Silent but Deadly', 3), ('Trouble at the Docks', 4), ('Escape from NeoTokyo', 5))),
    ('Challenge', 'Banana Chomp', (('Gone Bananas', 6), ('Monkey Business', 7), ('Playing With Fire', 8))),
    ('Challenge', 'Cut-out Shoot-out', (("Take 'em Down", 9), ('Fall Out', 10), ('Pick Yer Piece', 11))),
    ('Challenge', "TimeSplitters 'Story' Classic", (('Badass Bus Pass Impasse', 13), ('But Where do the Batteries Go?', 14), ('Hit Me Baby One Morgue Time', 12))),
    ('Challenge', 'Monkeying Around', (('Simian Shootout', 18), ('Monkey Mayhem', 19), ('Dam Bursters', 20))),
    ('AL', 'Beginners Series', (('Adios Amigos!', 21), ('Casualty', 22), ('Top Shot', 23))),
    ('AL', 'Mode Madness', (('Chastity Chased', 25), ('Shrinking from the Cold', 24), ('Scrap Metal', 26))),
    ('AL', "It's a Blast", (('Night Shift', 27), ('Spoils of War', 28), ('Demolition Derby', 29))),
    ('AL', 'Too Hot to Handle', (('Monkey Immolation', 30), ('Disco Inferno', 32), ('Burns Department', 31))),
    ('AL', 'Team Series A', (('Club Soda', 33), ('Station Stand', 34), ('Men In Gray', 35))),
    ('HL', 'Maximus', (('Cold Corpse Caper', 41), ('Killer Queen', 40), ('R109 Beta', 39))),
    ('HL', 'Elimination Series', (('Baking for the Taking', 42), ('Brace Yourself', 43), ('Starship Whoopers', 44))),
    ('HL', "Burns 'n' Bangs", (('Chinese Burns', 46), ('Snow Business', 45), ('Rocket Man', 47))),
    ('HL', 'Outnumbered but Never Outpunned!', (('Someone Has Got to Pay...', 48), ('Time to Split', 49), ("Can't Handle This", 50))),
    ('HL', 'Team Series B', (('Hack a Hacker', 36), ('Rice Cracker Rush', 37), ('Superfly Lady', 38))),
    ('EL', 'One Shot Thrills', (('Babes in the Woods', 51), ('Double Bill', 52), ('Nikki Jinki Bricky', 53))),
    ('EL', 'Duel Meaning', (("If I'm Ugly - You Smell!", 58), ('Golem Guru', 59), ('Golden Thighs', 57))),
    ('EL', 'Frantic Series', (("Hangar Hat's Off!", 61), ("Can't Please Everyone...", 60), ('Big Top Blowout', 62))),
    ('EL', 'Team Series C', (('Bags of Fun', 54), ("They're Not Pets!", 55), ('Nice Threads', 56))),
    ('EL', 'Sincerest Form of Flattery', (('Aztec the Dino Hunter', 63), ('Half Death', 64), ('Dead Fraction', 65))),
)


@dataclass(frozen=True)
class Mission:
    number: int                # the game's mission number (0-65); IDs and trophy bits derive from it
    name: str
    prefix: str                # "AL", "HL", "EL" or "Challenge"
    group: str
    group_number: int

    @property
    def item_name(self) -> str:
        return f"{self.prefix} - {self.group} - {self.name}"


MISSIONS: tuple[Mission, ...] = tuple(
    Mission(number=number, name=name, prefix=prefix, group=group, group_number=g)
    for g, (prefix, group, missions) in enumerate(GROUPS)
    for name, number in missions
)
MISSION_COUNT = 66
assert sorted(m.number for m in MISSIONS) == list(range(MISSION_COUNT))

# ---- Save data (the loaded profile) ----
PROFILE_POINTER = 0x80468DC8
TROPHY_FLAGS_OFFSET = 0xBE0        # + 0x10 per grade; bit = mission number, 32 per word
TROPHY_GRADE_STRIDE = 0x10

# ---- Groups ----
GROUP_TABLE = 0x8031C8C8           # 22 records of 56 bytes
GROUP_STRIDE = 56
GROUP_COUNT_OFFSET = 0x04          # number of missions in the group
GROUP_MISSIONS_OFFSET = 0x08       # their mission numbers
GROUP_CONDITION_OFFSET = 0x24      # the group's 5-word condition


def group_condition_address(group_number: int) -> int:
    return GROUP_TABLE + GROUP_STRIDE * group_number + GROUP_CONDITION_OFFSET


# ---- The mission lock ----
CONDITION_LOCKED = 0
CONDITION_HOOKED = 5               # the type the client takes over
CONDITION_MAX = 6
JUMP_ENTRY = 0x80314DD8            # the game's jump table entry for condition type 5
JUMP_NORMAL = 0x8013E930           # where it normally points
ROUTINE = 0x80002E00               # empty low memory (only when Dolphin's cheat codes are off)
MISSION_TABLE = 0x80002E40         # 66 bytes, 1 = playable
ROUTINE_AREA = 0x90                # bytes that must be empty before the routine is written
ROUTINE_CODE = (
    0x80010044,                    # lwz   r0, 0x44(r1)     who asked for this condition?
    0x3C808013,                    # lis   r4, 0x8013
    0x6084EC64,                    # ori   r4, r4, 0xEC64   0x8013EC64 = the game's mission check
    0x7C002040,                    # cmplw r0, r4
    0x4182000C,                    # beq   mission
    0x807F0004,                    # lwz   r3, 4(r31)       anyone else: answer = word 1 (group open?)
    0x4813BD54,                    # b     0x8013EB6C       normal way out of the condition function
    0x3C808000,                    # mission: lis r4, 0x8000
    0x60842E40,                    # ori   r4, r4, 0x2E40   r4 = MISSION_TABLE
    0x7C64E0AE,                    # lbzx  r3, r4, r28      answer = list[mission number]
    0xBA61000C,                    # lmw   r19, 0xC(r1)     leave the condition function...
    0x38210040,                    # addi  r1, r1, 0x40
    0x4813BEE0,                    # b     0x8013ED10       ...and the mission check, with that answer
)

# ---- Characters ----
# 127 unlock entries of 0x20 bytes from 0x80325678: the character's number at +0 and its 5-word
# condition at +0xC. Names come from the character definitions (0x44 bytes each from 0x8032BD60,
# name text ID first), matched by character number. Entry order is the game's menu order.
# The last entry (Consultant, always locked) is left alone.
CHARACTER_TABLE = 0x80325678
CHARACTER_STRIDE = 0x20
CHARACTER_CONDITION_OFFSET = 0x0C
# (name, the game's character number), in table order
CHARACTER_ENTRIES: tuple[tuple[str, int], ...] = (
    ('Sgt Cortez', 0x6A), ('Corp Hart', 0x7F), ('Ilsa Nadir', 0x2E),
    ('Gregor Lenko', 0x6F), ('Jake Fenton', 0x44), ('Lady Jane', 0x45),
    ('Viola', 0x0E), ('Mr Underwood', 0x85), ('Hank Nova', 0x6B),
    ('Candi Skyler', 0x7D), ('Ghost', 0x64), ('Chastity', 0x3D),
    ('Elijah Jones', 0x06), ('Ramona Sosa', 0x05), ('Harry Tipper', 0x72),
    ('Kitten Celeste', 0x6C), ('Captain Ash', 0x61), ('Jungle Queen', 0x01),
    ('Gretel Mk II', 0x32), ('R-109', 0x84), ('Monkey', 0x02),
    ('Hybrid Mutant', 0x2D), ('Big Tony', 0x0D), ('Jacque de la Morte', 0x68),
    ('Ozor Mox', 0x7B), ('Sadako', 0x63), ('The Colonel', 0x00),
    ('Khallos', 0x75), ('Stone Golem', 0x0F), ('Machinist', 0x30),
    ('Reaper Splitter', 0x37), ('Hector Baboso', 0x07), ('Lean Molly', 0x0B),
    ('Dr. Peabody', 0x74), ('Crypt Zombie', 0x87), ('ChassisBot', 0x31),
    ('SentryBot', 0x91), ('Meezor Mox', 0x7C), ('Male Trooper', 0x83),
    ('Female Trooper', 0x82), ('Crispin', 0x8D), ('Undead Priest', 0x33),
    ('Louie Bignose', 0x34), ('Slick Tommy', 0x41), ('Jimmy Needles', 0x42),
    ('Accountant', 0x5A), ('Lawyer', 0x5B), ('Braces', 0x0C),
    ('Maiden', 0x38), ('Jo-Beth Casey', 0x3E), ('Riot Officer', 0x66),
    ('Barby Gimp', 0x65), ('Jebediah Crump', 0x09), ('Venus Starr', 0x71),
    ('Mikey Two-guns', 0x70), ('Jared Slim', 0x08), ('Ample Sally', 0x0A),
    ('Henchman', 0x73), ('Cyberfairy', 0x5F), ('Kypriss', 0x79),
    ('Mister Giggles', 0x78), ('Marco the Snitch', 0x35), ('Hatchet Sal', 0x43),
    ('Changeling', 0x39), ('The Hunchback', 0x69), ('Sewer Zombie', 0x36),
    ('Gargoyle', 0x86), ('The Cropolite', 0x81), ('Beetleman', 0x95),
    ('Dark Henchman', 0x90), ('High Priest', 0x77), ('Wood Golem', 0x22),
    ('Aztec Warrior', 0x76), ('The Master', 0x3B), ('Krayola', 0x3C),
    ('Milkbaby', 0x62), ('Drone Splitter', 0x80), ('Baby Drone', 0x8E),
    ('Scourge Splitter', 0x7E), ('R One-Oh-Seven', 0x60), ('Feeder Zombie', 0x5D),
    ('Stumpy', 0x6E), ('Lola Varuska', 0x88), ('Nikki', 0x89),
    ('Jinki', 0x8A), ('Ringmistress', 0x8B), ('Calamari', 0x8F),
    ('Snowman', 0x8C), ('Bear', 0x6D), ('Leo Krupps', 0x40),
    ('Sergio', 0x94), ('Mischief', 0x96), ('The Impersonator', 0x97),
    ('Badass Cyborg', 0x98), ('Chinese Chef', 0x99), ('Duckman Drake', 0x9A),
    ('Gingerbread Man', 0x9B), ('Insect Mutant', 0x9C), ('Robofish', 0x9D),
    ('Dinosaur', 0x7A), ('Handyman', 0x1E), ('Nikolai', 0x12),
    ('Private Sand', 0x13), ('Private Grass', 0x14), ('Private Coal', 0x15),
    ('Private Poorly', 0x16), ('Sgt Rock', 0x17), ('Sgt Shivers', 0x18),
    ('Sgt Wood', 0x19), ('Sgt Shock', 0x1A), ('Sgt Slate', 0x1B),
    ('Lt Frost', 0x1C), ('Lt Wild', 0x1D), ('Lt Shade', 0x1F),
    ('Lt Bush', 0x20), ('Lt Chill', 0x21), ('Trooper White', 0x23),
    ('Trooper Brown', 0x24), ('Trooper Black', 0x25), ('Trooper Green', 0x26),
    ('Trooper Grey', 0x27), ('Capt Snow', 0x28), ('Capt Sand', 0x29),
    ('Capt Night', 0x2A), ('Capt Forest', 0x2B), ('Capt Pain', 0x2C),
)
# (name, condition address, character number)
CHARACTERS: tuple[tuple[str, int, int], ...] = tuple(
    (name, CHARACTER_TABLE + CHARACTER_STRIDE * entry + CHARACTER_CONDITION_OFFSET, number)
    for entry, (name, number) in enumerate(CHARACTER_ENTRIES)
)

# The game's four default characters (Sgt Cortez, Corp Hart, Ilsa Nadir, Gregor Lenko). On
# entering Arcade, a player whose selected character is locked is given the next one of these.
# If that one is locked too, the character select screen steps through character numbers looking
# for an unlocked one, and crashes on the first number that has no unlock entry. The client
# keeps this table filled with characters you own, so the search never has to step.
DEFAULT_CHARACTERS = 0x80326658
DEFAULT_CHARACTER_COUNT = 4
CHARACTER_NUMBER_LIMIT = 162       # character numbers run 0-161

# ---- Cheats ----
# 13 entries of 0x1C bytes from 0x80358AE8: name text ID (16 bits) at +0, condition at +8.
# Gun Sounds (entry 0) and Skating (entry 7) are always locked in the game and Silly Hats (entry
# 12) is always unlocked; those three are left alone. Paintball's own condition is type 5, the
# type the mission lock takes over, which is harmless because the client overwrites it.
CHEAT_TABLE = 0x80358AE8
CHEAT_STRIDE = 0x1C
CHEAT_CONDITION_OFFSET = 0x08
# (name, entry number, name text ID)
CHEAT_ENTRIES: tuple[tuple[str, int, int], ...] = (
    ("Big Heads", 1, 0x58B), ("Small Heads", 2, 0x58C), ("Big Hands", 3, 0x58D),
    ("Paintball", 5, 0x58F), ("Fat Characters", 6, 0xA51),
    ("All Characters Cloaked", 8, 0xA52), ("Slow Motion Deaths", 9, 0x59B),
    ("Cardboard Characters", 10, 0xA53), ("Rotating Heads", 11, 0xA54),
)
# (name, condition address, entry number)
CHEATS: tuple[tuple[str, int, int], ...] = tuple(
    (name, CHEAT_TABLE + CHEAT_STRIDE * entry + CHEAT_CONDITION_OFFSET, entry)
    for name, entry, _text in CHEAT_ENTRIES
)
# ---- Silly Hats ----
# The Silly Hats cheat itself is always unlocked; each hat has its own bare 5-word condition,
# 20 bytes apart from 0x80314D60, in the order of the hat names (text IDs 0xA4C-0xA50).
HAT_TABLE = 0x80314D60
HAT_STRIDE = 20
HAT_NAMES: tuple[str, ...] = ("Chef", "Big Ears", "Pirate", "Roman", "Viking")
# (name, condition address, hat number)
HATS: tuple[tuple[str, int, int], ...] = tuple(
    (name, HAT_TABLE + HAT_STRIDE * k, k) for k, name in enumerate(HAT_NAMES)
)
# Infinite Ammo (entry 4, normally the last story level on Hard) is not an item, by the author's
# choice. The client keeps it locked so it cannot be earned the normal way either.
LOCKED_CHEATS: tuple[tuple[str, int, int], ...] = (
    ("Infinite Ammo", CHEAT_TABLE + CHEAT_STRIDE * 4 + CHEAT_CONDITION_OFFSET, 0x58E),
)
CONDITION_UNLOCKED = 1
# Type 0 does not mean "locked" for characters and cheats: it means "this entry does not exist".
# The game counts the entries whose type is not 0 and then walks that many, so writing 0 removes
# squares from the Gallery and character select and crashes Arcade Custom. They are locked
# instead with an ordinary condition that can never be met: a trophy on mission number 95 (there
# are only 66, so that bit of the profile is never set).
NEVER_MET = (4, 95, 4)             # type 4 (one mission has a trophy), mission 95, grade 4


def character_item_name(name: str) -> str:
    return name


def cheat_item_name(name: str) -> str:
    return f"{name} Unlock"


def hat_item_name(name: str) -> str:
    return f"{name} Hat Unlock"


# ---- Arcade maps and game modes ----
# Maps: 20 entries of 0x30 bytes from 0x8031DC88: name text ID at +0, map number at +4, condition
# at +0x1C. Dam (17) and Wild West (18) are never offered (type 0) and "tileset" (19) is the
# MapMaker tileset; those are left alone. Two entries are named "Scrapyard": entry 6 (map number
# 65, normally unlocked by the Mode Madness series) is the regular arcade map. Entry 5 (map number
# 46) is never seen in the menu as an unlockable and is believed to be the Assault version; it
# is left alone too.
MAP_TABLE = 0x8031DC88
MAP_STRIDE = 0x30
MAP_CONDITION_OFFSET = 0x1C
# (item name, entry number, name text ID)
MAP_ENTRIES: tuple[tuple[str, int, int], ...] = (
    ("Mexican Mission", 0, 0x69E), ("Ice Station", 1, 0x699), ("Hospital", 2, 0x6A1),
    ("Training Ground", 3, 0x6A6), ("Aztec", 4, 0x693),
    ("Scrapyard", 6, 0x6A2), ("Nightclub", 7, 0x69F), ("Hangar", 8, 0x696),
    ("Robot Factory", 9, 0x69D), ("Ufopia", 10, 0x6A5), ("Chinese", 11, 0x692), ("Chasm", 12, 0x6A7),
    ("Streets", 13, 0x68F), ("Compound", 14, 0x68E), ("Site", 15, 0x690), ("Circus", 16, 0x6A3),
)
# (name, condition address, entry number)
MAPS: tuple[tuple[str, int, int], ...] = tuple(
    (name, MAP_TABLE + MAP_STRIDE * entry + MAP_CONDITION_OFFSET, entry) for name, entry, _text in MAP_ENTRIES
)
# Game modes: one bare 5-word condition per mode, 20 bytes apart from 0x8031DB0C, in the order of
# the mode table at 0x8031D8F8 (0x1C bytes per mode, name text ID in the high half of +0x14).
# Modes 0-2 (MapMaker Preview, One on One, Story) are not arcade choices and are left alone.
MODE_CONDITIONS = 0x8031DB0C
MODE_CONDITION_STRIDE = 20
MODE_TABLE = 0x8031D8F8
MODE_STRIDE = 0x1C
# (name, mode number, name text ID)
MODE_ENTRIES: tuple[tuple[str, int, int], ...] = (
    ("Deathmatch", 3, 0x5B2), ("Team Deathmatch", 4, 0x5BC), ("Capture the Bag", 5, 0x5B0),
    ("BagTag", 6, 0x5AE), ("Elimination", 7, 0x5BE), ("Shrink", 8, 0x5CD), ("Vampire", 9, 0x5CF),
    ("Thief", 10, 0x5C5), ("Flame Tag", 11, 0x5BA), ("Virus", 12, 0x5C0), ("Regeneration", 13, 0x5C2),
    ("Leech", 14, 0x5CB), ("Zones", 15, 0x5B4), ("Assault", 16, 0x5B8), ("Gladiator", 17, 0x5C9),
    ("Monkey Assistant", 18, 0x5D1),
)
# (name, condition address, mode number)
MODES: tuple[tuple[str, int, int], ...] = tuple(
    (name, MODE_CONDITIONS + MODE_CONDITION_STRIDE * number, number) for name, number, _text in MODE_ENTRIES
)


# Assault mode has its own map list (0x8013E4C4): Training Ground is always offered, Hangar and the
# Assault Scrapyard each have a bare condition. The map's item unlocks both versions.
# (map item name, condition address of its Assault version)
ASSAULT_MAPS: tuple[tuple[str, int], ...] = (
    ("Hangar", 0x80314D38),
    ("Scrapyard", 0x80314D4C),
)
# Training Ground's Assault version has no condition: the check says "map 3: yes" in code, with
# `cmpwi r3, 3` at 0x8013E4DC. The client changes that to `cmpwi r3, -1` (never true, so the
# answer is "no") while the Training Ground item is missing. As with the story lock, the map menu
# is started through a small routine that first runs icbi on the changed code, so Dolphin picks
# up the change at any time. The menu's start address is the fifth word of its screen record.
TRAINING_GROUND_ASSAULT_CHECK = 0x8013E4DC
TRAINING_GROUND_OPEN = 0x2C030003  # cmpwi r3, 3   (the game's own instruction)
TRAINING_GROUND_SHUT = 0x2C03FFFF  # cmpwi r3, -1
MAP_MENU_POINTER = 0x80326918
MAP_MENU_NORMAL = 0x8019E39C
MAP_MENU_ROUTINE = 0x80002EE0
MAP_MENU_ROUTINE_CODE = (
    0x3D808014, 0x398CE4C0,        # lis r12, 0x8014 / addi r12, r12, -0x1B40   (0x8013E4C0)
    0x7C0067AC,                    # icbi 0, r12
    0x398C0020, 0x7C0067AC,        # addi r12, r12, 0x20 / icbi 0, r12
    0x4C00012C,                    # isync
    0x4819B4A4,                    # b 0x8019E39C   the game's map menu
)
MAP_MENU_AREA_END = 0x80002F00

# ---- Arcade weapons ----
# 42 entries of 36 bytes from 0x80311E70, one per weapon the custom weapon set editor can offer
# (checked by 0x8013EE80). Entry N goes with weapon definition N (72 bytes each from 0x80312458,
# name text ID first). Condition at +0x10. Only the Brick has a real unlock (Bricking it on
# Silver); the rest are always on, apart from entries the game never offers (type 0: Silenced
# Luger and its (x2), Digital Camera, Temporal Uplink, Gun Powder, a second Scifi Handgun and
# spare Unarmed entries) which are left alone, as is Unarmed (entry 0).
WEAPON_TABLE = 0x80311E70
WEAPON_STRIDE = 36
WEAPON_CONDITION_OFFSET = 0x10
WEAPON_DEFINITIONS = 0x80312458
WEAPON_DEFINITION_STRIDE = 72
# (item name, entry number, entry of its (x2) version or None, name text ID)
WEAPON_ENTRIES: tuple[tuple[str, int, int | None, int], ...] = (
    ("Silenced Pistol", 1, 2, 0x631), ("Luger Pistol", 5, 6, 0x635), ("Garrett Revolver", 7, 8, 0x637),
    ("Tactical 12-Gauge", 9, None, 0x64C), ("Minigun", 10, None, 0x654), ("Sniper Rifle", 11, None, 0x639),
    ("Vintage Rifle", 12, None, 0x63A), ("Flamethrower", 13, None, 0x63B), ("Fire Extinguisher", 14, None, 0x63C),
    ("Soviet S47", 15, 16, 0x63D), ("ElectroTool", 17, None, 0x63F), ("Scifi Handgun", 18, None, 0x640),
    ("Rocket Launcher", 19, None, 0x641), ("Homing Launcher", 20, None, 0x642), ("Lasergun", 21, None, 0x643),
    ("Plasma Autorifle", 22, None, 0x644), ("Grenade Launcher", 23, None, 0x645),
    ("Proximity Mine", 24, None, 0x646), ("Remote Mine", 25, None, 0x647), ("Timed Mine", 26, None, 0x648),
    ("TNT", 27, None, 0x649), ("Tommy Gun", 28, 29, 0x64A), ("SBP90 Machinegun", 30, 31, 0x64D),
    ("Shotgun", 32, 33, 0x64F), ("Brick", 34, None, 0x651), ("Crossbow", 37, None, 0x653),
)


def weapon_condition_address(entry: int) -> int:
    return WEAPON_TABLE + WEAPON_STRIDE * entry + WEAPON_CONDITION_OFFSET


def weapon_item_name(name: str) -> str:
    return f"{name} Unlock"


def map_item_name(name: str) -> str:
    return f"{name} Map Unlock"


def mode_item_name(name: str) -> str:
    return f"{name} Mode Unlock"


# ---- Story Mode ----
# The game's own level order (the story level table at 0x8031D768).
STORY_LEVELS: tuple[str, ...] = (
    "1990 Siberia", "1932 Chicago", "1895 Notre Dame", "2280 Return to Planet X", "2019 NeoTokyo",
    "1853 Wild West", "1972 Atom Smasher", "1920 Aztec Ruins", "2315 Robot Factory", "2401 Space Station",
)
FINAL_STORY_LEVEL = len(STORY_LEVELS) - 1
STORY_DIFFICULTIES = ("Easy", "Normal", "Hard")
# Single-player completion: one word per difficulty in the profile, bit = level. Finishing on a
# higher difficulty also sets the lower ones.
STORY_FLAGS_OFFSET = 0xBC8

# "Is story level N available?" (r3 = level) normally says yes for level 0 and otherwise asks
# whether the level before is complete. The client replaces its first five instructions with a
# lookup in a mask it keeps in low memory (bit N = level N is open).
STORY_FUNCTION = 0x8013EDF4
STORY_ORIGINAL = (0x9421FFD0, 0x7C0802A6, 0x90010034, 0x93E1002C, 0x7CBF2B78)
STORY_MASK_ADDRESS = 0x80002ED0
STORY_PATCH = (
    0x3CC08000,                    # lis   r6, 0x8000
    0x80C62ED0,                    # lwz   r6, 0x2ED0(r6)   r6 = the mask
    0x7CC61C30,                    # srw   r6, r6, r3
    0x54C307FE,                    # clrlwi r3, r6, 31      answer = bit `level`
    0x4E800020,                    # blr
)
# Dolphin keeps running code it has already compiled, so changing the function alone only works
# if the game has not used it yet. To make it work at any time, the two story menus (level
# select and difficulty select) are started through a small routine that first tells the
# emulated CPU the function changed (icbi), then carries on into the game's own menu code. The
# menus' start addresses are data, so pointing them at the routine needs no code change.
STORY_ROUTINES = 0x80002E90
STORY_ROUTINE_CODE = (
    0x3D808014, 0x398CEDE0,        # lis r12, 0x8014 / addi r12, r12, -0x1220   (0x8013EDE0)
    0x7C0067AC,                    # icbi 0, r12
    0x398C0020, 0x7C0067AC,        # addi r12, r12, 0x20 / icbi 0, r12
    0x4C00012C,                    # isync
    0x48199404,                    # b 0x8019C2AC   the game's level select menu
    0x3D808014, 0x398CEDE0, 0x7C0067AC, 0x398C0020, 0x7C0067AC, 0x4C00012C,
    0x4819A2BC,                    # b 0x8019D180   the game's difficulty select menu
)
STORY_AREA_END = 0x80002ED4        # routines and mask: 0x80002E90 up to here
# (address of the menu's start pointer, the game's own value, our routine)
STORY_MENU_POINTERS = (
    (0x80326954, 0x8019C2AC, STORY_ROUTINES),
    (0x80326940, 0x8019D180, STORY_ROUTINES + 0x1C),
)
GOAL_SPACE_STATION, GOAL_ALL_TROPHIES = 0, 1          # GOAL_ALL_TROPHIES is the Trophy Hunt goal
STORY_INDIVIDUAL, STORY_PROGRESSIVE = 0, 1
PROGRESSIVE_STORY_ITEM_NAME = "Progressive Story Level"

# ---- Story objectives ----
# Each level's objectives are a table of 36-byte records in the game's static data (found
# through a per-level (table, count) pair; Siberia's pair is at 0x802D2DD8). Record layout:
#   +0x00 text ID   +0x10 / +0x14 / +0x18 role on Easy / Normal / Hard
#                     (0 main, 1 optional, -1 not in that difficulty)
#   +0x1C state     0 before the level is loaded, 1 not given yet, 2 active, 5 completed
# One record serves every difficulty, so an objective is one check however it is played.
# Two records are not used on any difficulty and are left out: Chicago "Gain access to the
# Sunrise Nightclub" and Wild West "Fight off the Colonel's troops until he surrenders". Chicago
# "Stop the informant making the call" (record 4) is marked optional on every difficulty but the
# level never gives it (checked in game), so it is left out too.
OBJECTIVE_STATE_OFFSET = 0x1C
OBJECTIVE_COMPLETED = 5
# (level, record number, record address, text ID, location name, role on Easy/Normal/Hard)
STORY_OBJECTIVES: tuple[tuple[int, int, int, int, str, tuple[int, int, int]], ...] = (
    (0, 0, 0x802CB0C0, 0x428, 'Deactivate the Communications Dish', (0, 0, 0)),
    (0, 1, 0x802CB0E4, 0x429, 'Investigate the Secret Digging Site', (0, 0, 0)),
    (0, 2, 0x802CB108, 0x42A, 'Destroy the Bio-Hazard Container at the Digging Site', (0, 0, 0)),
    (0, 3, 0x802CB12C, 0x42B, 'Restore Power', (-1, 0, 0)),
    (0, 4, 0x802CB150, 0x42C, 'Access the Top of the Dam', (-1, 0, 0)),
    (0, 5, 0x802CB174, 0x42D, 'Eliminate the Gunship', (-1, 0, 0)),
    (0, 6, 0x802CB198, 0x42E, 'Burn All Evidence in the Filing Cabinets', (1, 1, 0)),
    (0, 7, 0x802CB1BC, 0x42F, "Don't Allow Any Mutants to Survive", (-1, 1, 0)),
    (0, 8, 0x802CB1E0, 0x426, 'Retrieve the Time Crystal', (0, 0, 0)),
    (0, 9, 0x802CB204, 0x427, 'Escape through the Time Portal', (0, 0, 0)),
    (1, 0, 0x802FE8F8, 0x430, 'Drain the Whisky Barrels', (1, 0, 0)),
    (1, 1, 0x802FE91C, 0x431, 'Rendezvous with Your Informant', (0, 0, 0)),
    (1, 2, 0x802FE940, 0x432, 'Protect Marco as He Returns to His Hideout', (0, 0, 0)),
    (1, 3, 0x802FE964, 0x433, 'Obtain the Nightclub Pass Card', (0, 0, 0)),
    (1, 6, 0x802FE9D0, 0x436, "Prevent Tony's Brother from Escaping", (1, 1, 0)),
    (1, 7, 0x802FE9F4, 0x437, 'Eliminate Big Tony', (0, 0, 0)),
    (1, 8, 0x802FEA18, 0x426, 'Retrieve the Time Crystal', (0, 0, 0)),
    (1, 9, 0x802FEA3C, 0x438, 'Minimize Civilian Casualties', (-1, 1, 0)),
    (1, 10, 0x802FEA60, 0x427, 'Escape through the Time Portal', (0, 0, 0)),
    (2, 0, 0x802FAC68, 0x43E, 'Rescue the Maidens', (0, 0, 0)),
    (2, 1, 0x802FAC8C, 0x43F, 'Help the Hunchback Escape with the Maiden', (1, 1, 0)),
    (2, 2, 0x802FACB0, 0x440, 'Fight Off the Portal Daemon', (0, 0, 0)),
    (2, 3, 0x802FACD4, 0x441, 'Make Your Way to the Roof to Escape Notre Dame', (0, 0, 0)),
    (2, 4, 0x802FACF8, 0x426, 'Retrieve the Time Crystal', (0, 0, 0)),
    (2, 5, 0x802FAD1C, 0x427, 'Escape through the Time Portal', (0, 0, 0)),
    (2, 6, 0x802FAD40, 0x442, 'Eliminate Jacque de la Morte', (0, 0, 0)),
    (3, 0, 0x802DC6B0, 0x451, 'Locate the Crashed UFO', (0, 0, 0)),
    (3, 1, 0x802DC6D4, 0x452, 'Shoot Down the Escaping UFOs', (-1, 0, 0)),
    (3, 2, 0x802DC6F8, 0x453, 'Find the UFO Base', (-1, 0, 0)),
    (3, 3, 0x802DC71C, 0x426, 'Retrieve the Time Crystal', (0, 0, 0)),
    (3, 4, 0x802DC740, 0x427, 'Escape through the Time Portal', (0, 0, 0)),
    (3, 5, 0x802DC764, 0x454, 'Repel the Beach Attack', (0, 0, 0)),
    (3, 6, 0x802DC788, 0x455, 'Fight Off the Raid on the Crashed UFO', (0, 0, 0)),
    (4, 0, 0x802F68D8, 0x443, 'Follow the Hacker to the Research Area', (0, 0, 0)),
    (4, 1, 0x802F68FC, 0x444, "Obtain the Hacker's Password", (0, 0, 0)),
    (4, 2, 0x802F6920, 0x445, 'Gather Evidence of TimeSplitter Research', (-1, 0, 0)),
    (4, 3, 0x802F6944, 0x446, 'Upload the Evidence to the Local Police Server', (-1, 0, 0)),
    (4, 4, 0x802F6968, 0x447, 'Deactivate the TimeSplitter Machine', (0, 0, 0)),
    (4, 5, 0x802F698C, 0x448, 'Eliminate the Gang Leader before She Escapes', (0, -1, -1)),
    (4, 6, 0x802F69B0, 0x427, 'Escape through the Time Portal', (0, 0, 0)),
    (4, 7, 0x802F69D4, 0x426, 'Retrieve the Time Crystal', (0, 0, 0)),
    (4, 8, 0x802F69F8, 0x44A, 'Minimize Civilian Casualties', (-1, 1, 0)),
    (5, 0, 0x802D36F8, 0x456, 'Rescue Ramona from Jail', (0, 0, 0)),
    (5, 1, 0x802D371C, 0x457, "Destroy the Wanted Posters to Clear Ramona's Name", (1, 1, 0)),
    (5, 2, 0x802D3740, 0x458, 'Put Out the Fire in the Barn and Rescue the Girl', (0, 0, 0)),
    (5, 3, 0x802D3764, 0x459, 'Eliminate the Colonel', (0, 0, 0)),
    (5, 5, 0x802D37AC, 0x426, 'Retrieve the Time Crystal', (0, 0, 0)),
    (5, 6, 0x802D37D0, 0x427, 'Escape through the Time Portal', (0, 0, 0)),
    (6, 0, 0x802C570C, 0x44B, 'Activate the Reactor', (0, 0, 0)),
    (6, 1, 0x802C5730, 0x44C, 'Defuse the Bombs', (0, 0, 0)),
    (6, 2, 0x802C5754, 0x426, 'Retrieve the Time Crystal', (0, 0, 0)),
    (6, 3, 0x802C5778, 0x427, 'Escape through the Time Portal', (0, 0, 0)),
    (6, 4, 0x802C579C, 0x44D, 'Minimize Scientist Casualties', (1, 1, 0)),
    (6, 5, 0x802C57C0, 0x44E, 'Eliminate Khallos', (0, 0, 0)),
    (7, 0, 0x802F3160, 0x44F, 'Find the Lost Temple', (0, 0, 0)),
    (7, 1, 0x802F3184, 0x426, 'Retrieve the Time Crystal', (0, 0, 0)),
    (7, 2, 0x802F31A8, 0x427, 'Escape through the Time Portal', (0, 0, 0)),
    (7, 3, 0x802F31CC, 0x450, 'Defeat the Golems', (0, 0, 0)),
    (8, 0, 0x802E5E50, 0x439, 'Gain Access to the Inner Processing Area', (0, 0, 0)),
    (8, 1, 0x802E5E74, 0x43A, 'Locate and Collect the ElectroTool', (0, 0, 0)),
    (8, 2, 0x802E5E98, 0x43B, 'Overload the Energy Nodes with Electricity', (0, 0, 0)),
    (8, 3, 0x802E5EBC, 0x43C, 'Find the Factory Core', (0, 0, 0)),
    (8, 4, 0x802E5EE0, 0x426, 'Retrieve the Time Crystal', (0, 0, 0)),
    (8, 5, 0x802E5F04, 0x427, 'Escape through the Time Portal', (0, 0, 0)),
    (8, 6, 0x802E5F28, 0x43D, 'Defeat the Machinist', (0, 0, 0)),
    (9, 0, 0x802C0D38, 0x45B, 'Activate the Self Destruct Sequence', (0, 0, 0)),
    (9, 1, 0x802C0D5C, 0x45C, 'Shoot Down the Incoming TimeSplitter Ships', (0, 0, 0)),
    (9, 2, 0x802C0D80, 0x45D, 'Escape from the Spacestation', (0, 0, 0)),
    (9, 3, 0x802C0DA4, 0xA93, 'Collect the Crystals', (0, 0, 0)),
)


# Objectives that only exist on Easy (role -1 on Normal and Hard): with "Skip Easy Mode Exclusive
# Story Objectives", completing their level on Normal or Hard checks them. (level, location ID)
def _easy_only_objectives() -> tuple[tuple[int, int], ...]:
    return tuple((level, objective_location_id(level, record))
                 for level, record, _a, _t, _name, roles in STORY_OBJECTIVES
                 if roles[0] != -1 and roles[1] == -1 and roles[2] == -1)


def objective_location_name(level: int, name: str) -> str:
    return f"{STORY_LEVELS[level]} - {name}"


def objective_location_id(level: int, record: int) -> int:
    return BASE_ID + 600 + level * 16 + record


def story_item_name(level: int) -> str:
    return STORY_LEVELS[level]


def story_location_name(level: int, difficulty: int) -> str:
    return f"{STORY_LEVELS[level]} Completed ({STORY_DIFFICULTIES[difficulty]})"


def story_location_id(level: int, difficulty: int) -> int:
    return BASE_ID + 500 + level * len(STORY_DIFFICULTIES) + difficulty


# ---- Names and IDs ----
MISSION_ITEM_NAMES: tuple[str, ...] = tuple(m.item_name for m in MISSIONS)
ARCADE_ITEM_NAMES: tuple[str, ...] = tuple(m.item_name for m in MISSIONS if m.prefix != "Challenge")
CHALLENGE_ITEM_NAMES: tuple[str, ...] = tuple(m.item_name for m in MISSIONS if m.prefix == "Challenge")
CHARACTER_ITEM_NAMES: tuple[str, ...] = tuple(character_item_name(c[0]) for c in CHARACTERS)
CHEAT_ITEM_NAMES: tuple[str, ...] = tuple(cheat_item_name(c[0]) for c in CHEATS)
HAT_ITEM_NAMES: tuple[str, ...] = tuple(hat_item_name(h[0]) for h in HATS)
MAP_ITEM_NAMES: tuple[str, ...] = tuple(map_item_name(m[0]) for m in MAPS)
WEAPON_ITEM_NAMES: tuple[str, ...] = tuple(weapon_item_name(w[0]) for w in WEAPON_ENTRIES)
MODE_ITEM_NAMES: tuple[str, ...] = tuple(mode_item_name(m[0]) for m in MODES)
STORY_ITEM_NAMES: tuple[str, ...] = tuple(story_item_name(k) for k in range(len(STORY_LEVELS)))
# ---- Behead The Undead score multiplier ----
# Behead The Undead adds a kill's points (75, 100, 25 or 50 by enemy) to its score, the word at
# r13-0x7138, in one place: 0x8014B050 onwards, with the points in r5. The combo bonus
# (0x8014ABF0) is built from those same points. Only the three Behead The Undead missions use it.
# That instruction (`lwz r3, score`) is replaced by a jump to a few instructions that multiply the
# points by a number kept in low memory, do the replaced load and jump back. The points shown
# when you score are multiplied too. The client only ever changes the number.
# Dolphin keeps running code it has already compiled, so the Arcade League / Challenge mission
# select screen (which always comes before one of these missions) is started through a small
# routine that first runs icbi on the changed instruction, as for the story lock.
# (Monkeying Around was tried the same way, with hooks at 0x80148CB4 (points in r31), 0x801498B4
# and 0x8014A00C (points in r4), but Monkey Mayhem's combos made even x2 far too easy.)
MULTIPLIER_COPIES = 3                        # x2, x3, x4
BEHEAD_MULTIPLIER_ITEM_NAME = "Progressive Behead The Undead Score Multiplier"
MULTIPLIER_ITEM_NAMES = (BEHEAD_MULTIPLIER_ITEM_NAME,)
BEHEAD_FACTOR = 0x80002F00                   # the multiplier (1-4) the code reads
MULTIPLIER_FACTORS = {BEHEAD_MULTIPLIER_ITEM_NAME: BEHEAD_FACTOR}
SCORE_MENU_POINTER = 0x803268A0              # start of the mission select screen
SCORE_MENU_NORMAL = 0x801A330C
SCORE_MENU_ROUTINE = 0x80002F08
SCORE_CAVES = 0x80002F40
SCORE_AREA_END = 0x80002F60
# (address, the game's own instruction, register holding the points, multiplier address)
SCORE_HOOKS = (
    (0x8014B050, 0x806D8EC8, 5, BEHEAD_FACTOR),
)


def _branch(source: int, target: int) -> int:
    return 0x48000000 | ((target - source) & 0x03FFFFFC)


def _build_score_menu_routine() -> tuple[int, ...]:
    code = []
    for address, _original, _register, _factor in SCORE_HOOKS:
        code += [0x3D800000 | address >> 16,       # lis  r12, high
                 0x618C0000 | address & 0xFFFF,    # ori  r12, r12, low
                 0x7C0067AC]                       # icbi 0, r12
    code.append(0x4C00012C)                        # isync
    code.append(_branch(SCORE_MENU_ROUTINE + 4 * len(code), SCORE_MENU_NORMAL))
    return tuple(code)


def _build_score_caves() -> tuple[int, ...]:
    code = []
    for k, (address, original, register, factor) in enumerate(SCORE_HOOKS):
        cave = SCORE_CAVES + 20 * k
        code += [0x3C600000 | factor >> 16,                          # lis   r3, high
                 0x80630000 | factor & 0xFFFF,                       # lwz   r3, low(r3)
                 0x7C0001D6 | register << 21 | register << 16 | 3 << 11,   # mullw rP, rP, r3
                 original,                                           # lwz   r3, score
                 _branch(cave + 16, address + 4)]                    # back
    return tuple(code)


SCORE_MENU_ROUTINE_CODE = _build_score_menu_routine()
SCORE_CAVE_CODE = _build_score_caves()
SCORE_HOOK_BRANCHES = tuple(_branch(address, SCORE_CAVES + 20 * k)
                            for k, (address, _o, _r, _f) in enumerate(SCORE_HOOKS))
assert SCORE_MENU_ROUTINE + 4 * len(SCORE_MENU_ROUTINE_CODE) <= SCORE_CAVES
assert SCORE_CAVES + 4 * len(SCORE_CAVE_CODE) <= SCORE_AREA_END

# ---- Progressive Starting Armour ----
# 0x804013C8 starts a list of the characters in the level, the player first (0 in the menus, and
# left pointing at freed memory after quitting a level). In the player's object, +0x10 is the
# armour and +0x14 the size of a full bar (11 in Story on Normal, 8 on Hard, 1.6 in Arcade);
# +0x13E0 points at a body record whose +0x19C is health (more than 0 = alive).
# The level's flow is a small state machine, its state the word at 0x80468E10 (r13-0x7070,
# switched on at 0x801501E8): 3 while playing. A restart from the pause menu or a retry after
# dying takes it through 6 (and 8, or 7 and 2) before it is back at 3, keeping the same object.
# A new life is, as in Future Perfect: a new player object (a level has loaded); the state
# coming back to playing after one of those reload states; or health coming back above 0 (a
# respawn in Arcade).
STARTING_ARMOUR_ITEM_NAME = "Progressive Starting Armour"
STARTING_ARMOUR_COPIES = 4                   # 25%, 50%, 75%, 100%
PLAYER_LIST = 0x804013C8
PLAYER_ARMOUR_OFFSET = 0x10
PLAYER_FULL_BAR_OFFSET = 0x14
PLAYER_BODY_OFFSET = 0x13E0
BODY_HEALTH_OFFSET = 0x19C
LEVEL_STATE = 0x80468E10
LEVEL_STATE_PLAYING = 3
LEVEL_STATE_RELOADING = (2, 6, 7, 8)
STARTING_ARMOUR_SETTLE_POLLS = 4             # polls (0.25 s each) to wait after a new life begins
# What is being played comes from the game's setup block at 0x803D0A98: +0x4C is 0 outside a
# level, +0x8C is the story level (1 = Siberia, up to 12; 0 outside Story), and +0x70 is the
# Arcade League / Challenge mission number (0 in Arcade Custom, which is Glass Smash's Pane in
# the Neck: not a mission that gets armour).
SETUP_IN_LEVEL = 0x803D0AE4
SETUP_STORY_LEVEL = 0x803D0B24             # 0 outside Story; 1 (Siberia) to 12 in a story level
SETUP_STORY_LEVEL_MAX = 12                   # the game switches on it with 13 cases (0x80063E28)
SETUP_MISSION_NUMBER = 0x803D0B08
# Where starting armour applies: Story, every Arcade League mission and these Challenge groups.
STARTING_ARMOUR_CHALLENGE_GROUPS = ("Behead The Undead", "Banana Chomp", "TimeSplitters 'Story' Classic")
MISSION_BY_NUMBER = {m.number: m for m in MISSIONS}

# ---- Temporal Uplink cartridges ----
# Picking up a cartridge in Story sets a word in the profile to 1 (0x80026284: object model 0x142
# RetroRacer, 0x143 Anaconda, 0x144 AstroLander). The Temporal Uplink in a level (0x80262FAC counts
# the cartridges to decide whether its game menu opens, 0x8026297C lists the games) only asks
# whether each word is 0. So the client keeps each word at 0 (no item) or 2 (you have the item):
# a 1 can then only mean the cartridge has just been picked up, whatever you own.
# (game, story level, profile offset, Hard only)
CARTRIDGES: tuple[tuple[str, int, int, bool], ...] = (
    ("Anaconda", 0, 0x1198, False),
    ("RetroRacer", 8, 0x119C, True),
    ("AstroLander", 4, 0x11A4, False),
)
CARTRIDGE_PICKED_UP = 1
CARTRIDGE_OWNED = 2


def cartridge_item_name(game: str) -> str:
    return f"Temporal Uplink - {game} Cartridge"


def cartridge_location_name(game: str, level: int) -> str:
    return f"{STORY_LEVELS[level]} - {game} Cartridge Found"


CARTRIDGE_ITEM_NAMES = tuple(cartridge_item_name(c[0]) for c in CARTRIDGES)

# ---- Anaconda score ----
# The score of the Anaconda game being played is the word at 0x8043D774 (found with a value
# search). One location per 500 points, up to the highest score the options ask for.
ANACONDA_SCORE = 0x8043D774
ANACONDA_STEP = 500
ANACONDA_MAX_STEPS = 20                      # 10000 points


def anaconda_location_name(points: int) -> str:
    return f"Temporal Uplink - Anaconda - {points} Points"


def anaconda_location_id(points: int) -> int:
    return BASE_ID + 850 + points // ANACONDA_STEP


# ---- RetroRacer and AstroLander ----
# Found with a value search: the byte at 0x804435B7 counts the RetroRacer laps finished (0 on lap 1,
# 5 once the race is over); the byte at 0x804696E3 (low byte of a word only the Temporal Uplink
# games' code at 0x80269xxx uses) is the AstroLander level, counted from 0. Both stay at their
# last value afterwards, and are only read during Story.
RETRORACER_LAPS = 0x804435B7
RETRORACER_LAP_COUNT = 5
ASTROLANDER_LEVEL = 0x804696E3
ASTROLANDER_LEVEL_COUNT = 11


def retroracer_location_names() -> tuple[str, ...]:
    return tuple(f"Temporal Uplink - RetroRacer - Lap {k}" for k in range(1, RETRORACER_LAP_COUNT + 1)) \
        + ("Temporal Uplink - RetroRacer - Completed",)


def retroracer_location_id(index: int) -> int:
    """index 0-4 = laps 1-5, 5 = Completed."""
    return BASE_ID + 880 + index


def astrolander_location_name(level: int) -> str:
    return f"Temporal Uplink - AstroLander - Level {level} Completed"


def astrolander_location_id(level: int) -> int:
    return BASE_ID + 890 + level


def cartridge_location_id(index: int) -> int:
    return BASE_ID + 800 + index

# ---- Weapon buffs ----
# Whole-number weapon stats the client can raise, as in Future Perfect:
#   * clip size: +0x14 of the weapon stat table (0x240 bytes per weapon from 0x8030B6F0, found
#     from 0x80069CB0; +0x10 is the ammo type). The (x2) weapons share their single weapon's record.
#   * most ammo carried: +0x00 of the ammo table (0xD0 bytes per ammo type from 0x80309900, found
#     from 0x800238E4; the ammo type's name is the text at +0x88).
# Both are plain data. Fire rate, accuracy and damage are left out on purpose (they would apply
# to enemies carrying the weapon as well). The Homing Launcher's clip (1) is left out too. The
# Shotgun's clip of 2 goes up by half (one shell) per copy.
# Each row is one progressive item: every copy adds `change` of the normal value, up to `copies`.
# The position of a row decides its item ID, so only ever add rows at the end.
# (weapon, stat, addresses, normal value, change per copy, copies, always in the pool)
WEAPON_BUFFS: tuple[tuple[str, str, tuple[int, ...], int, float, int, bool], ...] = (
    ("Silenced Pistol", "Clip Size", (0x8030B704,), 8, 0.25, 3, False),
    ("Silenced Luger", "Clip Size", (0x8030B944,), 7, 0.25, 3, False),
    ("Luger Pistol", "Clip Size", (0x8030BB84,), 7, 0.25, 3, False),
    ("Garrett Revolver", "Clip Size", (0x8030BDC4,), 6, 0.25, 3, False),
    ("Tactical 12-Gauge", "Clip Size", (0x8030C004,), 8, 0.25, 3, False),
    ("Sniper Rifle", "Clip Size", (0x8030C484,), 5, 0.25, 3, False),
    ("Vintage Rifle", "Clip Size", (0x8030C6C4,), 5, 0.25, 3, False),
    ("Soviet S47", "Clip Size", (0x8030CD84,), 30, 0.25, 3, False),
    ("Scifi Handgun", "Clip Size", (0x8030D204, 0x80311104), 30, 0.25, 3, False),   # two records
    ("Rocket Launcher", "Clip Size", (0x8030D444,), 3, 0.25, 3, False),
    ("Grenade Launcher", "Clip Size", (0x8030DD44,), 8, 0.25, 3, False),
    ("Tommy Gun", "Clip Size", (0x8030EAC4,), 32, 0.25, 3, False),
    ("SBP90 Machinegun", "Clip Size", (0x8030ED04,), 64, 0.25, 3, False),
    ("Crossbow", "Clip Size", (0x80310804,), 4, 0.25, 3, False),
    ("Pistols", "Reserve Ammo", (0x803099D0,), 60, 0.25, 3, False),        # Pistol Ammo
    ("Soviet S47", "Reserve Ammo", (0x80309AA0,), 200, 0.25, 3, False),
    ("Minigun", "Reserve Ammo", (0x80309B70,), 400, 0.25, 3, False),
    ("Sniper Rifles", "Reserve Ammo", (0x80309C40,), 40, 0.25, 3, False),  # Sniper and Vintage Rifle
    ("Shotguns", "Reserve Ammo", (0x80309DE0,), 40, 0.25, 3, False),       # Shotgun Shells
    ("Garrett Revolver", "Reserve Ammo", (0x80309EB0,), 80, 0.25, 3, False),
    ("SBP90 Machinegun", "Reserve Ammo", (0x80309F80,), 256, 0.25, 3, False),
    ("Tommy Gun", "Reserve Ammo", (0x8030A050,), 200, 0.25, 3, False),
    ("Lasergun", "Reserve Ammo", (0x8030A120,), 3000, 0.25, 3, False),
    ("Plasma Autorifle", "Reserve Ammo", (0x8030A1F0,), 200, 0.25, 3, False),
    ("Scifi Handgun", "Reserve Ammo", (0x8030A2C0,), 200, 0.25, 3, False),
    ("Rocket Launcher", "Reserve Ammo", (0x8030A390,), 30, 0.25, 3, False),
    ("Homing Launcher", "Reserve Ammo", (0x8030A460,), 30, 0.25, 3, False),
    ("Grenade Launcher", "Reserve Ammo", (0x8030A530,), 40, 0.25, 3, False),
    ("Brick", "Reserve Ammo", (0x8030A6D0,), 40, 0.25, 3, False),
    ("Remote Mine", "Reserve Ammo", (0x8030A7A0,), 20, 0.25, 3, False),
    ("Timed Mine", "Reserve Ammo", (0x8030A870,), 20, 0.25, 3, False),
    ("Proximity Mine", "Reserve Ammo", (0x8030A940,), 20, 0.25, 3, False),
    ("ElectroTool", "Reserve Ammo", (0x8030AAE0,), 1000, 0.25, 3, False),
    ("Flamethrower", "Reserve Ammo", (0x8030ABB0,), 1500, 0.25, 3, False),
    ("Fire Extinguisher", "Reserve Ammo", (0x8030AC80,), 1000, 0.25, 3, False),
    ("Crossbow", "Reserve Ammo", (0x8030AD50,), 50, 0.25, 3, False),
    # Added in 0.13.1, once a bigger Shotgun clip was confirmed to work: +1 shell per copy.
    ("Shotgun", "Clip Size", (0x8030EF44,), 2, 0.5, 3, False),
)


def weapon_buff_item_name(weapon: str, stat: str, change: float) -> str:
    return f"Weapon Buff - {weapon} - +{round(change * 100)}% {stat}"


def weapon_buff_value(normal: int, change: float, copies: int) -> int:
    """The stat's value with this many copies (halves round up, so 3.75 -> 4 and 4.5 -> 5)."""
    return int(normal * (1 + change * copies) + 0.5)


WEAPON_BUFF_ITEM_NAMES: tuple[str, ...] = tuple(weapon_buff_item_name(b[0], b[1], b[4]) for b in WEAPON_BUFFS)

# ---- Damage resistances ----
# Every hit on a character goes through 0x8001E100(event): +0x18 is the damage type, +0x1C the
# damage (a float), r26 the event and r31 the character being hit. 0x8001E3D8 is the point every
# hit that will do damage reaches, before the character's own resistances (0x8001F354), armour
# and health. That instruction (lis r3, 0x803d) is replaced by a jump to a few instructions that,
# when the character is player 1, multiply the damage by a number kept for its type, do the
# replaced instruction and jump back. Enemies are not affected. The client only changes the
# numbers. Dolphin keeps running code it has already compiled, so the level's "playing" entry
# first runs a routine that clears Dolphin's copy once (icbi) after the jump is written, then
# carries on into the message code. Confirmed in game with tools/ts2_resistance_test.py.
# Damage types (42, see the table at 0x803141C0), grouped by what they are:
# (group, damage types)
RESISTANCES: tuple[tuple[str, tuple[int, ...]], ...] = (
    ("Bullet", (1, 2, 3, 27, 29, 35, 36, 40, 41)),          # bullets, pellets, crossbow bolts
    ("Explosive", (4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 21, 34, 38)),   # 21 = every blast
    ("Fire", (19, 20, 39)),                                  # Flamethrower, burning, Fire Extinguisher
    ("Plasma", (22, 23, 24, 25, 26, 28, 30, 31, 32, 33, 37)),   # Lasergun, Plasma, Scifi, ElectroTool
    ("Melee", (0, 18)),                                      # punches, Brick
)
DAMAGE_TYPE_COUNT = 42
assert sorted(t for _g, types in RESISTANCES for t in types) == list(range(DAMAGE_TYPE_COUNT))
RESISTANCE_COPIES = 6
RESISTANCE_STEP = 0.10                       # 10% less damage per copy, so at most 60%
# Weapon buffs, resistances and cheat traps fill the locations left over together; a resistance
# copy is this many times as likely to be picked as a weapon buff copy (there are far fewer).
RESISTANCE_WEIGHT = 2.0


def resistance_item_name(group: str) -> str:
    return f"Progressive {group} Damage Resistance"


RESISTANCE_ITEM_NAMES: tuple[str, ...] = tuple(resistance_item_name(group) for group, _types in RESISTANCES)
RESISTANCE_HOOK = 0x8001E3D8
RESISTANCE_HOOK_ORIGINAL = 0x3C60803D        # lis r3, 0x803d
RESISTANCE_CAVE = 0x80002AC0
RESISTANCE_FLUSH = 0x80002B40                # the level-state routine: icbi once, then the message code
RESISTANCE_TABLE = 0x80002B80                # 42 floats: damage multiplier by type
RESISTANCE_FLUSHED = 0x80002C30              # 0 = Dolphin's copy still to be cleared
RESISTANCE_AREA_END = 0x80002C40

# ---- Cheat traps ----
# Gameplay code tests a cheat as (0x80469754 AND cheat unlocked AND 0x80469750), bit = entry number
# in the cheat table: 0x80469754 holds the cheats switched on in the menu (r13-0x672C, set by
# 0x8026B600 / cleared by 0x8026B5E8) and 0x80469750 the cheats this mode allows (0 in the menus,
# 0xF7E in Story). The tests run during play, so a bit switched on mid-level shows at once
# (confirmed with Big Heads). A trap switches its cheat's bit on in both words (and unlocks the
# cheat) for a while, then takes back only the bits it added.
CHEAT_ACTIVE = 0x80469754
CHEAT_ALLOWED = 0x80469750
# (cheat name as in CHEATS, cheat table entry)
TRAPS: tuple[tuple[str, int], ...] = (
    ("Big Heads", 1), ("Small Heads", 2), ("Big Hands", 3), ("Fat Characters", 6),
    ("Cardboard Characters", 10), ("Rotating Heads", 11), ("All Characters Cloaked", 8),
    ("Slow Motion Deaths", 9),
)
TRAP_COPIES = 3                              # at most this many of each trap in a game


def trap_item_name(cheat: str) -> str:
    return f"{cheat} Trap"


TRAP_ITEM_NAMES: tuple[str, ...] = tuple(trap_item_name(t[0]) for t in TRAPS)

# ---- Death Link ----
# The game fails a mission by setting bit 0x10000 of the setup's +0x5C flags and calling its "end
# the level" routine 0x80153804 (e.g. 0x8014CA1C when every player is out, 0x8014CB2C for a
# failed score; story objectives set the same bit at 0x801468B8). The level-state routine
# (0x801501C8, run every frame) picks what to do from a table of 9 addresses, one per level
# state; the entry for "playing" (3) is pointed at a few new instructions that fail the mission
# when DEATH_TRIGGER is not zero and otherwise carry on as normal. Only data the game re-reads
# every frame is changed, so Dolphin's compiled code does not get in the way.
SETUP_FLAGS_5C = 0x803D0AF4
SETUP_FAILED_FLAG = 0x10000
STATE_TABLE_PLAYING = 0x8031E194 + 4 * LEVEL_STATE_PLAYING
STATE_PLAYING_HANDLER = 0x801502C8           # what that entry normally holds
STATE_ROUTINE_EXIT = 0x801508E4
END_LEVEL_ROUTINE = 0x80153804
DEATH_TRIGGER = 0x80002F60
DEATH_CAVE = 0x80002F64
DEATH_TRIGGER_POLLS = 8                      # polls to wait for the game to act on the trigger
DEATH_KILL_POLLS = 16                        # after a kill: a failure this soon came from it (4 s)
# Failing a story level during its opening cutscene crashes the game, so a death received then
# waits until you can move. This word (r13-0x6840, set at 0x80261320) is 1 while you play and 0
# through a story cutscene (seen over three opening cutscenes).
STORY_CONTROL_FLAG = 0x80469640
CUTSCENE_SETTLE_POLLS = 4                    # polls to wait after a cutscene ends


DEATH_TRIGGER_FAIL, DEATH_TRIGGER_KILL = 1, 2
# Arcade League missions and Challenges work out their result (and trophy) from the state of the
# match, so ending one early can award a trophy and leave the end-of-match data half set up (a
# crash on leaving). There a received death kills the player instead, with the game's own
# "kill this character" routine (0x8001EE1C, given the character's body): the game then takes a
# life, respawns the player or fails the mission itself.
KILL_CHARACTER_ROUTINE = 0x8001EE1C


def _build_death_cave() -> tuple[int, ...]:
    low = DEATH_TRIGGER & 0xFFFF

    def branch(index: int, target: int, link: int = 0) -> int:
        return _branch(DEATH_CAVE + 4 * index, target) | link
    return (
        0x3D800000 | (DEATH_TRIGGER >> 16),    # 0  lis r12, 0x8000
        0x800C0000 | low,                      # 1  lwz r0, trigger(r12)
        0x2C000000,                            # 2  cmpwi r0, 0
        0x41820058,                            # 3  beq 25              (carry on as normal)
        0x38600000,                            # 4  li r3, 0
        0x906C0000 | low,                      # 5  stw r3, trigger(r12)
        0x2C000000 | DEATH_TRIGGER_KILL,       # 6  cmpwi r0, kill
        0x41820024,                            # 7  beq 16
        0x3C60803D,                            # 8  lis r3, 0x803D
        0x38630A98,                            # 9  addi r3, r3, 0x0A98       (the setup)
        0x8003005C,                            # 10 lwz r0, 0x5C(r3)
        0x64000001,                            # 11 oris r0, r0, 1            (failed)
        0x9003005C,                            # 12 stw r0, 0x5C(r3)
        branch(13, END_LEVEL_ROUTINE, 1),      # 13 bl end the level
        branch(14, STATE_ROUTINE_EXIT),        # 14
        0x60000000,                            # 15 nop
        0x3C600000 | (PLAYER_LIST >> 16),      # 16 lis r3, players@h
        0x80630000 | (PLAYER_LIST & 0xFFFF),   # 17 lwz r3, players@l(r3)  (player 1)
        0x2C030000,                            # 18 cmpwi r3, 0
        0x41820018,                            # 19 beq 25
        0x806313E0,                            # 20 lwz r3, 0x13E0(r3)      (the body)
        0x2C030000,                            # 21 cmpwi r3, 0
        0x4182000C,                            # 22 beq 25
        branch(23, KILL_CHARACTER_ROUTINE, 1), # 23 bl kill it
        0x60000000,                            # 24 nop
        branch(25, STATE_PLAYING_HANDLER),     # 25 carry on as normal
    )


# The code 1.0.x clients put there (fail only): replaced when found.
OLD_DEATH_CAVE_CODE = (
    0x3D800000 | (DEATH_TRIGGER >> 16), 0x800C0000 | (DEATH_TRIGGER & 0xFFFF), 0x2C000000, 0x41820028,
    0x38000000, 0x900C0000 | (DEATH_TRIGGER & 0xFFFF), 0x3C60803D, 0x38630A98, 0x8003005C, 0x64000001,
    0x9003005C, _branch(DEATH_CAVE + 44, END_LEVEL_ROUTINE) | 1, _branch(DEATH_CAVE + 48, STATE_ROUTINE_EXIT),
    _branch(DEATH_CAVE + 52, STATE_PLAYING_HANDLER),
)


DEATH_CAVE_CODE = _build_death_cave()
DEATH_AREA_END = DEATH_CAVE + 4 * len(DEATH_CAVE_CODE)
assert DEATH_TRIGGER >= SCORE_AREA_END and DEATH_AREA_END <= 0x80003000

# ---- Death Link Amnesty ----
# Arcade League missions: a death is health (body +0x19C) going from above 0 to 0 or below. It is
# only counted once the mission has gone on for a moment without failing, so a death that fails
# a one-life mission is sent once, as a failure.
DEATH_CONFIRM_POLLS = 6                      # 1.5 s

# ---- In-game announcements ----
# Every on-screen message goes through 0x8010D1A8(player, style, text, delay), the same routine
# as in Future Perfect: r3 = player (0 = player 1), r4 = style 1-6, r5 = text, f1 = seconds before
# it shows. "Checkpoint reached" is style 2 (0x8004D934). A message the same as one already on
# screen is not added again. The client puts the text at MESSAGE_TEXT and the style at
# MESSAGE_STYLE; a few instructions run from the level-state table's "playing" entry (before
# Death Link's) pass them to the game and clear the style word, then wait MESSAGE_GAP frames
# before taking the next one.
SHOW_MESSAGE_ROUTINE = 0x8010D1A8
MESSAGE_CAVE = 0x80002D80                    # up to 0x80002E00, where the mission lock starts
MESSAGE_STYLE = 0x80002700                   # 0 = nothing waiting
MESSAGE_DELAY = 0x80002704                   # float seconds before it shows: always 0
MESSAGE_COOLDOWN = 0x80002708                # frames left before the next message may be taken
MESSAGE_TEXT = 0x80002710                    # up to 0x80002800, where the award screen starts
MESSAGE_TEXT_MAX = 0x80002800 - MESSAGE_TEXT - 1
MESSAGE_GAP = 30                             # half a second: the client also waits (below)
# The game's message queue for player 1 (0x803BB898, 0x1254 bytes per player): 16 entries of
# 0x120 bytes from +0x38, each holding the style (+0), the text (+4, up to 256 bytes), a timer
# in seconds (+0x108, starting at minus the delay and counting up) and the style's timings
# (+0x10C, +0x114: for style 2, 1.5 and 2.5 seconds). The client only passes the next message on
# once no message of the same style is still on screen.
MESSAGE_QUEUE = 0x803BB898 + 0x38
MESSAGE_QUEUE_ENTRIES = 16
MESSAGE_ENTRY_SIZE = 0x120
MESSAGE_ENTRY_TIMER, MESSAGE_ENTRY_STAGE_1, MESSAGE_ENTRY_STAGE_2 = 0x108, 0x10C, 0x114
MESSAGE_SPARE_SECONDS = 0.25
MESSAGE_STYLE_LINE, MESSAGE_STYLE_BIG = 2, 3


def _build_message_cave() -> tuple[int, ...]:
    def branch(index: int, target: int, link: int = 0) -> int:
        return _branch(MESSAGE_CAVE + 4 * index, target) | link

    def cond(index: int, bo: int, bi: int, target_index: int) -> int:
        return (16 << 26) | (bo << 21) | (bi << 16) | ((4 * (target_index - index)) & 0xFFFC)

    low = lambda address: address & 0xFFFF
    out = 18
    code = (
        0x3D808000,                                    # 0  lis r12, 0x8000
        0x808C0000 | low(MESSAGE_COOLDOWN),            # 1  lwz r4, cooldown(r12)
        0x3484FFFF,                                    # 2  addic. r4, r4, -1
        cond(3, 12, 0, 6),                             # 3  blt take            (cooldown was 0)
        0x908C0000 | low(MESSAGE_COOLDOWN),            # 4  stw r4, cooldown(r12)
        branch(5, MESSAGE_CAVE + 4 * out),             # 5  b out
        0x80AC0000 | low(MESSAGE_STYLE),               # 6  take: lwz r5, style(r12)
        0x2C050000,                                    # 7  cmpwi r5, 0
        cond(8, 12, 2, out),                           # 8  beq out             (nothing waiting)
        0x38000000,                                    # 9  li r0, 0
        0x900C0000 | low(MESSAGE_STYLE),               # 10 stw r0, style(r12)
        0x38000000 | MESSAGE_GAP,                      # 11 li r0, gap
        0x900C0000 | low(MESSAGE_COOLDOWN),            # 12 stw r0, cooldown(r12)
        0x7CA42B78,                                    # 13 mr r4, r5
        0xC02C0000 | low(MESSAGE_DELAY),               # 14 lfs f1, delay(r12)
        0x38AC0000 | low(MESSAGE_TEXT),                # 15 addi r5, r12, text
        0x38600000,                                    # 16 li r3, 0 (player 1)
        branch(17, SHOW_MESSAGE_ROUTINE, 1),           # 17 bl show the message
        branch(18, DEATH_CAVE),                        # 18 out: b Death Link's check (then normal play)
    )
    assert MESSAGE_CAVE + 4 * len(code) <= ROUTINE
    return code


MESSAGE_CAVE_CODE = _build_message_cave()

# ---- Award screen ("New Feature Unlocked") ----
# After a mission the game lists what became available since the mission started: 0x8019B49C
# compares maps, bot sets, characters, challenge sets, leagues, hats, Assault maps, game modes,
# cheats and the Brick with a snapshot (taken by 0x8019B9BC) and writes up to 10 entries: heading
# text IDs at 0x803EB2A8 and name text IDs 0x28 before them, shown 3 to a page by 0x8019AA80.
# Who builds the list (seen with tools/ts2_award_watch.py):
#   0x80188B2C  after a mission, when the game has no "something changed" flag: shows the award
#               screen if the list is not empty (menu context 6 after an Arcade League mission)
#   0x80188D70  another menu flow with the same check
#   0x8019AA98, 0x8019B03C, 0x8019B12C  the award screen itself (opening, every frame, next page)
# The builder ends `lwz r0, 0x44(r1)` (its return address), `mr r3, r29` (the number of entries).
# The client replaces the `mr` with a jump to AWARD_CAVE, which reloads r0 before going back.
# The client's entries are added on the award screen itself, and at 0x80188B2C only in menu
# context 6, so that the screen also appears when only Archipelago items were found (forcing it
# from a story level's menu flow crashed the game). They are never added at 0x80188D70. The cave
# leaves out the game's "New Challenge Set available!" entries, moves the rest down, puts the
# client's first entries (story levels, missions, challenges, cartridges) at the top and adds the
# client's other entries at the end.
# Every line is a text ID, looked up as (text table) + 4 * id with no limit, so an ID can be
# chosen that makes the game read a text pointer kept in AWARD_POINTERS. AWARD_SHOWN is set when
# the list is built with the client's entries.
# Dolphin keeps running code it has already compiled, so the jump only takes effect if it is
# written before the game first builds the list after booting. The client writes it as soon as it
# finds the game, and also starts the award screen itself (screen record start pointer at
# 0x803269A4) through AWARD_MENU_ROUTINE, which runs icbi on the jump first.
AWARD_LIST = 0x803EB2A8                    # heading text IDs; name text IDs at AWARD_LIST - 0x28
AWARD_NAME_OFFSET = -0x28
AWARD_HOOK = 0x8019B9A8
AWARD_HOOK_ORIGINAL = 0x7FA3EB78           # mr r3, r29
AWARD_RETURN = 0x8019B9AC
AWARD_AFTER_MISSION_CHECK = 0x80188B2C     # return address of the after-mission check
AWARD_OTHER_CHECK = 0x80188D70
AWARD_CONTEXT = 0x803ECE7C                 # the menu's +0x20AC word
AWARD_CONTEXT_ARCADE = 6
# The game's "New Challenge Set available!" entries are left out (the client lists the challenges).
AWARD_HIDDEN_HEADING = 851
AWARD_TEXT_TABLE = 0x80469618              # r13 - 0x6868: the game's text table
AWARD_CAVE = 0x80002800                    # code, up to AWARD_MENU_ROUTINE
AWARD_MENU_ROUTINE = 0x80002980
AWARD_MENU_POINTER = 0x803269A4            # start of the award screen
AWARD_MENU_NORMAL = 0x8019AA80
AWARD_FRONT_COUNT = 0x800029A0             # the first FRONT_COUNT entries go at the top
AWARD_COUNT = 0x800029A4
AWARD_SHOWN = 0x800029A8
AWARD_ENTRIES = 0x800029B0                 # 10 x (heading text ID, name text ID)
AWARD_POINTERS = 0x80002A00                # 10 x (heading text pointer, name text pointer)
AWARD_END = 0x80002A50
AWARD_HEADING_TEXT = 0x80002300            # 10 x 32 bytes
AWARD_NAME_TEXT = 0x80002440               # 10 x 64 bytes
AWARD_TEXT_END = AWARD_NAME_TEXT + 10 * 64   # 0x800026C0 (the message text starts at 0x80002700)
AWARD_MAX = 10
AWARD_HEADING_MAX, AWARD_NAME_MAX = 31, 63
assert AWARD_TEXT_END <= 0x80002700 and AWARD_END <= MESSAGE_CAVE

# Headings, in the game's own style ("New Character available!"), all ending in "!".
AWARD_STORY = "New Story Level available!"
AWARD_MISSION = "New Mission available!"
AWARD_CHALLENGE = "New Challenge available!"
AWARD_CARTRIDGE = "New Cartridge available!"
AWARD_WEAPON = "New Weapon available!"
AWARD_MULTIPLIER = "Score Multiplier found!"
AWARD_ITEM = "Archipelago Item found!"
AWARD_BUFF = "{stat} Buff found!"
AWARD_OTHER_PLAYER = "{player}'s Item!"
AWARD_MULTIPLIER_NAMES = {BEHEAD_MULTIPLIER_ITEM_NAME: "Behead The Undead"}

# Text never wraps on the award screen. A heading that is too wide for the box is drawn a little
# smaller; a name that is too wide is drawn in a smaller font (font 9 -> 4, see 0x8019AE48), and
# anything wider still runs off the sides. Widths in the font's own units (glyph advance + spacing
# + kerning, from the glyphs at 0x803554A8 and the tables at 0x802BB1C8 / 0x802BB648): a name of
# up to about 350 keeps the big font and one up to about 500 fits in the small one. Every name the
# client writes for TimeSplitters 2's own items stays under 470.

# Three of the game's own headings have no "!". Their entries in the text table are pointed at
# copies that do. (text ID, the game's text, the text used instead, where the copy goes)
AWARD_HEADING_FIXES: tuple[tuple[int, str, str, int], ...] = (
    (2627, "New Assault Level available", "New Assault Level available!", 0x80002A60),
    (2628, "New Weapon available", "New Weapon available!", 0x80002A80),
    (2629, "New Arcade League available", "New Arcade League available!", 0x80002AA0),
)
AWARD_HEADING_FIX_SIZE = 0x20
assert all(len(fixed) < AWARD_HEADING_FIX_SIZE for _i, _o, fixed, _a in AWARD_HEADING_FIXES)
assert AWARD_END <= AWARD_HEADING_FIXES[0][3] \
    and AWARD_HEADING_FIXES[-1][3] + AWARD_HEADING_FIX_SIZE <= MESSAGE_CAVE
assert AWARD_HEADING_FIXES[-1][3] + AWARD_HEADING_FIX_SIZE <= RESISTANCE_CAVE \
    and RESISTANCE_AREA_END <= MESSAGE_CAVE

# Award screen line for a resistance: "New Resistance found!" / "Fire Damage 20%".
AWARD_RESISTANCE = "New Resistance found!"


def _build_resistance_cave() -> tuple[int, ...]:
    def low(address: int) -> int:
        return address & 0xFFFF
    done = 14
    code = [
        0x3D808040,                               # 0  lis   r12, 0x8040
        0x818C0000 | low(PLAYER_LIST),            # 1  lwz   r12, PLAYER_LIST(r12)   player 1
        0x7C0CF840,                               # 2  cmplw r12, r31               being hit?
        0x40820000 | (done - 3) * 4,              # 3  bne   done
        0x817A0018,                               # 4  lwz   r11, 0x18(r26)         damage type
        0x280B0000 | (DAMAGE_TYPE_COUNT - 1),     # 5  cmplwi r11, 41
        0x41810000 | (done - 6) * 4,              # 6  bgt   done
        0x3D808000,                               # 7  lis   r12, 0x8000
        0x5560103A,                               # 8  slwi  r0, r11, 2
        0x398C0000 | low(RESISTANCE_TABLE),       # 9  addi  r12, r12, TABLE
        0x7C0C042E,                               # 10 lfsx  f0, r12, r0
        0xC03A001C,                               # 11 lfs   f1, 0x1c(r26)          damage
        0xEC210032,                               # 12 fmuls f1, f1, f0
        0xD03A001C,                               # 13 stfs  f1, 0x1c(r26)
        RESISTANCE_HOOK_ORIGINAL,                 # 14 done: lis r3, 0x803d (the replaced instruction)
    ]
    code.append(_branch(RESISTANCE_CAVE + 4 * len(code), RESISTANCE_HOOK + 4))
    assert RESISTANCE_CAVE + 4 * len(code) <= RESISTANCE_FLUSH
    return tuple(code)


def _build_resistance_flush() -> tuple[int, ...]:
    """The level state's "playing" entry: clear Dolphin's copy of the hooked code once, then the
    message code (which carries on into Death Link's and the game's own)."""
    low = RESISTANCE_FLUSHED & 0xFFFF
    code = (
        0x3D808000,                               # 0  lis   r12, 0x8000
        0x816C0000 | low,                         # 1  lwz   r11, FLUSHED(r12)
        0x2C0B0000,                               # 2  cmpwi r11, 0
        0x40820000 | (10 - 3) * 4,                # 3  bne   9 + 1
        0x3D600000 | RESISTANCE_HOOK >> 16,       # 4  lis   r11, hook@h
        0x616B0000 | RESISTANCE_HOOK & 0xFFFF,    # 5  ori   r11, r11, hook@l
        0x7C005FAC,                               # 6  icbi  0, r11
        0x4C00012C,                               # 7  isync
        0x39600001,                               # 8  li    r11, 1
        0x916C0000 | low,                         # 9  stw   r11, FLUSHED(r12)
        _branch(RESISTANCE_FLUSH + 40, MESSAGE_CAVE),   # 10 b message code
    )
    assert RESISTANCE_FLUSH + 4 * len(code) <= RESISTANCE_TABLE
    return code


RESISTANCE_CAVE_CODE = _build_resistance_cave()
RESISTANCE_FLUSH_CODE = _build_resistance_flush()
RESISTANCE_HOOK_BRANCH = _branch(RESISTANCE_HOOK, RESISTANCE_CAVE)
assert RESISTANCE_TABLE + 4 * DAMAGE_TYPE_COUNT <= RESISTANCE_FLUSHED

# ---- Archipelago Shop ----
# The View Cutscenes menu (Options > View Cutscenes) becomes a shop. Its 13 rows each show one
# shop location's item and price; A buys it with points. Points come from trophies (Bronze 10,
# Silver 20, Gold 30, Platinum 40, a better trophy counting the ones below it), story levels
# finished (Easy 15, Normal 35, Hard 50, likewise), every kill (1) and Trophy filler items.
# Shop location k is row k % 13 of batch k // 13; each batch after the first needs one more
# Progressive Shop Restock. Confirmed in game with tools/ts2_shop_test.py.
# The menu (see the shop research notes):
#   * screen start pointer 0x803269CC -> builder 0x80198E20, which we start through a wrapper
#     that counts openings and clears Dolphin's copy of the builder (icbi) before it runs;
#   * the builder's two "has this cutscene been seen?" calls become li r3, 1 (all rows show);
#   * its rows' A-press callback (lis/addi at 0x80198F48) becomes ours: when the row may be
#     bought (AFFORD), switch it to its prepared text (NEXT_TEXT), re-centre it (0x80213BD4) and
#     report it in SHOP_PICK; otherwise report it + 0x100. A cutscene never plays;
#   * box width, row font (and the unchanged height / position) are li values in the builder;
#   * row texts: each cutscene's text ID (table 0x802C0C30, +0xC) is pointed at a text slot of
#     ours through the text table trick (award_text_id); the menu's title (text 2632), "View
#     Cutscenes" (434) and "Options" (429) entries in the text table point straight at our texts.
# The client never changes a text the menu is showing (its centring is worked out when the menu
# is built): each row has two buffers, and only the one not on screen is written.
SHOP_ROWS = 13
SHOP_SIZES = (13, 26, 39, 52, 65)
SHOP_MAX = SHOP_SIZES[-1]
SHOP_RESTOCK_ITEM_NAME = "Progressive Shop Restock"
TROPHY_POINTS = (10, 20, 30, 40)                 # per grade, Bronze to Platinum
STORY_POINTS = (15, 35, 50)                      # per difficulty, Easy to Hard
KILL_POINTS = 1
# Trophy filler items: points only. (grade, points, weight when picking one at random)
TROPHY_FILLERS = (("Bronze", 10, 4), ("Silver", 20, 3), ("Gold", 30, 2), ("Platinum", 40, 1))
TROPHY_FILLER_COPIES = 20                        # copies joining the weapon buff / resistance mix
TROPHY_FILLER_WEIGHT = 1.0
# Price ranges by what the item is (points).
SHOP_PRICES = {"progression": (15, 200), "useful": (5, 75), "filler": (1, 15)}
SHOP_STORY_PRICES = (85, 200)                    # story levels (this game's or Future Perfect's)


def shop_location_name(index: int) -> str:
    return f"Archipelago Shop Item {index + 1}"


def shop_location_id(index: int) -> int:
    return BASE_ID + 950 + index


def trophy_filler_item_name(grade: str) -> str:
    return f"{grade} Trophy"


TROPHY_FILLER_ITEM_NAMES: tuple[str, ...] = tuple(trophy_filler_item_name(t[0]) for t in TROPHY_FILLERS)
TROPHY_FILLER_POINTS = {trophy_filler_item_name(grade): points for grade, points, _w in TROPHY_FILLERS}

SHOP_MENU_POINTER = 0x803269CC
SHOP_MENU_BUILDER = 0x80198E20
SHOP_CUTSCENE_TABLE = 0x802C0C30                 # 13 x 16 bytes, +0xC = the row's text ID
SHOP_TEXT_IDS = {"title": 2632, "menu": 434, "options": 429}
SHOP_ORIGINAL_TEXT = {"title": "Select cutscene", "menu": "View Cutscenes", "options": "Options"}
SHOP_NEW_TEXT = {"menu": "Archipelago Shop", "options": "Options & Shop"}
SHOP_SELECTED_ROW = 0x8021A78C                   # (list) -> the row the cursor is on
SHOP_CENTRE_ROW = 0x80213BD4                     # (row) -> x offset centring its text (row +0x34)
SHOP_WIDTH, SHOP_FONT = 600, 4                   # the user's choice (the game's: 270, font 21)
# (address, the game's word, ours)
SHOP_CODE_CHANGES = (
    (0x80198E6C, 0x3880010E, 0x38800000 | SHOP_WIDTH),     # li r4, box width
    (0x80198F20, 0x38800015, 0x38800000 | SHOP_FONT),      # li r4, row font
    (0x80198E94, 0x4BFA57B9, 0x38600001),                  # bl 0x8013E64C -> li r3, 1
    (0x80198ED4, 0x4BFA5779, 0x38600001),
    (0x80198F48, 0x3C60801A, 0x3C608000),                  # lis r3, high(callback)
    (0x80198F4C, 0x38039094, 0x38031880),                  # addi r0, r3, low(callback)
)
# Low memory (0x80001800-0x8000180B is the system's; ours ends before the award screen's 0x80002300).
SHOP_WRAPPER = 0x80001840
SHOP_CALLBACK = 0x80001880
SHOP_PICK = 0x80001910                           # row + 1 of the last A press (+0x100: not bought)
SHOP_OPENED = 0x80001914                         # how many times the menu has been opened
SHOP_AFFORD = 0x80001920                         # 13 words: 1 = A buys this row now
SHOP_NEXT_TEXT = 0x80001960                      # 13 words: the text a row switches to when bought
SHOP_SLOTS = 0x800019A0                          # 16 text pointers: rows, title, menu, options
SHOP_TEXTS = 0x80001A00                          # 26 x 80 bytes (two per row), then 3 x 64
SHOP_ROW_TEXT_SIZE, SHOP_TEXT_SIZE = 80, 64
SHOP_TITLE, SHOP_MENU, SHOP_OPTIONS = 26, 27, 28  # text buffer numbers
SHOP_AREA_END = SHOP_TEXTS + 26 * SHOP_ROW_TEXT_SIZE + 3 * SHOP_TEXT_SIZE
assert SHOP_AREA_END <= AWARD_HEADING_TEXT
assert SHOP_CODE_CHANGES[-1][2] == 0x38030000 | (SHOP_CALLBACK & 0xFFFF)


def shop_text_address(n: int) -> int:
    if n < 2 * SHOP_ROWS:
        return SHOP_TEXTS + SHOP_ROW_TEXT_SIZE * n
    return SHOP_TEXTS + SHOP_ROW_TEXT_SIZE * 2 * SHOP_ROWS + SHOP_TEXT_SIZE * (n - 2 * SHOP_ROWS)


def shop_text_size(n: int) -> int:
    return SHOP_ROW_TEXT_SIZE if n < 2 * SHOP_ROWS else SHOP_TEXT_SIZE


def _build_shop_wrapper() -> tuple[int, ...]:
    low = SHOP_OPENED & 0xFFFF
    code = [
        0x3D608000,                              # lis   r11, 0x8000
        0x818B0000 | low,                        # lwz   r12, OPENED(r11)
        0x398C0001,                              # addi  r12, r12, 1
        0x918B0000 | low,                        # stw   r12, OPENED(r11)
        0x3D800000 | SHOP_MENU_BUILDER >> 16,    # lis   r12, builder@h
        0x618C0000 | SHOP_MENU_BUILDER & 0xFFFF, # ori   r12, r12, builder@l
        0x3960000A,                              # li    r11, 10      (cache lines, to 0x80198F60)
        0x7D6903A6,                              # mtctr r11
        0x7C0067AC,                              # loop: icbi 0, r12
        0x398C0020,                              # addi  r12, r12, 0x20
        0x4200FFF8,                              # bdnz  loop
        0x4C00012C,                              # isync
    ]
    code.append(_branch(SHOP_WRAPPER + 4 * len(code), SHOP_MENU_BUILDER))
    assert SHOP_WRAPPER + 4 * len(code) <= SHOP_CALLBACK
    assert all(SHOP_MENU_BUILDER <= a < SHOP_MENU_BUILDER + 10 * 32 for a, _g, _o in SHOP_CODE_CHANGES)
    return tuple(code)


def _build_shop_callback() -> tuple[int, ...]:
    def low(address: int) -> int:
        return address & 0xFFFF
    code = [
        0x9421FFE0,                              # 0  stwu  r1, -0x20(r1)
        0x7C0802A6,                              # 1  mflr  r0
        0x90010024,                              # 2  stw   r0, 0x24(r1)
        0x93E1001C,                              # 3  stw   r31, 0x1c(r1)
        _branch(SHOP_CALLBACK + 16, SHOP_SELECTED_ROW) | 1,   # 4  bl the selected row
        0x7C7F1B79,                              # 5  mr.   r31, r3
        0x41820000 | (29 - 6) * 4,               # 6  beq   out
        0x809F0018,                              # 7  lwz   r4, 0x18(r31)       row number
        0x3CA08000,                              # 8  lis   r5, 0x8000
        0x5486103A,                              # 9  slwi  r6, r4, 2
        0x38E50000 | low(SHOP_AFFORD),           # 10 addi  r7, r5, AFFORD
        0x7C07302E,                              # 11 lwzx  r0, r7, r6
        0x2C000000,                              # 12 cmpwi r0, 0
        0x38840001,                              # 13 addi  r4, r4, 1           pick = row + 1
        0x40820000 | (17 - 14) * 4,              # 14 bne   buy
        0x38840100,                              # 15 addi  r4, r4, 0x100       not bought
        0x48000000 | (28 - 16) * 4,              # 16 b     store
        0x38000000,                              # 17 buy: li r0, 0
        0x7C07312E,                              # 18 stwx  r0, r7, r6          not twice
        0x38E50000 | low(SHOP_NEXT_TEXT),        # 19 addi  r7, r5, NEXT_TEXT
        0x7C07302E,                              # 20 lwzx  r0, r7, r6
        0x901F0020,                              # 21 stw   r0, 0x20(r31)       the row's new text
        0x90810008,                              # 22 stw   r4, 0x8(r1)
        0x7FE3FB78,                              # 23 mr    r3, r31
        _branch(SHOP_CALLBACK + 96, SHOP_CENTRE_ROW) | 1,     # 24 bl centre it
        0x907F0034,                              # 25 stw   r3, 0x34(r31)
        0x80810008,                              # 26 lwz   r4, 0x8(r1)
        0x3CA08000,                              # 27 lis   r5, 0x8000
        0x90850000 | low(SHOP_PICK),             # 28 store: stw r4, PICK(r5)
        0x83E1001C,                              # 29 out: lwz r31, 0x1c(r1)
        0x80010024,                              # 30 lwz   r0, 0x24(r1)
        0x7C0803A6,                              # 31 mtlr  r0
        0x38210020,                              # 32 addi  r1, r1, 0x20
        0x4E800020,                              # 33 blr
    ]
    assert SHOP_CALLBACK + 4 * len(code) <= SHOP_PICK
    return tuple(code)


SHOP_WRAPPER_CODE = _build_shop_wrapper()
SHOP_CALLBACK_CODE = _build_shop_callback()
# Shop hints (the "Shop Hints" option).
SHOP_HINTS_NONE, SHOP_HINTS_ALL, SHOP_HINTS_PROGRESSION = 0, 1, 2

# Items bought in the shop are kept off the award screen. The client's own lines simply leave them
# out; the game's own lines (characters, cheats, hats, maps, modes, the Brick) come from comparing
# what is unlocked with a snapshot taken earlier (0x8019B9BC, kept in the menu data at
# 0x803EADD0), so the client marks such an item as already unlocked in that snapshot.
AWARD_SNAPSHOT = 0x803EADD0
AWARD_SNAPSHOT_CHARACTERS = AWARD_SNAPSHOT + 0x268     # 127 words, by character entry
AWARD_SNAPSHOT_MAPS = AWARD_SNAPSHOT + 0x464           # 19 words, by map entry
AWARD_SNAPSHOT_CHEATS = AWARD_SNAPSHOT + 0x194         # 13 words, by cheat entry
AWARD_SNAPSHOT_HATS = AWARD_SNAPSHOT + 0x1C8           # 5 words, by hat
AWARD_SNAPSHOT_MODES = AWARD_SNAPSHOT + 0x1DC          # 19 words, by mode number
AWARD_SNAPSHOT_BRICK = 0x80468FFC                      # r13-0x6E84
AWARD_SNAPSHOT_ASSAULT = {"Hangar": 0x80469000, "Scrapyard": 0x80469004}   # r13-0x6E80 / -0x6E7C


def _native_award_slots() -> dict[str, tuple[int, ...]]:
    slots: dict[str, list[int]] = {}
    for entry, (name, _address, _number) in enumerate(CHARACTERS):
        slots.setdefault(character_item_name(name), []).append(AWARD_SNAPSHOT_CHARACTERS + 4 * entry)
    for name, _address, entry in MAPS:
        slots.setdefault(map_item_name(name), []).append(AWARD_SNAPSHOT_MAPS + 4 * entry)
    for name, address in AWARD_SNAPSHOT_ASSAULT.items():
        slots.setdefault(map_item_name(name), []).append(address)
    for name, _address, entry in CHEATS:
        slots.setdefault(cheat_item_name(name), []).append(AWARD_SNAPSHOT_CHEATS + 4 * entry)
    for name, _address, number in HATS:
        slots.setdefault(hat_item_name(name), []).append(AWARD_SNAPSHOT_HATS + 4 * number)
    for name, _address, number in MODES:
        slots.setdefault(mode_item_name(name), []).append(AWARD_SNAPSHOT_MODES + 4 * number)
    slots.setdefault(weapon_item_name("Brick"), []).append(AWARD_SNAPSHOT_BRICK)
    return {name: tuple(addresses) for name, addresses in slots.items()}


NATIVE_AWARD_SLOTS = _native_award_slots()

# TimeSplitters: Future Perfect (the user's other apworld): its items are shortened in this game's
# shop and award screen the same way it does itself. Its story level items are priced as story
# levels in the shop.
TSFP_GAME_NAME = "TimeSplitters Future Perfect"
TSFP_STORY_ITEM_NAMES = (
    "2401 Time To Split", "1924 Scotland the Brave", "1969 The Russian Connection", "1969 The Khallos Express",
    "1994 Mansion of Madness", "1994 What Lies Below", "2052 Breaking and Entering", "2052 You Genius, U Genix",
    "2243 Machine Wars", "2243 Something to Crow About", "1924 You Take The High Road", "2401 The Hooded Man",
    "1924 Future Perfect", "Progressive Story Level",
)
MISSION_ITEM_PREFIXES = ("AL - ", "HL - ", "EL - ", "Challenge - ")


def tsfp_short_item_name(name: str) -> str:
    """"AL - One Gun Fun - Rockets 101" -> "Rockets 101" (split at the first two " - ", so a mission
    name with a dash of its own stays whole); "Weapon Buff - Plasma Autorifle - +25% Reserve Ammo"
    -> "Plasma Autorifle +25% Reserve Ammo"; anything else as it is."""
    if name.startswith(MISSION_ITEM_PREFIXES):
        parts = name.split(" - ", 2)
        if len(parts) == 3:
            return parts[2]
    if name.startswith("Weapon Buff - "):
        parts = name.split(" - ", 2)
        if len(parts) == 3:
            return f"{parts[1]} {parts[2]}"
    return name


# Kills: player 1's kills this match, a float at the start of the per-match stats (0x803C1200,
# 0x754 bytes per player; stat 0 = kills, see the arcade award notes).
PLAYER_KILLS = 0x803C1200


def _build_award_cave() -> tuple[int, ...]:
    """Entered with r29 = the game's list length; leaves through AWARD_RETURN with the new length in
    r3 and the game's return address back in r0."""
    def d(op, rt, ra, imm): return (op << 26) | (rt << 21) | (ra << 16) | (imm & 0xFFFF)
    def x(rt, ra, rb, xo): return (31 << 26) | (rt << 21) | (ra << 16) | (rb << 11) | (xo << 1)
    def slwi(ra, rs, n): return (21 << 26) | (rs << 21) | (ra << 16) | (n << 11) | ((31 - n) << 1)
    def cmpwi(ra, imm): return d(11, 0, ra, imm)
    def cmpw(ra, rb): return x(0, ra, rb, 0)
    low = lambda address: address - 0x80000000
    high = (AWARD_LIST + 0x8000) >> 16
    names = AWARD_NAME_OFFSET
    labels: dict[str, int] = {}
    code: list = []
    def label(name): labels[name] = len(code)
    def bc(kind, name): code.append((kind, name))          # resolved below
    code += [x(29, 3, 29, 444),                          # mr r3, r29                 game's length
             d(32, 0, 1, 0x44),                          # lwz r0, 0x44(r1)           who asked
             d(15, 11, 0, AWARD_OTHER_CHECK >> 16),
             d(24, 11, 11, AWARD_OTHER_CHECK & 0xFFFF),
             cmpw(0, 11)]
    bc("beq", "return")                                  # never at the other menu flow's check
    code += [d(15, 11, 0, AWARD_AFTER_MISSION_CHECK >> 16),
             d(24, 11, 11, AWARD_AFTER_MISSION_CHECK & 0xFFFF),
             cmpw(0, 11)]
    bc("bne", "go")                                      # the award screen itself: always
    code += [d(15, 11, 0, (AWARD_CONTEXT + 0x8000) >> 16),
             d(32, 11, 11, AWARD_CONTEXT & 0xFFFF),
             cmpwi(11, AWARD_CONTEXT_ARCADE)]
    bc("bne", "return")                                  # after-mission check: Arcade League only
    label("go")
    code += [d(15, 12, 0, 0x8000),                       # lis r12, 0x8000
             d(36, 12, 12, low(AWARD_SHOWN)),            # stw r12, SHOWN(r12)
             d(32, 5, 12, low(AWARD_FRONT_COUNT)),       # lwz r5, FRONT_COUNT(r12)   F
             d(32, 4, 12, low(AWARD_COUNT)),             # lwz r4, COUNT(r12)         all entries
             d(15, 6, 0, high),                          # lis r6, list@ha
             d(14, 6, 6, AWARD_LIST - (high << 16)),     # addi r6, r6, list@l
             d(14, 7, 0, 0), d(14, 8, 0, 0)]             # j = 0, kept = 0
    label("filter")                                      # drop the game's entries with a hidden heading
    code.append(cmpw(7, 3)); bc("bge", "filtered")
    code += [slwi(10, 7, 2), x(0, 6, 10, 23), cmpwi(0, AWARD_HIDDEN_HEADING)]
    bc("beq", "drop")
    code += [slwi(11, 8, 2), x(0, 6, 11, 151),           # heading
             d(14, 10, 10, names), d(14, 11, 11, names),
             x(0, 6, 10, 23), x(0, 6, 11, 151),          # name
             d(14, 8, 8, 1)]
    label("drop")
    code.append(d(14, 7, 7, 1)); bc("b", "filter")
    label("filtered")
    code += [x(8, 3, 8, 444),                            # mr r3, r8                  entries kept
             d(14, 7, 3, -1)]                            # addi r7, r3, -1            i = last entry
    label("shift")                                       # move the game's entries down by F
    code.append(cmpwi(7, 0)); bc("blt", "front")
    code += [x(10, 7, 5, 266), cmpwi(10, AWARD_MAX)]
    bc("bge", "next")
    code += [slwi(11, 7, 2), slwi(10, 10, 2),
             x(0, 6, 11, 23), x(0, 6, 10, 151),          # lwzx r0,r6,r11 / stwx r0,r6,r10
             d(14, 11, 11, names), d(14, 10, 10, names),
             x(0, 6, 11, 23), x(0, 6, 10, 151)]
    label("next")
    code.append(d(14, 7, 7, -1)); bc("b", "shift")
    label("front")                                       # the client's first F entries at the top
    code += [d(14, 7, 0, 0), d(14, 9, 12, low(AWARD_ENTRIES))]
    label("front_loop")
    code.append(cmpw(7, 5)); bc("bge", "front_done")
    code += [slwi(10, 7, 2), d(32, 0, 9, 0), x(0, 6, 10, 151), d(14, 10, 10, names),
             d(32, 0, 9, 4), x(0, 6, 10, 151), d(14, 9, 9, 8), d(14, 7, 7, 1)]
    bc("b", "front_loop")
    label("front_done")
    code += [x(3, 3, 5, 266), cmpwi(3, AWARD_MAX)]       # length = min(length + F, 10)
    bc("ble", "back")
    code.append(d(14, 3, 0, AWARD_MAX))
    label("back")                                        # the client's other entries at the end
    code.append(cmpw(7, 4)); bc("bge", "return")
    code.append(cmpwi(3, AWARD_MAX)); bc("bge", "return")
    code += [slwi(10, 3, 2), d(32, 0, 9, 0), x(0, 6, 10, 151), d(14, 10, 10, names),
             d(32, 0, 9, 4), x(0, 6, 10, 151), d(14, 9, 9, 8), d(14, 7, 7, 1), d(14, 3, 3, 1)]
    bc("b", "back")
    label("return")
    code.append(d(32, 0, 1, 0x44))                       # lwz r0, 0x44(r1): the game loaded its return
    code.append(("b", "@return"))                        # address there just before the hooked line
    conditions = {"blt": (12, 0), "bge": (4, 0), "ble": (4, 1), "beq": (12, 2), "bne": (4, 2)}
    words = []
    for k, item in enumerate(code):
        if isinstance(item, tuple):
            kind, name = item
            offset = (AWARD_RETURN - (AWARD_CAVE + 4 * k)) if name == "@return" else 4 * (labels[name] - k)
            if kind == "b":
                item = 0x48000000 | (offset & 0x03FFFFFC)
            else:
                bo, bi = conditions[kind]
                item = (16 << 26) | (bo << 21) | (bi << 16) | (offset & 0xFFFC)
        words.append(item)
    assert AWARD_CAVE + 4 * len(words) <= AWARD_MENU_ROUTINE
    return tuple(words)


AWARD_CAVE_CODE = _build_award_cave()
AWARD_HOOK_BRANCH = _branch(AWARD_HOOK, AWARD_CAVE)
AWARD_MENU_ROUTINE_CODE = (
    0x3D800000 | AWARD_HOOK >> 16,                 # lis  r12, high
    0x618C0000 | AWARD_HOOK & 0xFFFF,              # ori  r12, r12, low
    0x7C0067AC,                                    # icbi 0, r12
    0x4C00012C,                                    # isync
    _branch(AWARD_MENU_ROUTINE + 16, AWARD_MENU_NORMAL),
)
assert AWARD_MENU_ROUTINE + 4 * len(AWARD_MENU_ROUTINE_CODE) <= AWARD_FRONT_COUNT


def award_text_id(table: int, pointer_address: int) -> int:
    """A text ID that the game's text lookup turns into the pointer stored at pointer_address."""
    return ((pointer_address - table) & 0xFFFFFFFF) >> 2

# ---- Easier trophy requirements ----
# Each mission record (e.g. Top Shot's at 0x80318AFC, which starts with its name and description
# text IDs) points at +0x1C to its list of 0x14-byte conditions; a trophy's time limit is the word
# after the condition type, in frames (60 a second). (address, normal value, easier value)
EASIER_TROPHIES: dict[str, tuple[tuple[int, int, int], ...]] = {
    # Top Shot: come 1st within this time. Platinum 2:00 (normally 1:10); Silver 4:00 and Gold 3:00 stay.
    "easier_top_shot": ((0x80318AE4, 70 * 60, 120 * 60),),
}
EASIER_TROPHY_NAMES = {
    "easier_top_shot": "Top Shot",
}

FILLER_ITEM_NAME = "Nothing"
VICTORY_ITEM_NAME = "Victory"
# ---- Milestones ----
# A Bronze or better on every mission of a group, a league or all Challenges.
MILESTONE_TROPHY = 1    # Bronze
MILESTONE_ARCADE_GROUPS, MILESTONE_CHALLENGE_GROUPS, MILESTONE_LEAGUES, MILESTONE_ALL_CHALLENGES = range(4)
LEAGUE_NAMES = {"AL": "Amateur League", "HL": "Honorary League", "EL": "Elite League"}
# (location name, location ID, the missions it needs, kind)
MILESTONES: tuple[tuple[str, int, tuple[Mission, ...], int], ...] = (
    *(
        (f"{prefix} - {group} - Group Completed", BASE_ID + 300 + g,
         tuple(m for m in MISSIONS if m.group_number == g),
         MILESTONE_CHALLENGE_GROUPS if prefix == "Challenge" else MILESTONE_ARCADE_GROUPS)
        for g, (prefix, group, _missions) in enumerate(GROUPS)
    ),
    *(
        (f"{league} Completed", BASE_ID + 330 + k, tuple(m for m in MISSIONS if m.prefix == prefix),
         MILESTONE_LEAGUES)
        for k, (prefix, league) in enumerate(LEAGUE_NAMES.items())
    ),
    ("All Challenges Completed", BASE_ID + 333, tuple(m for m in MISSIONS if m.prefix == "Challenge"),
     MILESTONE_ALL_CHALLENGES),
)

# Goal events (they have no ID: the client reports the goal itself).
STORY_GOAL_LOCATION_NAME = f"{STORY_LEVELS[FINAL_STORY_LEVEL]} Completed"
TROPHY_GOAL_LOCATION_NAME = "Trophy Hunt Completed"
# Trophy Hunt: which missions count.
HUNT_ARCADE, HUNT_CHALLENGES, HUNT_ALL = 0, 1, 2


def hunted_missions(setting: int) -> tuple["Mission", ...]:
    if setting == HUNT_ARCADE:
        return tuple(m for m in MISSIONS if m.prefix != "Challenge")
    if setting == HUNT_CHALLENGES:
        return tuple(m for m in MISSIONS if m.prefix == "Challenge")
    return MISSIONS


def location_name(mission: Mission, tier: int) -> str:
    """tier is 1 (Bronze) to 4 (Platinum)."""
    return f"{mission.item_name} ({TIERS[tier - 1]})"


def location_id(mission_number: int, tier: int) -> int:
    return BASE_ID + mission_number * len(TIERS) + (tier - 1)


LOCATION_NAME_TO_ID: dict[str, int] = {
    location_name(mission, tier): location_id(mission.number, tier)
    for mission in MISSIONS
    for tier in range(1, len(TIERS) + 1)
}
LOCATION_NAME_TO_ID.update({
    story_location_name(level, d): story_location_id(level, d)
    for level in range(len(STORY_LEVELS))
    for d in range(len(STORY_DIFFICULTIES))
})
LOCATION_NAME_TO_ID.update({
    objective_location_name(level, name): objective_location_id(level, record)
    for level, record, _address, _text, name, _roles in STORY_OBJECTIVES
})
LOCATION_NAME_TO_ID.update({name: location_id for name, location_id, _missions, _kind in MILESTONES})
EASY_ONLY_OBJECTIVES = _easy_only_objectives()
LOCATION_NAME_TO_ID.update({cartridge_location_name(c[0], c[1]): cartridge_location_id(k)
                            for k, c in enumerate(CARTRIDGES)})
LOCATION_NAME_TO_ID.update({anaconda_location_name(step * ANACONDA_STEP): anaconda_location_id(step * ANACONDA_STEP)
                            for step in range(1, ANACONDA_MAX_STEPS + 1)})
LOCATION_NAME_TO_ID.update({name: retroracer_location_id(k) for k, name in enumerate(retroracer_location_names())})
LOCATION_NAME_TO_ID.update({astrolander_location_name(level): astrolander_location_id(level)
                            for level in range(1, ASTROLANDER_LEVEL_COUNT + 1)})
LOCATION_NAME_TO_ID.update({shop_location_name(k): shop_location_id(k) for k in range(SHOP_MAX)})
assert len(set(LOCATION_NAME_TO_ID.values())) == len(LOCATION_NAME_TO_ID)

ITEM_NAME_TO_ID: dict[str, int] = {
    **{m.item_name: BASE_ID + 1000 + m.number for m in MISSIONS},
    **{story_item_name(k): BASE_ID + 1100 + k for k in range(len(STORY_LEVELS))},
    PROGRESSIVE_STORY_ITEM_NAME: BASE_ID + 1150,
    **{cartridge_item_name(c[0]): BASE_ID + 1200 + k for k, c in enumerate(CARTRIDGES)},
    FILLER_ITEM_NAME: BASE_ID + 2000,
    BEHEAD_MULTIPLIER_ITEM_NAME: BASE_ID + 6000,
    STARTING_ARMOUR_ITEM_NAME: BASE_ID + 6002,      # (6001 was the Monkeying Around multiplier)
    **{name: BASE_ID + 7000 + k for k, name in enumerate(WEAPON_BUFF_ITEM_NAMES)},
    **{name: BASE_ID + 7500 + k for k, name in enumerate(TRAP_ITEM_NAMES)},
    **{name: BASE_ID + 7600 + k for k, name in enumerate(RESISTANCE_ITEM_NAMES)},
    SHOP_RESTOCK_ITEM_NAME: BASE_ID + 7700,
    **{name: BASE_ID + 7710 + k for k, name in enumerate(TROPHY_FILLER_ITEM_NAMES)},
    **{character_item_name(c[0]): BASE_ID + 3000 + c[2] for c in CHARACTERS},
    **{cheat_item_name(c[0]): BASE_ID + 4000 + c[2] for c in CHEATS},
    **{hat_item_name(h[0]): BASE_ID + 4100 + h[2] for h in HATS},
    **{map_item_name(m[0]): BASE_ID + 4200 + m[2] for m in MAPS},
    **{mode_item_name(m[0]): BASE_ID + 4300 + m[2] for m in MODES},
    **{weapon_item_name(w[0]): BASE_ID + 5000 + w[1] for w in WEAPON_ENTRIES},
}
assert len(ITEM_NAME_TO_ID) == (MISSION_COUNT + len(STORY_LEVELS) + 4 + len(CARTRIDGES) + len(WEAPON_BUFFS) + len(TRAPS) + len(RESISTANCES) + 1 + len(TROPHY_FILLERS) + len(CHARACTERS) + len(CHEATS) + len(HATS)
                               + len(MAPS) + len(MODES) + len(WEAPON_ENTRIES))
