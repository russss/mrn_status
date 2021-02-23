import requests
from datetime import timedelta, datetime
from polybot import Bot
from time import sleep

from mrn import UplinkWindow, Downlink

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
        tweet += f"Expected data: {window.request_volume_returned:.0f} MB in "
        tweet += (
            str(round((window.pass_end - window.pass_start).total_seconds() / 60))
            + " minutes\n"
        )
        tweet += f"Configured bitrate: {window.request_forward_rate}/{window.request_return_rate} kbps"
        if window.request_adr:
            tweet += " (adaptive)"
        self.post(tweet)

    def tweet_downlink(self, downlink):
        tweet = orbiter_names.get(downlink.orbiter, downlink.orbiter)
        tweet += " downlinking "
        tweet += str(round(downlink.bits / 8 / 1024 / 1024)) + " MB"
        tweet += " from " + lander_names.get(downlink.lander, downlink.lander)
        tweet += " to Earth"
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
        res = requests.get(
            "https://mars.nasa.gov/rss/api/?feed=marsrelay&category=all&feedtype=json"
        )

        if res.status_code == 200:
            self.data = res.json()
        else:
            self.log.warn("Error %s reading marsrelay data feed", res.status_code)

        res = requests.get(
            "https://mars.nasa.gov/rss/api/?feed=marsrelay_db&category=all&feedtype=json"
        )

        if res.status_code == 200:
            self.downlink_data = res.json()
        else:
            self.log.warn("Error %s reading marsrelay_db data feed", res.status_code)

    def poll(self):
        if not self.last_update or self.last_update < datetime.now() - timedelta(
            minutes=10
        ):
            self.update_data()
            self.last_update = datetime.now()

        for window_data in self.data["marsRelay"]:
            window = UplinkWindow.from_json(window_data)
            if (
                window.link_type != ""
                and window.hail_end > datetime.now()
                and window.hail_start < datetime.now()
                and self.should_tweet_window(window)
            ):
                self.tweet_window(window)
                self.mark_tweeted_window(window)

        for downlink_data in self.downlink_data["DownlinkBuffer"]:
            downlink = Downlink.from_json(downlink_data)
            if (
                downlink.end_time > datetime.now()
                and downlink.start_time < datetime.now()
                and self.should_tweet_downlink(downlink)
            ):
                self.tweet_downlink(downlink)
                self.mark_tweeted_downlink(downlink)


TweetMRN().run()
