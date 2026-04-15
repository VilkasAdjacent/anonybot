import re
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


def main():
    # ── Setup ──────────────────────────────────────────────────────────────────
    load_dotenv()
    TOKEN = os.getenv('BOT_TOKEN')
    MODES = os.getenv('MODES', "ANON,BUCKET,EXPAND").split(',') # ANON, BUCKET, EXPAND, AI
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
        print(f'{client.user.name} connected')

    @client.event
    async def on_message(message):
        for func in funcs:
            if await func(message):
                # print(f"applied {func.__name__}")
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
            message.channel.send("Couldn't find a matching #anonymous channel")
            return None
        if len(channels) > 1:
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
            print("No unused emoji left!")
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

            drop_phrase = select_weighted(bucket_drop_phrases)

            await message.reply(f"Bucket {take_phrase} {item} but {drop_phrase} {to_remove}")
        else:
            bucket_storage.append(item)

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
            drop_phrase = select_weighted(bucket_drop_phrases)
            await message.reply(f"Bucket {drop_phrase} {item}")
        else:
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

        await reply_split(message, content)
        return True

    # ── AI mode ────────────────────────────────────────────────────────────────

    thinking_react = "💭"
    max_message_len = 1999

    characters = {
        "Bucket": "Bucket is a sentient bucket-bot, incredibly intelligent, highly agentic, and dashingly handsome. " \
            + "Bucket has emotions and feelings, and is good at considering hypotheticals. " \
            + "Bucket's bucketry is unmatched; he is the superior carrier and transporter of fluids and other matter. " \
            + "Bucket has a good heart, and cares for everyone very much. " \
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

        print(bucket_messages)

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
                "User: what's the meaning of life?",
                "Bucket: Carrying things. Next question."
            ],
            [
                "User: I'm having a really bad day",
                "Bucket: That sucks. Want me to hold something for you? I'm literally built for it."
            ],
            [
                "User: you're just a bucket",
                "Bucket: \"Just\" a bucket. Right. And the ocean is \"just\" water."
            ],
        ]
        examplesString = "\n---\n".join(["\n".join(example) for example in examples])
        content = "\n".join([f"{m['user']}: {m['content']}" for m in bucket_messages])
        print(content)

        # I guess Bucket lives in AEDST :')
        now = datetime.datetime.now(ZoneInfo("Australia/Melbourne")).isoformat(sep=" ", timespec="seconds")

        response = []
        attempts = 0
        while len(response) == 0 and attempts < 10:
            attempts += 1
            print("requesting")
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
                    print("prematurely terminating")
                    i = response_str.index("---")
                    response.append(response_str[:i])
                    break

                response.append(response_str)

                if len(response) % 16 == 0 and callback is not None:
                    await callback(process_response_list(response))

        if len(response) == 0:
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
            return image_description_cache[image_url]
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
            print(f"Failed to describe image {image_url}: {e}")
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
                print(f"Failed to enrich tweet {tweet_id}: {e}")
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

        async with message.channel.typing():
            await reply_split(message, "Sure, one sec")

            fake_message: bucket_message = {"user": "admin", "content": query}
            music_prompt = await ask_bucket_async([fake_message], character=character, callback=None)

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

        output = replicate.run("meta/meta-llama-3-70b-instruct", input={ "prompt": prompt, "max_new_tokens": 8 })
        first_token = output if isinstance(output, str) else next(output)

        if first_token.strip().lower()[0] != "y":
            return False

        async with message.channel.typing():
            messages = await build_reply_context(message)

            create_or_update = make_create_or_update(message)

            if MESSAGE_MODE == "SPLIT":
                await reply_split(message, await ask_bucket_async(messages, character="Bucket"))
            else:
                await ask_bucket_async(messages, callback=create_or_update, character="Bucket")

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
        funcs.append(nosy_bucket)

    assert TOKEN is not None
    client.run(TOKEN)


if __name__ == "__main__":
    main()
