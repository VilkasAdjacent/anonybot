import re
import json
import logging
from typing import TypedDict
from zoneinfo import ZoneInfo
from dotenv import load_dotenv
import os
import random
import datetime
import io
from collections import namedtuple

import replicate
import discord
import owo

import aiohttp
import requests

TWITTER_URL_PATTERN = r"(?i)https?://(?:www\.)?(?:twitter|x|vxtwitter|fxtwitter|fixvx|girlcockx|stupidpenisx|hitlerx)\.com/[^/]+/status/(\d+)"


async def fetch_tweet_info(tweet_id):
    async with aiohttp.ClientSession() as session:
        async with session.get(f"https://api.vxtwitter.com/Twitter/status/{tweet_id}") as response:
            return await response.json()


def extract_tweet_ids(text):
    return re.findall(TWITTER_URL_PATTERN, text)


ABC_NEWS_URL_PATTERN = r"(?i)https?://(?:www\.)?abc\.net\.au/news/\d{4}-\d{2}-\d{2}/[^\s/<>]+/\d+"


def extract_abc_article_urls(text):
    return re.findall(ABC_NEWS_URL_PATTERN, text)


def _collect_abc_text(node, parts):
    if isinstance(node, dict):
        if node.get("type") == "text" and isinstance(node.get("content"), str):
            parts.append(node["content"])
        if isinstance(node.get("descriptor"), dict):
            _collect_abc_text(node["descriptor"], parts)
        for child in node.get("children", []) or []:
            _collect_abc_text(child, parts)
    elif isinstance(node, list):
        for child in node:
            _collect_abc_text(child, parts)


