import re
from datetime import timedelta, datetime
from polybot import Bot
from time import sleep

from mrn import UplinkWindow, Downlink, FetchException, OrbiterEvent

# Interesting data:
# https://mars.nasa.gov/rss/api/?feed=marsrelay&category=all&feedtype=json
# https://mars.nasa.gov/rss/api/?feed=marsrelay_db&category=all&feedtype=json
# https://mars.nasa.gov/rss/api/?feed=marsrelay_oe&category=all&feedtype=json
# https://mars.nasa.gov/rss/api/?feed=mission_lmst&category=all&feedtype=json


orbiter_names = {
    "ODY": "Odyssey",
    "MRO": "MRO",
    "MVN": "Maven",
    "TGO": "ExoMars TGO",
    "MEX": "Mars Express",
}

lander_names = {"M20": "Perseverance", "NSY": "InSight", "MSL": "Curiosity"}

receiver_names = {
    "MLG": "Malargüe (ESA)",
    "NNO": "New Norcia (ESA)",
    "CEB": "Cebreros (ESA)",
    "KLZ": "Kalyazin (Roscosmos)",
}


def format_receiver(receiver):
    if receiver.startswith("DSS-"):
        return receiver
    elif re.match(r"^[0-9]+$", receiver):
        return "DSS-" + receiver
    elif receiver in receiver_names:
        return receiver_names[receiver]
    else:
        return receiver


class TweetMRN(Bot):
    def __init__(self):
        super().__init__("tweet_mrn")
        self.state = {"seen_windows": {}, "seen_downlinks": {}}
        self.last_update = None

    def main(self):
        while True:
            self.poll()
            sleep(10)

    def tweet_window(self, window):
        tweet = "New session: " + lander_names.get(window.lander, window.lander)
        if window.link_type == "forward":
            tweet += " ← "
        elif window.link_type == "return":
            tweet += " → "
        else:
            tweet += " ⟷ "
        tweet += orbiter_names.get(window.orbiter, window.orbiter)
        tweet += "\n"

        size_mbytes = round(window.request_volume_returned / 8)
        tweet += f"Expected data: {size_mbytes:.0f} MB in "
        tweet += (
            str(round((window.pass_end - window.pass_start).total_seconds() / 60))
            + " minutes\n"
        )
        tweet += f"Configured data rate: {window.request_forward_rate}/{window.request_return_rate} kbps"
        if window.request_adr:
            tweet += " (adaptive)"
        self.post(tweet)

    def get_orbiter_events(self, orbiter, time):
        events = sorted(
            [
                e
                for e in self.orbiter_events
                if e.orbiter == orbiter
                and e.start_time <= time
                and (e.end_time is None or e.end_time > time)
            ],
            key=lambda e: e.start_time,
        )

        ret = [e for e in events if e.type != "DataRate"]
        # DataRate events don't have an end_time, so take the most recent one only
        dr = [e for e in events if e.type == "DataRate"]
        if len(dr) > 0:
            ret += [dr[-1]]
        return ret

    def tweet_downlink(self, downlink):
        if downlink.bits < 100000:
            return

        events = self.get_orbiter_events(downlink.orbiter, downlink.start_time)
        tweet = orbiter_names.get(downlink.orbiter, downlink.orbiter)
        tweet += " downlinking "
        tweet += str(round(downlink.bits / 8 / 1024 / 1024, 2)) + " MB"
        tweet += " from " + lander_names.get(downlink.lander, downlink.lander)
        tweet += " to Earth"

        tracks = [e for e in events if e.type == "DSNTrack"]
        if len(tracks) > 0:
            tweet += "\n"
            if len(tracks) == 1:
                tweet += "Ground station: "
            else:
                tweet += "Ground stations: "
            tweet += ", ".join(format_receiver(track.receiver) for track in tracks)

        drs = [e for e in events if e.type == "DataRate"]
        if len(drs) > 0:
            tweet += "\nData rate: "
            rate = drs[0].data_rate / 1024
            if rate > 1024:
                tweet += f"{round(rate / 1024, 1)} Mbps"
            else:
                tweet += f"{round(rate)} kbps"

        self.post(tweet)

    def should_tweet_window(self, window):
        to_delete = []
        seen = False
        for window_date, seen_window in self.state["seen_windows"].items():
            if window_date < datetime.now() - timedelta(days=7):
                to_delete.append(window_date)
            if seen_window == window.id:
                seen = True

        for window in to_delete:
            del self.state["seen_windows"][window]

        return not seen

    def mark_tweeted_window(self, window):
        self.state["seen_windows"][window.hail_start] = window.id
        self.save_state()

    def should_tweet_downlink(self, downlink):
        to_delete = []
        seen = False
        for downlink_date, seen_downlink in self.state["seen_downlinks"].items():
            if downlink_date < datetime.now() - timedelta(days=7):
                to_delete.append(downlink_date)
            if seen_downlink == downlink.id:
                seen = True

        for downlink in to_delete:
            del self.state["seen_downlinks"][downlink]

        return not seen

    def mark_tweeted_downlink(self, downlink):
        self.state["seen_downlinks"][downlink.start_time] = downlink.id
        self.save_state()

    def update_data(self):
        self.log.debug("Updating data")

        try:
            self.windows = UplinkWindow.fetch()
        except FetchException:
            self.log.warn("Error reading marsrelay data feed")

        try:
            self.downlinks = Downlink.fetch()
        except FetchException:
            self.log.warn("Error reading downlink data feed")

        try:
            self.orbiter_events = OrbiterEvent.fetch()
        except FetchException:
            self.log.warn("Error reading orbiter event data feed")

    def poll(self):
        if not self.last_update or self.last_update < datetime.now() - timedelta(
            minutes=10
        ):
            self.update_data()
            self.last_update = datetime.now()

        for window in self.windows:
            if (
                window.link_type != ""
                and window.hail_end > datetime.now()
                and window.hail_start < datetime.now()
                and self.should_tweet_window(window)
            ):
                self.tweet_window(window)
                self.mark_tweeted_window(window)

        for downlink in self.downlinks:
            if (
                downlink.end_time > datetime.now()
                and downlink.start_time < datetime.now()
                and self.should_tweet_downlink(downlink)
            ):
                self.tweet_downlink(downlink)
                self.mark_tweeted_downlink(downlink)


TweetMRN().run()
