from copy import deepcopy
import discord
from discord.ext import commands
import random
import sqlite3

_default_state = {
    "maps": {
        "arena": {
            "Aquarena",
            "Authority",
            "Calico",
            "Cerberus",
            "Chasm",
            "Skyway",
            "Vertex",
        },
        "byo5": {
            "Brynhildr",
            "Coral",
            "Elite",
            "Exhumed",
            "Ingonyama",
            "Kryosis",
            "Minora",
            "NightFlare",
            "Raptor",
            "TwilightGrove",
        },
        "ctf": {
            "Authority",
            "BeachBlitz",
            "Brynhildr",
            "Cerberus",
            "Coral",
            "CrushDepth",
            "Drought",
            "Elite",
            "Exhumed",
            "FatalFortress",
            "Gloomlands",
            "Icedance",
            "Ingonyama",
            "Kryosis",
            "Minora",
            "NightFlare",
            "Outpost",
            "Raptor",
            "RiftValley",
            "Tolar",
            "Trailblazer",
            "TwilightGrove",
            "Zephyr",
        },
        "ctf-ladder": {
            "Brynhildr",
            "Coral",
            "Elite",
            "Exhumed",
            "Ingonyama",
            "Kryosis",
            "Minora",
            "NightFlare",
            "Outpost",
            "Raptor",
            "RiftValley",
            "Trailblazer",
            "TwilightGrove",
        },
        "tdm": {
            "Authority",
            "Blitz",
            "Calypso",
            "Cerberus",
            "Crystalline",
            "Skyway",
            "Speedway",
            "Tribulus",
            "Zephyr",
        },
    },
    "rulesets": {
        "ctf-byo5": {
            "pool": "byo5",
            "order": "~pp~bbbbbbbr",
        },
        "ctf-ladder": {
            "pool": "ctf-ladder",
            "order": "pppppppp6?",
        },
        "ctf-ladder-bans": {
            "pool": "ctf-ladder",
            "order": "bbbbpppppppp6?",
        },
    },
    "active-pickbans-by-user": {},
}
state = deepcopy(_default_state)

db = sqlite3.connect("solomonbot.sqlite3")
db.row_factory = sqlite3.Row

bot = commands.Bot(command_prefix="$")


@bot.command()
async def maps(ctx: commands.Context, pool=None):
    """List the maps available for picks/bans."""
    if pool is None:
        embed = discord.Embed()
        for pool_name, maps in state["maps"].items():
            embed.add_field(
                name="`{}`".format(pool_name),
                value=", ".join(sorted(maps)),
                inline=False,
            )
        await ctx.send("Available map pools:", embed=embed)
        return

    map_list = state["maps"].get(pool)
    if not map_list:
        valid_pools = ", ".join("`{}`".format(m) for m in sorted(state["maps"]))
        await ctx.send(
            "No maps found for specified pool. (Valid pools: {})".format(valid_pools)
        )
        return

    await ctx.send(", ".join("`{}`".format(m) for m in sorted(map_list)))


@bot.command()
async def cancel(ctx: commands.Context):
    """Cancel a pick/ban process."""
    actives = state["active-pickbans-by-user"]
    process = actives.get(ctx.author)
    if not process:
        await ctx.send(
            "You do not have an active pick/ban process. Start one with the `pickban` command."
        )
        return
    captain1, captain2 = process["captains"]
    actives.pop(captain1, None)
    actives.pop(captain2, None)
    await ctx.send(
        "Cancelled pick/ban process for {} and {}.".format(
            captain1.mention, captain2.mention
        )
    )


@bot.command()
async def rulesets(ctx: commands.Context, choice=None):
    """List the pre-defined rulesets available for picks/bans."""
    if choice is None:
        embed = discord.Embed()
        for ruleset_name, config in state["rulesets"].items():
            embed.add_field(
                name="`{}`".format(ruleset_name),
                value="Map pool: `{}`, order: `{}`".format(
                    config["pool"], config["order"]
                ),
                inline=False,
            )
        await ctx.send("Available rulesets:", embed=embed)
        return

    config = state["rulesets"].get(choice)
    if not config:
        valid_rulesets = ", ".join("`{}`".format(r) for r in sorted(state["rulesets"]))
        await ctx.send(
            "No ruleset found with the specified name. (Valid rulesets: {})".format(
                valid_rulesets
            )
        )
        return

    await ctx.send(
        "Map pool: `{}`, order: `{}`".format(config["pool"], config["order"])
    )