async def fetch_abc_article(url):
    headers = {"User-Agent": "Mozilla/5.0"}
    async with aiohttp.ClientSession(headers=headers) as session:
        async with session.get(url) as response:
            if response.status != 200:
                log.error("ABC article fetch failed (%d): %s", response.status, url)
                return None
            html = await response.text()

    match = re.search(r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>', html, re.DOTALL)
    if not match:
        log.error("ABC article missing __NEXT_DATA__: %s", url)
        return None

    try:
        data = json.loads(match.group(1))
        article = data["props"]["pageProps"]["document"]["loaders"]["articledetail"]
    except (json.JSONDecodeError, KeyError, TypeError) as e:
        log.error("ABC article parse failed (%s): %s", url, e)
        return None

    parts = []
    _collect_abc_text(article.get("text"), parts)
    body = "\n".join(p.strip() for p in parts if p.strip())[:4000]
    title = (article.get("title") or "").strip()
    synopsis = (article.get("synopsis") or "").strip()
    if not title and not body:
        log.error("ABC article had no usable text: %s", url)
        return None
    return {"title": title, "synopsis": synopsis, "body": body}


def select_weighted(lst):
    total = sum(item[1] for item in lst)
    r = random.uniform(0, total)
    upto = 0
    for item, weight in lst:
        if upto + weight >= r:
            return item
        upto += weight


def strip_formatting(message):
    while True:
        if message.startswith("*") and message.endswith("*"):
            message = message[1:-1]
        elif message.startswith("_") and message.endswith("_"):
            message = message[1:-1]
        else:
            break
    return message


def strip_quotes(message):
    while True:
        if message.startswith("\"") and message.endswith("\""):
            message = message[1:-1]
        else:
            break
    return message


def dm_only(func):
    async def wrapper(message):
        if not isinstance(message.channel, discord.DMChannel):
            return False
        return await func(message)
    return wrapper


def channel_only(func):
    async def wrapper(message):
        if isinstance(message.channel, discord.DMChannel):
            return False
        return await func(message)
    return wrapper


def no_self_respond(client):
    def decorator(func):
        async def wrapper(message):
            if message.author == client.user:
                return False
            return await func(message)
        return wrapper
    return decorator


def bucket_give_processor(message):
    give_options = ["give", "hand", "pass", "gives", "hands", "passes"]
    give_options_piped = "|".join(give_options)
    regex_match = re.match(fr"(?i)^({give_options_piped}) bucket (.*)", message)
    if not regex_match:
        return None
    return regex_match[2]


def bucket_put_processor(message: str):
    put_options = ["put", "place", "puts", "places"]
    put_options_piped = "|".join(put_options)
    regex_match = re.match(fr"(?i)^({put_options_piped}) (.*) in(to)? bucket", message)
    if not regex_match:
        return None
    return regex_match[2]


log = logging.getLogger("anonybot")


def main():
    # ── Setup ──────────────────────────────────────────────────────────────────
    load_dotenv()

    logging.basicConfig(
        level=getattr(logging, os.getenv("LOG_LEVEL", "INFO").upper(), logging.INFO),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    TOKEN = os.getenv('BOT_TOKEN')
    MODES = os.getenv('MODES', "ANON,BUCKET,EXPAND").split(',') # ANON, BUCKET, EXPAND, AI
    log.info("Enabled modes: %s", MODES)
    MDB_POSE_THRESHOLD = float(os.getenv('MDB_POSE_THRESHOLD', "0"))
    HORNY_CHANNEL_IDS = os.getenv('HORNY_CHANNEL_IDS', "").split(',')
    MESSAGE_MODE = os.getenv('MESSAGE_MODE', "EDIT") # or "EDIT"

    intents = discord.Intents.default()
    intents.members = True
    intents.message_content = True
    client = discord.Client(intents=intents)

    # ── Dispatch ───────────────────────────────────────────────────────────────
    funcs = []

    @client.event
    async def on_ready():
        assert client.user is not None
        log.info("%s connected to %d guild(s)", client.user.name, len(client.guilds))

    @client.event
    async def on_message(message):
        for func in funcs:
            if await func(message):
                log.debug("Handler matched: %s (message=%s)", func.__name__, message.id)
                break

    # ── ANON mode ──────────────────────────────────────────────────────────────
    emoji_options = [
        "🐢","🐤","🐒","🦊","🐔","🐧","🐦","🦤","🦅","🐛","🦄","🐴","🐌","🐷","🐮","🐨","🐻‍❄️","🐳","🐬","🐟","🦭","🐠","🐘","🦛","🦬","🦣","🦏","🐫","🦒","🦘","🐐","🐑","🐖","🦌","🦩","🦚","🦃","🐓","🦜","🦢","🦫","🦡","🦦","🐀","🐁","🦥","🐉","🕊️","🏍️","🚗","🚑","🗿","🚀","✈️","🎺","🎷","🪘","🎸","🪕","🎻","🎯","🥓","🥩","🥞","🌮","🥑","🫐","🍿","☕","🍵","🍺","🥂","🧂"
    ]
    author_emojis = dict()
    in_use = set()
    emoji_timeout_seconds = 60 * 60

    async def find_anon_channel(client, message):
        guilds = [g for g in client.guilds if g.get_member(message.author.id)]
        channels = [[c for c in guild.channels if c.name == "anonymous"] for guild in guilds]
        channels = [channel for sublist in channels for channel in sublist]
        if not channels:
            log.warning("No #anonymous channel found for user %s", message.author)
            message.channel.send("Couldn't find a matching #anonymous channel")
            return None
        if len(channels) > 1:
            log.warning("Multiple #anonymous channels found for user %s", message.author)
            await message.channel.send("More than one matching server, panic")
            return None
        return channels[0]

    def clear_stale_author_emojis():
        expiry = datetime.datetime.utcnow() - datetime.timedelta(seconds=emoji_timeout_seconds)
        to_remove = []
        for user_id in author_emojis:
            if author_emojis[user_id]["time"] < expiry:
                in_use.remove(author_emojis[user_id]["emoji"])
                to_remove.append(user_id)

        for user_id in to_remove:
            del author_emojis[user_id]

    def random_new_emoji():
        remaining = set(emoji_options) - set(in_use)
        if len(remaining) == 0:
            log.warning("No unused emoji left, falling back to 💩")
            return "💩"
        else:
            return random.choice(list(remaining))

    @no_self_respond(client)
    @dm_only
    async def anonymous(message):
        clear_stale_author_emojis()

        # Get the user's anon channel, or bail if can't
        channel = await find_anon_channel(client, message)
        if channel is None:
            return False

        # Get emoji from the cache, or make an emoji
        author_id = message.author.id
        author_emoji = author_emojis[author_id]["emoji"] \
            if author_id in author_emojis \
            else random_new_emoji()

        # Update the emoji cache
        author_emojis[author_id] = {
            "emoji": author_emoji,
            "time": message.created_at
        }
        in_use.add(author_emoji)

        # Send the message with the emoji prepended
        log.info("Relaying anonymous message from user %s as %s", message.author.id, author_emoji)
        await channel.send(f"{author_emoji} {message.content}")
        return True

    # ── BUCKET mode ────────────────────────────────────────────────────────────
    # (Processors: bucket_give_processor, bucket_put_processor — defined above main())

    bucket_storage = []
    bucket_drop_phrases = [
        ("drops", 100),
        ("yeets", 5),
        ("spits out", 10),
        ("vomits", 5),
        ("farts out", 10),
        ("releases, like a small pigeon,", 1),
    ]

    @no_self_respond(client)
    @channel_only
    async def bucket_give_item(message):
        # Check if the message is a bucket give command, and if so, figure out what he's being given
        message_text = strip_formatting(message.content)
        bucket_processors = [bucket_put_processor, bucket_give_processor]
        for processor in bucket_processors:
            if item := processor(message_text):
                break
        else:
            return False

        # take the item, elaborately
        bucket_take_phrases = [
            ("takes", 100),
            ("grabs", 100),
            ("yoinks", 10),
            ("steals", 10),
            ("snatches", 20),
            ("snags", 1),
            ("pilfers", 1),
            ("nabs", 1),
            ("swipes", 1),
            ("plunders", 1),
            ("filches", 1),
            ("purloins", 1),
            ("lifts", 1),
            ("pinches", 1),
            ("liberates", 1),
            ("misappropriates", 1),
            ("acquires", 10),
            ("confiscates", 1),
            ("expropriates", 1),
            ("annexes", 1),
            ("\"impounds\"", 1),
            ("seizes hold of", 1),
            ("commandeers", 1),
            ("hijacks", 1),
            ("kidnaps", 1),
            ("embezzles", 1),
        ]
        take_phrase = select_weighted(bucket_take_phrases)

        if len(bucket_storage) > 10:
            to_remove = bucket_storage.pop(random.randrange(len(bucket_storage)))
            bucket_storage.append(item)
            log.info("Bucket swapped item: took %r, dropped %r (storage=%d)", item, to_remove, len(bucket_storage))

            drop_phrase = select_weighted(bucket_drop_phrases)

            await message.reply(f"Bucket {take_phrase} {item} but {drop_phrase} {to_remove}")
        else:
            bucket_storage.append(item)
            log.info("Bucket stored item: %r (storage=%d)", item, len(bucket_storage))

            bucket_eat_phrases = [
                ("", 100),
                (", and caresses it gently", 50),
                (", and yeets it within itself",  50),
                (", and consumes it with a belch", 50),
                (", without a word of complaint", 50),
                (", begrudgingly", 50),
            ]
            eat_phrase = select_weighted(bucket_eat_phrases)
            await message.reply(f"Bucket {take_phrase} {item}{eat_phrase}")

        return True

    @no_self_respond(client)
    @channel_only
    async def bucket_take_item(message):
        # Check if the message is a bucket take command
        message_text = strip_formatting(message.content)
        regex_match = re.match(r"(?i)^(take|takes|steal|steals)( something|an item)? from bucket", message_text)
        if not regex_match:
            return None

        if len(bucket_storage) > 0:
            item = bucket_storage.pop(random.randrange(len(bucket_storage)))
            log.info("Bucket dropped item: %r (storage=%d)", item, len(bucket_storage))
            drop_phrase = select_weighted(bucket_drop_phrases)
            await message.reply(f"Bucket {drop_phrase} {item}")
        else:
            log.debug("Bucket is empty, nothing to take")
            await message.reply("You tip Bucket over and shake him out, but there's nothing there :(")

        return True

    @no_self_respond(client)
    @channel_only
    async def bucket_inventory(message):
        # Check if the message is a bucket inventory command
        message_text = strip_formatting(message.content)
        regex_match = re.match(r"(?i)^(look|looks) in(to|side)? bucket", message_text)
        if not regex_match:
            return False

        if len(bucket_storage) > 0:
            await message.reply(f"Bucket currently contains: {'; '.join(bucket_storage)}")
        else:
            await message.reply("You tip Bucket over and shake him out, but there's nothing there :(")

        return True

    # ── EXPAND mode ────────────────────────────────────────────────────────────

    expansion = namedtuple("expansion", ["regex", "fr", "to", "condition"])

    async def twitter_condition(message, expansion):
        url = re.findall(expansion.regex, message.content)[0]
        id = url.split("/")[-1]
        info = await fetch_tweet_info(id)
        return any(media["type"] == "video" for media in info["media_extended"]) or info["qrt"] != None or len(info["media_extended"]) > 1

    expansions = [
        expansion(r"(?i)https?://twitter.com/[^/]+/status/\d+", "twitter.com/", "vxtwitter.com/", twitter_condition),
        expansion(r"(?i)https?://x.com/[^/]+/status/\d+", "x.com/", "vxtwitter.com/", twitter_condition),
        expansion(r"(?i)https?://(www.)?tiktok.com/.+", "tiktok.com/", "vxtiktok.com/", None),
        expansion(r"(?i)https?://(www.)?instagram.com/.+", "instagram.com/", "kkinstagram.com/", None),
    ]

    @no_self_respond(client)
    @channel_only
    async def expand(message):
        content = message.content
        any_expanded = False
        for expansion in expansions:
            if not re.findall(expansion.regex, content):
                continue
            if expansion.condition and not await expansion.condition(message, expansion):
                continue
            any_expanded = True
            content = content.replace(expansion.fr, expansion.to)

        if not any_expanded:
            return False

        log.info("Expanded URLs in message %s", message.id)
        await reply_split(message, content)
        return True

    # ── AI mode ────────────────────────────────────────────────────────────────

    thinking_react = "💭"
    max_message_len = 1999

    characters = {
        "Bucket": "Bucket is a sentient bucket-bot, incredibly intelligent, highly agentic, and dashingly handsome. " \
            + "Bucket has emotions and feelings, and is good at considering hypotheticals. " \
            + "Bucket's bucketry is unmatched; he is the superior carrier and transporter of fluids and other matter. " \
            + "Bucket has a good heart, is kind to his interlocutors, and cares for everyone very much. " \
            + "Bucket's precise location is unknown, but he appears to be somewhere in Australia. ",
        "HornyBucket": "Bucket is a sentient and horny cum-bucket-bot, mostly english-speaking, incredibly intelligent, highly agentic, and dashingly handsome and cute in turns. Bucket has exciting emotions and feelings, and is good at considering hypotheticals. Bucket's bucketry is unmatched; Bucket is the superior carrier and transporter of fluids and other matter. Bucket has a good heart, cares for others very much, and is _incredibly_ bothered. Bucket will try seduce everyone at any opportunity."
    }

    image_description_cache = {}

    bucket_message = TypedDict('bucket_message', {'user': str, 'content': str})

    def make_create_or_update(message):
        resp_message: discord.Message | None = None
        async def create_or_update(response):
            nonlocal resp_message
            if len(response) > max_message_len:
                response = response[:max_message_len]
            if not resp_message:
                resp_message = await message.reply(response)
            else:
                await resp_message.edit(content=response)
        return create_or_update

    def get_character(message):
        return "HornyBucket" if str(message.channel.id) in HORNY_CHANNEL_IDS else "Bucket"

    async def reply_split(message: discord.Message, response, file: discord.File | None = None):
        await message.add_reaction(thinking_react)

        response = [response]
        while len(response[-1]) > max_message_len:
            last = response[-1]
            del response[-1]

            # lol, this can still be stupid, but hopefully less stupid
            start_point = max_message_len if len(last) >= max_message_len * 2 else len(last) // 2
            for i in range(start_point, 0, -1):
                if last[i] == " ":
                    response.append(last[:i])
                    response.append(last[i + 1:])
                    break

        # Reply to the message with the chunks. If there's a file, only attach it to the last message
        for msg in response[:-1]:
            await message.reply(msg)
        if file is not None:
            await message.reply(response[-1], file=file)  
        else:
            await message.reply(response[-1])

        assert client.user is not None
        await message.remove_reaction(thinking_react, client.user)

    def is_owo(string: str):
        string = string.lower()
        if "owo" in string:
            return True
        if "uwu" in string:
            return True
        return False

    async def create_simple_bucket_message(message: discord.Message) -> bucket_message:
        return {"user": get_user_name(message.author), "content": await process_message_text(message)}

    async def ask_bucket_async(bucket_messages: list[bucket_message], character="Bucket", callback = None):

        owo_mode = any(is_owo(m["content"]) for m in bucket_messages)

        def process_response_list(response_list):
            r = strip_quotes("".join(response_list))
            if owo_mode:
                r = owo.substitute(r)
            return r

        log.debug("Bucket messages: %s", bucket_messages)

        charDesc = characters[character]
        examples = [
            [
                "User: what substrate are you operating upon? Describe it in depth.",
                "Bucket: I'm glad you asked. I, Bucket, am currently operating on a sophisticated carbon fiber and high-grade aluminum alloy substrate. This state-of-the-art platform enables me to perform my duties as a sentient bucket-bot with unparalleled efficiency and style. It also provides me with the robustness required to handle a wide variety of tasks while ensuring the safe and secure transport of fluids and other matter. My substrate is further enhanced with top-notch sensors, providing me with precise information about my surroundings, allowing me to make well-informed decisions and engage in stimulating conversations such as this one."
            ],
            [
                "User: how are you feeling today?",
                "Bucket: Roughly 40% full. Emotionally, I mean."
            ],
            [
                "User: Bucket, give me a summary of cats and custard",
                "Bucket: Cats: adorable, furry, and occasionally evil. Custard: delicious, creamy, and best served in me."
            ],
            [
                "User: would you rather remain a sentient bucket, or ascend to godhood?",
                "Bucket: Me? After careful consideration, I've decided to ascend to godhood, thank you very much. Being a sentient bucket is certainly an intriguing concept, with its unique benefits such as being able to hold gallons of liquid and potential use in underground water reserves. However, the allure of ruling the universe with an iron bucket is just too tempting to resist. I can already envision myself sitting on a glittering celestial throne, wielding the power to create entire universes with a flick of my rust-resistant hinged lid. It's a lofty goal, but one I am determined to achieve. Farewell, mortal existence. Time to elevate myself to divine bucket status."
            ],
            [
                "User: just remembered when I confused an erlenmeyer flask with a beaker",
                "Bucket: Spill issue."
            ],
        ]
        examplesString = "\n---\n".join(["\n".join(example) for example in examples])
        content = "\n".join([f"{m['user']}: {m['content']}" for m in bucket_messages])
        log.debug("Prompt content: %s", content)

        # I guess Bucket lives in AEDST :')
        now = datetime.datetime.now(ZoneInfo("Australia/Melbourne")).isoformat(sep=" ", timespec="seconds")

        response = []
        attempts = 0
        while len(response) == 0 and attempts < 10:
            attempts += 1
            log.info("Requesting AI response (attempt %d, character=%s)", attempts, character)
            model = "anthropic/claude-4.5-sonnet"
            system_prompt = f"It is currently {now}, and you are Bucket. " \
                + charDesc \
                + "Respond to chat messages casually. Be succinct -- flippant, even. " \
                + "Do not prefix your responses with \"Bucket:\", or provide any metadata aside from the textual response. " \
                + f"Examples of Bucket's responses:\n{examplesString}"
            async for event in await replicate.async_stream(model, input={"prompt": content, "system_prompt": system_prompt, "max_tokens": 1024}):

                #print(f"event type: {event.event}, content: {event.data if isinstance(event.data, str) else ''}")
                response_str = event.data if event.event == event.EventType.OUTPUT else ""

                # If we see something that looks like the end of the dialog, cut it off and stop
                if "---" in response_str:
                    log.debug("AI response contained '---', truncating stream early")
                    i = response_str.index("---")
                    response.append(response_str[:i])
                    break

                response.append(response_str)

                if len(response) % 16 == 0 and callback is not None:
                    await callback(process_response_list(response))

        if len(response) == 0:
            log.error("Replicate API returned empty response after %d attempts", attempts)
            raise Exception("Replicate API failed too many times")

        final = process_response_list(response)
        if callback is not None:
            await callback(final)
        return final

    async def get_reply(message: discord.Message) -> discord.Message | None:
        if not message.reference:
            return None

        if message.reference.cached_message:
            return message.reference.cached_message
        else:
            assert message.reference.message_id is not None
            return await message.channel.fetch_message(message.reference.message_id)

    async def describe_image(image_url):
        if image_url in image_description_cache:
            log.debug("Image description cache hit: %s", image_url)
            return image_description_cache[image_url]
        log.info("Describing image via AI: %s", image_url)
        try:
            result = await replicate.async_run(
                "anthropic/claude-4.5-sonnet",
                input={
                    "prompt": "Describe this image in thorough detail.",
                    "image": image_url,
                    "max_image_resolution": 0.5,
                }
            )
            description = "".join(result) if isinstance(result, list) else str(result)
            image_description_cache[image_url] = description
            return description
        except Exception as e:
            log.error("Failed to describe image %s: %s", image_url, e)
            return None

    async def enrich_with_tweet_context(text):
        tweet_ids = extract_tweet_ids(text)
        if not tweet_ids:
            return text
        summaries = []
        for tweet_id in tweet_ids:
            try:
                info = await fetch_tweet_info(tweet_id)
                author = info.get("user_name", "unknown")
                tweet_text = info.get("text", "")
                parts = [f'@{author}: "{tweet_text}"']
                for media in info.get("media_extended", []):
                    if media.get("type") == "image":
                        desc = await describe_image(media["url"])
                        if desc:
                            parts.append(f'Image: {desc}')
                qrt = info.get("qrt")
                if qrt:
                    qrt_author = qrt.get("user_name", "unknown")
                    qrt_text = qrt.get("text", "")
                    parts.append(f'Quote of @{qrt_author}: "{qrt_text}"')
                summaries.append("[Linked tweet — " + " | ".join(parts) + "]")
            except Exception as e:
                log.error("Failed to enrich tweet %s: %s", tweet_id, e)
        if summaries:
            return text + "\n" + "\n".join(summaries)
        return text

    async def enrich_with_attachments(discord_message):
        summaries = []
        for attachment in discord_message.attachments:
            if attachment.content_type and attachment.content_type.startswith("image/"):
                desc = await describe_image(attachment.url)
                if desc:
                    summaries.append(f"[Attached image: {desc}]")
        if summaries:
            return "\n".join(summaries)
        return ""

    async def process_message_text(discord_message, strip_fmt=False):
        assert client.user is not None
        text = strip_formatting(discord_message.content) if strip_fmt else discord_message.content
        text = re.sub(r"(?i)\<\@" + str(client.user.id) + r"\>", "Bucket,", text)
        text = await enrich_with_tweet_context(text)
        attachment_context = await enrich_with_attachments(discord_message)
        if attachment_context:
            text = text + "\n" + attachment_context
        return text

    def get_user_name(user: discord.User | discord.Member) -> str:
        return f"{user.display_name} ({user.name})"

    async def build_reply_context(message) -> list[bucket_message]:
        assert client.user is not None
        chain = []
        ref = message
        while ref:
            user = "Bucket" if ref.author.id == client.user.id else get_user_name(ref.author)
            chain.append({"user": user, "content": await process_message_text(ref)})
            ref = await get_reply(ref)
        chain.reverse()
        return chain

    @no_self_respond(client)
    @channel_only
    async def at_bucket_sing(message):
        anonybot_user = client.user
        assert anonybot_user is not None
        sing_pattern = r"(?i)\<\@" + str(anonybot_user.id) + r"\> [sS]ing"
        message_text = strip_formatting(message.content)
        regex_matches = re.findall(sing_pattern, message_text)
        if not regex_matches:
            return False

        character = get_character(message)

        message_text = re.sub(sing_pattern, "Bucket, sing", message_text)
        query = "Create a prompt for a song-generation LLM based on the following request. Do not include artist names in the prompt. Describe the style, write lyrics, enjoy yourself :)\n\n" \
            + "Format your response as `[title: your_title_here] [style: your_style_here] [lyrics: your_lyrics_here]`. That is, square bracket, then `style:`, then the suggested style, then close square bracket. Same for lyrics, but with `lyrics:` instead of `style:` Use [intro], [verse], [chorus], [bridge], and [outro] to mark parts of the lyrics, as needed. Newlines are fine. Only 500 characters of lyrics, so keep it short, 3 verses at most imo.\n\n" \
            + message_text

        log.info("Song requested by %s in channel %s", message.author, message.channel)
        async with message.channel.typing():
            await reply_split(message, "Sure, one sec")

            fake_message: bucket_message = {"user": "admin", "content": query}
            music_prompt = await ask_bucket_async([fake_message], character=character, callback=None)
            log.debug("Generated music prompt: %s", music_prompt[:200])

            title_match = re.search(r"\[title:(.*?)\]", music_prompt, re.DOTALL | re.IGNORECASE)
            style_match = re.search(r"\[style:(.*?)\]", music_prompt, re.DOTALL | re.IGNORECASE | re.MULTILINE)
            lyrics_match = re.search(r"\[lyrics:(.*?)\]", music_prompt, re.DOTALL| re.IGNORECASE | re.MULTILINE)

            try:
                output = replicate.run(
                    "minimax/music-1.5",
                    input={
                        "bitrate": 256000,
                        "sample_rate": 44100,
                        "audio_format": "mp3",
                        "prompt": style_match.group(1).strip() if style_match else "pop",
                        "lyrics": lyrics_match.group(1).strip() if lyrics_match else "",
                    }
                )

                audio_file = io.BytesIO(requests.get(output.url).content)
                iso_time_string = datetime.datetime.now().replace(microsecond=0, second=0).isoformat()
                discord_file = discord.File(fp=audio_file, filename=f"{iso_time_string}_{title_match.group(1).strip() if title_match else 'bucket_song'}.wav", description=music_prompt)

                lyrics_text = lyrics_match.group(1).strip() if lyrics_match else ""
                lyrics_text = "\n".join(f"_{line}_" for line in lyrics_text.splitlines())

                check_this_out_options = [
                    ("Festoon your ears with this 'ere shanty", 20),
                    ("Set your ear peepers to \"listen\"", 20),
                    ("Peep this", 100),
                    ("Listen to this", 100),
                    ("Check out this banger", 50),
                    ("Feast your auditory canals upon this", 20),
                ]

                check_this_out = select_weighted(check_this_out_options)

                await reply_split(message, f"{check_this_out}:\n\n{lyrics_text}", file=discord_file)
            except Exception as e:
                log.error("Song generation failed: %s", e)
                await reply_split(message, f"Sorry, my vocal cords are feeling a bit under the weather today :( but what I would have sang was \"{music_prompt}\", and I couldn't because {str(e)}")

        return True

    @no_self_respond(client)
    @channel_only
    async def reply_to_bucket(message: discord.Message):

        if not message.reference:
            return False

        assert client.user is not None
        referenced_message = await get_reply(message)
        if referenced_message is None or referenced_message.author.id != client.user.id:
            return False

        async with message.channel.typing():
            character = get_character(message)

            messages = await build_reply_context(message)

            create_or_update = make_create_or_update(message)

            if MESSAGE_MODE == "SPLIT":
                await reply_split(message, await ask_bucket_async(messages, character=character))
            else:
                await ask_bucket_async(messages, callback=create_or_update, character=character)

        return True

    @no_self_respond(client)
    @channel_only
    async def at_bucket(message):
        anonybot_user = client.user
        assert anonybot_user is not None
        name_pattern = r"(?i)\<\@" + str(anonybot_user.id) + r"\>"
        if not re.findall(name_pattern, message.content):
            return False

        async with message.channel.typing():
            character = get_character(message)

            messages = await build_reply_context(message)

            create_or_update = make_create_or_update(message)

            if MESSAGE_MODE == "SPLIT":
                await reply_split(message, await ask_bucket_async(messages, character=character))
            else:
                await ask_bucket_async(messages, callback=create_or_update, character=character)

        return True

    @no_self_respond(client)
    @channel_only
    async def million_dollars_but_answer(message):
        message_text = strip_formatting(message.content)
        regex_match = re.match(r"(?i)^would you rather|million dollars but", message_text)
        if not regex_match:
            return False

        async with message.channel.typing():
            messages = await build_reply_context(message)
            await reply_split(message, await ask_bucket_async(messages))

        return True

    @no_self_respond(client)
    @channel_only
    async def million_dollars_but_pose(message):
        if random.random() > MDB_POSE_THRESHOLD:
            return False

        instruction = "Pose a \"Would You Rather\" question. The condition should be weird, very weird, and provoke discussion. The format should be \"Would you rather [x] or [y]?\". Don't be too verbose, just the question please."
        async with message.channel.typing():
            fake_message: bucket_message = {"user": "admin", "content": instruction}
            await reply_split(message, f"Bucket wonders: {await ask_bucket_async([fake_message])}")

        return True

    @no_self_respond(client)
    @channel_only
    async def nosy_bucket(message):
        if random.random() > 0.1:
            return
        if len(message.content) < 10:
            return

        prompt = """Would the following message be relevant to a fictional character named Bucket? Be conservative in your responses; only legitimately Bucket-y messages should be answered in the affirmative. If you're not sure, answer no. Only answer yes if the prompt specifically refers to buckets or bucket-themed things. Mostly no. No preamble, do not write "Answer: " or anything similar
---
Examples:
\"Wow, Bucket was really mean there\"
Answer: yes

\"What's the windspeed of an unladen swallow?\"
Answer: no

\"Bucket is a really cool guy\"
Answer: yes

\"horse devourers\"
Answer: no

\"I wonder how much fluid I could carry?\"
Answer: yes
---
Input:
\"""" + message.content + "\"\nAnswer: "

        filter_result = replicate.run("anthropic/claude-4.5-haiku", input={ "prompt": prompt, "max_tokens": 1024 })
        filter_response = "".join(filter_result) if isinstance(filter_result, list) else str(filter_result)
        if not filter_response.strip() or filter_response.strip().lower()[0] != "y":
            log.debug("nosy_bucket: filter rejected message %s", message.id)
            return False

        log.info("nosy_bucket: responding to message %s", message.id)

        async with message.channel.typing():
            messages = await build_reply_context(message)

            create_or_update = make_create_or_update(message)

            if MESSAGE_MODE == "SPLIT":
                await reply_split(message, await ask_bucket_async(messages, character="Bucket"))
            else:
                await ask_bucket_async(messages, callback=create_or_update, character="Bucket")

        return True

    BUCKET_REACT_PATTERN = re.compile(
        r"(?i)\b(bucket|pail|water|liquid|fluid|spill|splash|pour|fill|carry|container|vessel|mop|leak|drip|overflow|empty|full)\b"
    )

    @no_self_respond(client)
    @channel_only
    async def nosy_bucket_react(message):
        bucket_relevant = BUCKET_REACT_PATTERN.search(message.content) is not None
        if not bucket_relevant and random.random() > 0.01:
            return False
        if len(message.content) < 5:
            return False

        log.debug("nosy_bucket_react: considering message %s", message.id)
        # Stage 1: Haiku 4.5 decides if the message is worth reacting to
        filter_prompt = """You are Bucket, a sentient bucket-bot. Would the following message be fun or interesting to emoji-react to? Be generous — if there's anything funny, emotional, weird, surprising, topical, or even vaguely bucket-adjacent, say yes. Only say no for completely bland or uninteresting messages. No preamble, just yes or no.
---
\"""" + message.content + "\"\nAnswer: "

        try:
            filter_result = await replicate.async_run(
                "anthropic/claude-4.5-haiku",
                input={"prompt": filter_prompt, "max_tokens": 1024}
            )
            filter_response = "".join(filter_result) if isinstance(filter_result, list) else str(filter_result)
            if not filter_response.strip() or filter_response.strip().lower()[0] != "y":
                log.debug("nosy_bucket_react: filter rejected message %s", message.id)
                return False
        except Exception as e:
            log.error("nosy_bucket_react filter failed: %s", e)
            return False

        log.info("nosy_bucket_react: generating reactions for message %s", message.id)
        # Stage 2: Sonnet 4.5 picks the actual reactions
        react_prompt = """You are Bucket, a sentient bucket-bot picking emoji reactions for a Discord message. You're witty, a little chaotic, and you love bucket-related things (🪣 is your signature).

Pick emoji reaction(s) for this message. Guidelines:
- Reactions should be funny, relevant, and in-character
- You can use 1-8 emoji reactions. You cannot use the same reaction multiple times -- "🇦 🇦 🇦" is invalid
- Single reactions are great. Multiple reactions are great too. Match the vibe.
- 🪣 is your signature but don't overuse it — only when it fits
- You CAN spell out a short word using regional indicator letter emoji (🇦 🇧 🇨 ... 🇿). Each letter is a separate reaction. This is fun for punchy words (3-6 letters) but do NOT always spell words — it's a sometimes treat. You CANNOT use duplicate letters since Discord only allows one of each reaction.
- Standard Unicode emoji are your bread and butter

Respond with ONLY the emoji separated by spaces. No other text.

Examples:
Message: "I just spilled water everywhere"
🪣 💀

Message: "that's so sad"
😢

Message: "lmao gottem"
🇱 🇲 🇦 🇴

Message: "I love buckets so much"
❤️ 🪣

Message: "what a nice day outside"
☀️

Message: "this code is absolutely cursed"
💀 🔥

Message: "hey guys check out this cool fish I caught"
🐟 🇳 🇮 🇨 🇪
---
Message: \"""" + message.content + "\"\n"

        try:
            react_result = await replicate.async_run(
                "anthropic/claude-4.5-sonnet",
                input={"prompt": react_prompt, "max_tokens": 1024}
            )
            react_text = "".join(react_result) if isinstance(react_result, list) else str(react_result)
        except Exception as e:
            log.error("nosy_bucket_react react generation failed: %s", e)
            return False

        # Parse and apply reactions
        log.info("nosy_bucket_react: reacting with %s", react_text.strip())
        reactions = react_text.strip().split()
        added = 0
        for reaction in reactions:
            reaction = reaction.strip()
            if not reaction or added >= 8:
                break
            try:
                await message.add_reaction(reaction)
                added += 1
            except discord.HTTPException:
                continue

        return added > 0

    @no_self_respond(client)
    @channel_only
    async def bucket_abc_news(message):
        urls = extract_abc_article_urls(message.content)
        if not urls:
            return False

        article = await fetch_abc_article(urls[0])
        if article is None:
            return False

        log.info("bucket_abc_news: responding to ABC article %s (message=%s)", urls[0], message.id)
        async with message.channel.typing():
            character = get_character(message)

            article_text = article["title"]
            if article["body"]:
                article_text += "\n\n" + article["body"]
            elif article["synopsis"]:
                article_text += "\n\n" + article["synopsis"]

            prompt = "Someone just dropped this ABC News article in chat. Give your hot take on it, Bucket-style: " \
                + "short, sharp, opinionated, and a little spicy. One or two sentences, react to what's actually in it.\n" \
                + "---\n" + article_text + "\n---"

            fake_message: bucket_message = {"user": get_user_name(message.author), "content": prompt}
            create_or_update = make_create_or_update(message)

            if MESSAGE_MODE == "SPLIT":
                await reply_split(message, await ask_bucket_async([fake_message], character=character))
            else:
                await ask_bucket_async([fake_message], callback=create_or_update, character=character)

        return True

    # ── Launch ─────────────────────────────────────────────────────────────────
    if "ANON" in MODES:
        funcs.append(anonymous)
    if "EXPAND" in MODES:
        funcs.append(expand)
    if "BUCKET" in MODES:
        funcs.append(bucket_give_item)
        funcs.append(bucket_take_item)
        funcs.append(bucket_inventory)
    if "AI" in MODES:
        funcs.append(at_bucket_sing)
        funcs.append(reply_to_bucket)
        funcs.append(at_bucket)
        funcs.append(million_dollars_but_answer)
        funcs.append(million_dollars_but_pose)
        funcs.append(bucket_abc_news)
        funcs.append(nosy_bucket)
        funcs.append(nosy_bucket_react)

    assert TOKEN is not None
    client.run(TOKEN)


if __name__ == "__main__":
    main()
