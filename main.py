import argparse
import importlib
import os

sb = importlib.import_module("solomonbot")

parser = argparse.ArgumentParser(
    description="A Discord bot for organizing competitive games."
)
parser.add_argument("--key", help="Discord bot authentication key")
args = parser.parse_args()

sb.bot.run(args.key or os.getenv("DISCORD_BOT_KEY"))