@bot.command()
async def ruleset(
    ctx: commands.Context, choice, captain1: discord.Member, captain2: discord.Member
):
    """Begin a pick/ban process using a predefined ruleset."""
    config = state["rulesets"].get(choice)
    if not config:
        valid_rulesets = ", ".join("`{}`".format(m) for m in sorted(state["rulesets"]))
        await ctx.send(
            "The specified ruleset was not found. (Valid rulesets: {})".format(
                valid_rulesets
            )
        )
        return

    await pickban(ctx, captain1, captain2, config["pool"], config["order"])


@bot.command()
async def pickban(
    ctx: commands.Context,
    captain1: discord.Member,
    captain2: discord.Member,
    pool="ctf",
    order="pp" "bb" "bb" "bb" "r",
):
    """Begin a pick/ban process.

    'captain1' and 'captain2' must be @-mentions of the two captains.

    'pool' is the name of a defined map pool.
        It can optionally be specified as #/pool (e.g. 7/ctf) to randomly
        generate a sub-pool of that many maps from the named pool.

    'order' is specified as a sequence of the following:
        p: next captain picks a map from the remaining pool
        b: next captain bans a map from the remaining pool
        r: randomly pick a map from the remaining pool
        ~: swap the order of the captains for subsequent picks and bans

        Optionally, a digit (1-9) followed by ?s can be added to the end.
        The digit turns that many previous picks into options for a random
        selection instead of actual picks, and then each following ? will
        pick a map from that set. (So 'pppppppp6?' will pick 2 maps, then
        pick 6 more maps, using those last 6 maps to randomly select 1 -
        a total of three maps actually played.)

    """
    actives = state["active-pickbans-by-user"]
    acceptable = tuple("pbr123456789?~")
    digits = tuple("123456789")

    # Make sure neither captain is already picking
    busy_captains = {c.mention for c in (captain1, captain2) if c in actives}
    if busy_captains:
        await ctx.send(
            "These captain(s) are already busy: {}".format(", ".join(busy_captains))
        )
        return

    # Get the pool of maps
    digit_prefix, _, pool_name = pool.rpartition("/")
    pool_size = int(digit_prefix) if digit_prefix else None
    map_list = state["maps"].get(pool_name)
    if not map_list:
        valid_pools = ", ".join("`{}`".format(m) for m in sorted(state["maps"]))
        await ctx.send(
            "No maps found for specified pool. (Valid pools: {})".format(valid_pools)
        )

    # Validate the pick/ban order specification
    seen_digit = False
    seen_question_mark = False
    for action in order:
        if action not in acceptable:
            await ctx.send(
                "Invalid pick/ban process order."
                "> Must consist only of `p`, `b`, `r`, and/or a digit followed by `?`s."
            )
            return
        if seen_question_mark and action != "?":
            await ctx.send(
                "Invalid pick/ban process order. All `?` must be at the end after a digit."
            )
            return
        if action == "?":
            if not seen_digit:
                await ctx.send(
                    "Invalid pick/ban process order. All `?` must be at the end after a digit."
                )
                return
            seen_question_mark = True
        if action in digits:
            if seen_digit:
                await ctx.send(
                    "Invalid pick/ban process order. Only one digit is allowed."
                )
                return
            seen_digit = True

    process = {
        "captains": (captain1, captain2),
        "pool": set(random.sample(map_list, pool_size) if pool_size else map_list),
        "picks": [],
        "bans": [],
        "order": order,
        "reversals": 0,
    }
    actives[captain1] = actives[captain2] = process
    embed = discord.Embed()
    if pool_size:
        embed.add_field(
            name="Pool", value="`{}` (random {})".format(pool_name, pool_size)
        )
    else:
        embed.add_field(name="Pool", value="`{}`".format(pool_name))
    embed.add_field(name="Order", value="`{}`".format(process["order"]))
    embed.add_field(
        name="Available Maps",
        value=", ".join("`{}`".format(m) for m in process["pool"]),
        inline=False,
    )
    await ctx.send(
        "Starting pick/ban with {} and {} as captains.".format(
            captain1.mention, captain2.mention
        ),
        embed=embed,
    )

    await check_next(ctx, process)


@bot.command()
async def pick(ctx: commands.Context, choice):
    """Pick a map to during a pick/ban process."""
    await pick_or_ban(ctx, "picks", choice)


