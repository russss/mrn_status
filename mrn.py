import requests
from datetime import datetime, timedelta, date
from dataclasses import dataclass


def convert_date(datetimestr):
    if datetimestr == "" or datetimestr == "NULL":
        return None
    datestr, timestr = datetimestr.split("T")
    year, daynum = datestr.split("-")
    timestr, millis = timestr.split(".")
    hours, mins, secs = map(int, timestr.split(":"))
    return (
        datetime.combine(date(int(year), 1, 1), datetime.min.time())
        + timedelta(int(daynum) - 1)
        + timedelta(hours=hours, minutes=mins, seconds=secs, milliseconds=int(millis))
    )


def parse(val, typ):
    if val == "" or val == "NULL":
        return None
    return typ(val)


class FetchException(Exception):
    pass


@dataclass
class UplinkWindow:
    id: str
    orbiter: str
    lander: str

    pass_start: datetime
    pass_end: datetime

    hail_start: datetime
    hail_end: datetime

    link_type: str

    request_forward_rate: int  # bits
    request_return_rate: int  # bits
    request_volume_returned: float  # bits
    request_adr: bool

    @classmethod
    def from_json(cls, data):
        return cls(
            id=data["OVERFLIGHTID"],
            orbiter=data["SPACECRAFTORBITER"],
            lander=data["SPACECRAFTLANDER"],
            pass_start=convert_date(data["STARTTIME"]),
            pass_end=convert_date(data["ENDTIME"]),
            hail_start=convert_date(data["HAILSTART"]),
            hail_end=convert_date(data["HAILEND"]),
            link_type=data["LINKTYPE"],
            request_forward_rate=parse(data["REQUESTFORWARDLINKDATARATE"], int),
            request_return_rate=parse(data["REQUESTRETURNLINKDATARATE"], int),
            request_volume_returned=parse(data["REQUESTDATAVOLUMERETURNED"], float),
            request_adr=data["REQUESTADR_ENABLE_FLAG"] not in ("ADR_OFF", ""),
        )

    @classmethod
    def fetch(cls):
        res = requests.get(
            "https://mars.nasa.gov/rss/api/?feed=marsrelay&category=all&feedtype=json"
        )
        if res.status_code != 200:
            raise FetchException(res.status_code)

        data = res.json()
        return [cls.from_json(row) for row in data["marsRelay"]]


@dataclass
class Downlink:
    id: str
    overflight_id: str
    orbiter: str
    lander: str

    start_time: datetime
    end_time: datetime

    bits: int

    @classmethod
    def from_json(cls, data):
        return cls(
            id=data["OVERFLIGHTID"] + data["STARTTIME"],
            overflight_id=data["OVERFLIGHTID"],
            orbiter=data["SPACECRAFTORBITER"],
            lander=data["SPACECRAFTLANDER"],
            start_time=convert_date(data["STARTTIME"]),
            end_time=convert_date(data["ENDTIME"]),
            bits=parse(data["BITS"], int),
        )

    @classmethod
    def fetch(cls):
        res = requests.get(
            "https://mars.nasa.gov/rss/api/?feed=marsrelay_db&category=all&feedtype=json"
        )
        if res.status_code != 200:
            raise FetchException(res.status_code)

        data = res.json()
        return [cls.from_json(row) for row in data["DownlinkBuffer"]]


@dataclass
class OrbiterEvent:
    orbiter: str
    type: str
    start_time: datetime
    end_time: datetime
    receiver: str
    data_rate: int  # bits/s

    @classmethod
    def from_json(cls, data):
        return cls(
            orbiter=data["SPACECRAFTORBITER"],
            type=data["EVENTTYPE"],
            start_time=convert_date(data["STARTTIME"]),
            end_time=convert_date(data["ENDTIME"]),
            receiver=parse(data["DSS"], str),
            data_rate=parse(data["DATARATE"], float),
        )

    @classmethod
    def fetch(cls):
        res = requests.get(
            "https://mars.nasa.gov/rss/api/?feed=marsrelay_oe&category=all&feedtype=json"
        )
        if res.status_code != 200:
            raise FetchException(res.status_code)

        data = res.json()
        return [cls.from_json(row) for row in data["orbiterEvent"]]
