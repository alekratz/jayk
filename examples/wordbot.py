from jayk.cli.module import JaykMeta, jayk_command
import random
import time
import asyncio
import functools
import itertools
import operator
import sqlite3
from string import punctuation


class Wordbot(metaclass=JaykMeta):
    def __init__(self, leaderboard_database, wordlist, words_per_hour=50, hours_per_round=6, ignore=[], leaderboard_timeout=300, **kwargs):
        super().__init__(**kwargs)
        # user params
        self.leaderboard_database = leaderboard_database
        self.wordlist = wordlist
        self.words_per_hour = words_per_hour
        self.hours_per_round = hours_per_round
        self.ignore = ignore
        self.leaderboard_timeout = leaderboard_timeout
        # state objects
        self.present = False
        self.last_leader = 0
        self.words = set()
        self.scoreboard = {}
        self.actualnames = {}
        try:
            self.loop = asyncio.get_event_loop()
        except:
            self.loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self.loop)
        self.end_callback = None
        self.ensure_database()

    def on_join_room(self, client, room, who):
        if who is None:
            self.present = True
            if self.end_callback is None:
                self.new_game(client, room)
            else:
                self.debug("Wordbot was kicked and has since-rejoined without starting a new game")

    def on_leave_room(self, client, room, who):
        if who is None:
            self.present = False

    def on_unload(self):
        if self.end_callback is not None:
            self.cancel_endgame()
        self.loop.stop()

    def on_update_params(self, params):
        updates = [
                'leaderboard_database',
                'wordlist',
                'words_per_hour',
                'hours_per_round',
                'ignore',
                'leaderboard_timeout']
        for p in updates:
            if p in params:
                self.debug("Updating parameter %s", p)
                setattr(self, p, params[p])

    @jayk_command("!leaderboard")
    def leaderboard(self, client, cmd, room, sender, msg):
        if self.last_leader > time.time():
            return
        db = sqlite3.connect(self.leaderboard_database)
        cur = db.cursor()
        count = 1
        cur.execute("SELECT user,score FROM users ORDER BY score DESC LIMIT 5")
        for row in cur.fetchall():
            client.send_message(room, "{}. {}. {}".format(count, self.actual_name(row[0]), row[1]))
            count += 1
        cur.close()
        db.close()
        self.last_leader = time.time() + self.leaderboard_timeout

    def actual_name(self, sender):
        return self.actualnames[sender] if sender in self.actualnames else sender

    def on_message(self, client, room, sender, msg):
        if sender.nick in self.ignore:
            return
        super().on_message(client, room, sender, msg)  # Let the base class do base message handling
        word_set = set(filter(len, [word.strip(punctuation) for word in msg.split()]))
        matches = word_set & self.words
        if len(matches) > 0:
            nick = sender.nick
            smallnick = nick.lower()
            if smallnick not in self.scoreboard:
                self.scoreboard[smallnick] = 0
            if smallnick != nick and smallnick not in self.actualnames:
                self.actualnames[smallnick] = nick
            self.scoreboard[smallnick] += len(matches)
            for word in matches:
                client.send_message(room, "{}: Congrats! '{}' is good for 1 point.".format(nick, word))
            self.words -= matches
        if len(self.words) == 0:
            self.end_game()

    def new_game(self, client, room):
        """
        Runs the new-game logic. This cancels any waiting end_game callback that may be running, chooses a new set of
        words, and starts a new endgame callback to be called N hours from now.
        """
        if self.end_callback is not None:
            self.cancel_endgame()
        self.words = set()
        self.scoreboard = {}
        with open(self.wordlist) as fp:
            words = fp.read().split('\n')
        total_words = self.words_per_hour * self.hours_per_round
        if len(words) < total_words:
            self.words = words
        else:
            while len(self.words) < total_words:
                count = total_words - len(self.words)
                self.words |= set(random.choice(words) for _ in range(count))
        game_end = functools.partial(self.end_game, client, room)
        #self.debug(self.words)
        seconds = self.hours_per_round * 3600
        self.debug("Round ends in %s seconds", seconds)
        self.end_callback = self.loop.call_later(seconds, game_end)

    def end_game(self, client, room):
        """
        Runs the end-game logic. If the bot is not present, the end of the game is deferred by one second.
        """
        self.debug("Round over")
        self.cancel_endgame()
        if self.present:
            score_key = operator.itemgetter(1)
            score_groups = itertools.groupby(sorted(self.scoreboard.items(), key=score_key, reverse=True), key=score_key)
            client.send_message(room, 'Game over. Here were the scores:')
            for place, (points, group) in enumerate(score_groups, 1):
                if points > 0:
                    for name, _ in group:
                        client.send_message(room, "{}. {}. {}".format(place, self.actual_name(name), points))
            self.update_leaderboard()
            self.new_game(client, room)
        else:
            # For some reason, we were kicked from the room. Reschedule the score report.
            self.info("Wordbot was not present when the round ended; deferring score report for 1 second")
            game_end = functools.partial(self.end_game, client, room)
            self.end_callback = self.loop.call_later(1, game_end)

    def update_leaderboard(self):
        db = sqlite3.connect(self.leaderboard_database)
        cur = db.cursor()
        for user in self.scoreboard:
            score = self.scoreboard[user]
            cur.execute("SELECT score FROM users WHERE user=?", (user,))
            row = cur.fetchone()
            if not row:
                cur.execute("INSERT INTO users (user, score) VALUES (?, 0)", (user,))
                old_score = 0
            else:
                old_score = row[0]
            cur.execute("UPDATE users SET score=? WHERE user=?", (old_score + score, user))
        cur.close()
        db.commit()

    def cancel_endgame(self):
        self.debug("Cancelling endgame")
        self.end_callback.cancel()

    def ensure_database(self):
        db = sqlite3.connect(self.leaderboard_database)
        cur = db.cursor()
        cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
        id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
        user VARCHAR(40) NOT NULL,
        score INTEGER DEFAULT 0)""")
        cur.close()
        db.commit()

    @staticmethod
    def author(): return 'intercal'

    @staticmethod
    def about(): return 'Every few hours, a group of random words is chosen. If you say one of these words, you get one point!'

    @staticmethod
    def name(): return 'Wordbot'


# TODO:
# * multi-room wordbot; shares its state across the server and not across the channel