@bot.command()
async def ban(ctx: commands.Context, choice):
    """Ban a map during a pick/ban process."""
    await pick_or_ban(ctx, "bans", choice)


@bot.command()
async def status(ctx: commands.Context):
    """Check the status of the current pick/ban process."""
    actives = state["active-pickbans-by-user"]
    process = actives.get(ctx.author)
    if not process:
        await ctx.send(
            "You do not have an active pick/ban process. Start one with the `pickban` command."
        )
        return
    await check_next(ctx, process)


@bot.command()
async def remaining(ctx: commands.Context):
    """List the maps remaining in the pool for a pick/ban process."""
    actives = state["active-pickbans-by-user"]
    process = actives.get(ctx.author)
    if not process:
        await ctx.send(
            "You do not have an active pick/ban process. Start one with the `pickban` command."
        )
        return
    embed = discord.Embed()
    embed.add_field(
        name="Available Maps",
        value=", ".join("`{}`".format(m) for m in process["pool"]),
    )
    await ctx.send("Remaining in the pool:", embed=embed)


def fuzzy_choice(options, choice):
    """Match a choice with one of multiple options in a human-friendly way.

    Will always match either one or none of the options. If a choice is ambiguous,
    it will choose to match none of them."""
    # Exact match, case-insensitive
    for option in options:
        if option.lower() == choice.lower():
            return option
    # Prefix match, case-insensitive
    potential_options = []
    for option in options:
        if option.lower().startswith(choice.lower()):
            potential_options.append(option)
    if potential_options:
        if len(potential_options) == 1:
            return potential_options[0]
        return None
    # Acronym match, case insensitive
    potential_options = []
    for option in options:
        acronym = "".join(letter for letter in option if "A" <= letter <= "Z")
        if len(acronym) > 1 and acronym.lower() == choice.lower():
            potential_options.append(option)
    if potential_options:
        if len(potential_options) == 1:
            return potential_options[0]
        return None
    return None


async def pick_or_ban(ctx: commands.Context, action, choice):
    """Shared logic between picks and bans."""
    actives = state["active-pickbans-by-user"]
    captain = ctx.author

    # We're actively picking?
    process = actives.get(captain)
    if not process:
        await ctx.send(
            "You do not have an active pick/ban process. Start one with the `pickban` command."
        )
        return

    total_actions = len(process["picks"] + process["bans"]) + process["reversals"]
    next_captain = process["captains"][total_actions % 2]
    next_action = process["order"][total_actions]

    # Our turn?
    if captain != next_captain:
        await ctx.send(
            "It's currently {}'s turn, not yours.".format(next_captain.mention)
        )
        return

    # Next action is a pick?
    if action == "picks" and next_action != "p":
        await ctx.send("The next action is a ban, not a pick. Use `ban` instead.")
        return

    # Next action is a ban?
    if action == "bans" and next_action != "b":
        await ctx.send("The next action is a pick, not a ban. Use `pick` instead.")
        return

    # Our selection is still available?
    choice = fuzzy_choice(process["pool"], choice)
    if not choice:
        embed = discord.Embed()
        embed.add_field(
            name="Available Maps",
            value=", ".join("`{}`".format(m) for m in sorted(process["pool"])),
        )
        await ctx.send("That choice isn't in the pool.", embed=embed)
        return

    process["pool"].remove(choice)
    process[action].append(choice)

    await check_next(ctx, process)


async def check_next(ctx: commands.Context, process):
    """Check for potential automated action in a pick/ban process and output status."""
    actives = state["active-pickbans-by-user"]
    total_actions = len(process["picks"] + process["bans"]) + process["reversals"]

    # Complete?
    if total_actions >= len(process["order"]):
        captain1, captain2 = process["captains"]
        embed = discord.Embed()
        embed.add_field(
            name="Picks",
            value=", ".join("`{}`".format(m) for m in process["picks"]) or "-",
        )
        embed.add_field(name="Bans", value=", ".join(process["bans"]) or "-")
        await ctx.send(
            "{} and {} have completed the pick/ban process:".format(
                captain1.mention,
                captain2.mention,
            ),
            embed=embed,
        )
        actives.pop(captain1, None)
        actives.pop(captain2, None)
        return

    next_captain = process["captains"][total_actions % 2]
    next_action = process["order"][total_actions]
    later_actions = process["order"][total_actions + 1 :]

    # Complete with random subset of picks?
    if next_action in tuple("123456789"):
        captain1, captain2 = process["captains"]
        subpool_size = int(next_action)
        subpool_selections = sum(action == "?" for action in later_actions)

        preserved_picks = process["picks"][:-subpool_size]
        subpool = process["picks"][-subpool_size:]
        selections = random.sample(subpool, subpool_selections)
        embed = discord.Embed()
        embed.add_field(
            name="Picks",
            value=(
                ", ".join(["__{}__".format(m) for m in preserved_picks] + subpool)
                or "*n/a*"
            ),
        )
        embed.add_field(name="Bans", value=(", ".join(process["bans"]) or "*n/a*"))
        embed.add_field(
            name="Selections",
            value=", ".join("`{}`".format(m) for m in preserved_picks + selections),
            inline=False,
        )
        await ctx.send(
            "{} and {} have completed the pick/ban process:".format(
                captain1.mention,
                captain2.mention,
            ),
            embed=embed,
        )
        actives.pop(captain1, None)
        actives.pop(captain2, None)
        return

    # Pick
    if next_action == "p":
        if not process["pool"]:
            await ctx.send("Unable to continue: ran out of maps in the pool.")
            await cancel(ctx)
            return
        await ctx.send("{}, it's your turn to pick.".format(next_captain.mention))
        return
    # Ban
    if next_action == "b":
        if not process["pool"]:
            await ctx.send("Unable to continue: ran out of maps in the pool.")
            await cancel(ctx)
            return
        await ctx.send("{}, it's your turn to ban.".format(next_captain.mention))
        return
    # Random
    if next_action == "r":
        auto_selections = []
        while next_action == "r":
            if not process["pool"]:
                await ctx.send(
                    "Failed to automatically select a map: no maps remaining in pool."
                )
                await cancel(ctx)
                return
            choice = random.choice(list(process["pool"]))
            process["pool"].remove(choice)
            process["picks"].append(choice)
            auto_selections.append(choice)
            total_actions += 1
            next_action = process["order"][total_actions : total_actions + 1]
        await ctx.send(
            "Automatically selected {} from the remaining pool.".format(
                ", ".join("`{}`".format(m) for m in auto_selections)
            )
        )
    # Swap
    if next_action == "~":
        process["reversals"] += 1

    await check_next(ctx, process)


@bot.command()
async def signup(ctx: commands.Context):
    """Sign up for a draft tournament."""

    if get_setting("signups") != "on":
        await ctx.send("Signups are not currently enabled.")
        return

    c = db.cursor()
    u = ctx.author

    signedup = c.execute(
        "SELECT mention FROM signups WHERE mention = ?;", (u.mention,)
    ).fetchone()
    if signedup:
        await ctx.send("You're already signed up, {}.".format(u.mention))
        return

    c.execute(
        "INSERT INTO signups (mention, display_name) VALUES (?, ?);",
        (u.mention, u.display_name),
    )
    db.commit()
    signups = c.execute("SELECT COUNT(1) AS total FROM signups;").fetchone()
    await ctx.send(
        "{} is now signed up (#{}, {}).".format(
            u.mention, signups["total"], u.display_name
        )
    )


@bot.command()
async def withdraw(ctx: commands.Context):
    """Withdraw from a draft tournament."""

    if get_setting("signups") != "on":
        await ctx.send("Signups are not currently enabled.")
        return

    c = db.cursor()
    u = ctx.author

    signedup = c.execute(
        "SELECT mention FROM signups WHERE mention = ?;", (u.mention,)
    ).fetchone()
    if not signedup:
        await ctx.send("You're not signed up, {}.".format(u.mention))
        return

    c.execute("DELETE FROM signups WHERE mention = ?;", (u.mention,))
    db.commit()
    await ctx.send("Your signup has been withdrawn, {}.".format(u.mention))


@bot.command()
async def checkin(ctx: commands.Context):
    """Check in for a draft tournament."""

    if get_setting("checkins") != "on":
        await ctx.send("Checkins are not currently enabled.")
        return

    c = db.cursor()
    u = ctx.author

    signedup = c.execute(
        "SELECT mention, checkin_time FROM signups WHERE mention = ? OR mention = ?;",
        (u.mention, u.mention.replace("@!", "@")),
    ).fetchone()
    if not signedup:
        await ctx.send("You're not signed up, {}.".format(u.mention))
        return
    if signedup["checkin_time"]:
        await ctx.send("You're already checked in, {}.".format(u.mention))
        return

    c.execute(
        "UPDATE signups SET checkin_time = CURRENT_TIMESTAMP WHERE mention = ? OR mention = ?;",
        (u.mention, u.mention.replace("@!", "@")),
    )
    db.commit()
    checkins = c.execute(
        "SELECT COUNT(1) AS total FROM signups WHERE checkin_time IS NOT NULL;"
    ).fetchone()
    await ctx.send(
        "{} has checked in (#{}, {}).".format(
            u.mention, checkins["total"], u.display_name
        )
    )


@bot.command()
async def signups(ctx: commands.Context):
    """List the currently signed up players for a draft tournament."""
    c = db.cursor()

    signedup = c.execute(
        "SELECT display_name FROM signups ORDER BY signup_time ASC;"
    ).fetchall()
    if not signedup:
        await ctx.send("No players signed up.")
        return

    embed = player_list_embed(signedup)
    await ctx.send("{} players signed up.".format(len(signedup)), embed=embed)


@bot.command()
async def checkins(ctx: commands.Context):
    """List the currently checked in players for a draft tournament."""
    c = db.cursor()

    checkedin = c.execute(
        "SELECT display_name FROM signups WHERE checkin_time IS NOT NULL ORDER BY checkin_time ASC;"
    ).fetchall()
    if not checkedin:
        await ctx.send("No players checked in.")
        return

    embed = player_list_embed(checkedin)
    await ctx.send("{} players checked in.".format(len(checkedin)), embed=embed)


def player_list_embed(player_list, group_size=20):
    """Generates a discord embed that lists a set of players, grouped into fields."""
    embed = discord.Embed()
    group_count = (len(player_list) - 1) // group_size
    for g in range(group_count + 1):
        start = g * group_size
        end = (g + 1) * group_size
        players = player_list[start:end]
        range_label = "{}-{}:".format(start + 1, start + len(players))
        player_text = "\n".join(p["display_name"] for p in players)
        embed.add_field(name=range_label, value=player_text)
    return embed


@bot.command(hidden=True)
@commands.is_owner()
async def setting(ctx: commands.Context, name: str, data: str):
    set_setting(name, data)
    await ctx.send("Set `{}` to `{}`.".format(name, data))


@bot.command(hidden=True)
@commands.is_owner()
async def enable(ctx: commands.Context, name: str):
    await setting(ctx, name, "on")


@bot.command(hidden=True)
@commands.is_owner()
async def disable(ctx: commands.Context, name: str):
    await setting(ctx, name, "off")


def get_setting(name):
    c = db.cursor()
    result = c.execute("SELECT data FROM settings WHERE name = ?;", (name,)).fetchone()
    if not result:
        return None
    return result["data"]


def set_setting(name, data):
    c = db.cursor()
    c.execute(
        "INSERT OR REPLACE INTO settings (name, data) VALUES (?, ?);", (name, data)
    )
    db.commit()


@bot.command(hidden=True)
async def whoami(ctx: commands.Context):
    """Respond with the Discord API ID of the invoker."""
    u = ctx.author
    await ctx.send("{} you are {} = `{}`".format(u.mention, u.display_name, u.mention))


@bot.command(hidden=True)
@commands.is_owner()
async def dbwipe(ctx: commands.Context):
    """Reset the database of persistent state."""
    c = db.cursor()
    c.executescript(
        """
        DROP TABLE IF EXISTS settings;
        CREATE TABLE settings (
            name TEXT PRIMARY KEY,
            data TEXT NOT NULL
        );
        
        DROP TABLE IF EXISTS signups;
        CREATE TABLE signups (
            mention TEXT PRIMARY KEY,
            display_name TEXT,
            signup_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            checkin_time TIMESTAMP DEFAULT NULL
        );
    """
    )
    db.commit()


@bot.command(hidden=True)
@commands.is_owner()
async def user(ctx: commands.Context, u: discord.Member = None):
    user = u or ctx.author
    await ctx.send("{}: {}".format(user.mention, user))


@bot.command(hidden=True)
@commands.is_owner()
async def wipe(ctx: commands.Context):
    """Clear all non-default state for the bot."""
    global state
    state = deepcopy(_default_state)
    await ctx.send("Global state wiped.")


@bot.command(hidden=True)
@commands.is_owner()
async def shutdown(ctx: commands.Context):
    """Shut down the bot process."""
    await ctx.send("Shutting down.")
    await bot.logout()