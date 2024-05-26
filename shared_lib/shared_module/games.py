from datetime import datetime


class Game:
    def __init__(
        self, year, season, start_datetime, duration, location, home_team, away_team
    ):
        self.year = year
        self.season = season
        self.start_datetime = start_datetime
        self.duration = duration
        self.location = location
        self.home_team = home_team
        self.away_team = away_team

    def to_dict(self):
        # 將 start_datetime 轉換為 ISO 8601 格式的字符串
        start_datetime_str = (
            self.start_datetime.isoformat() if self.start_datetime else None
        )

        return {
            "year": self.year,
            "season": self.season,
            "start_datetime": start_datetime_str,
            "duration": self.duration,
            "location": self.location,
            "home_team": self.home_team,
            "away_team": self.away_team,
        }

    @classmethod
    def from_dict(cls, data_dict):
        iso_datetime_str = data_dict.get("start_datetime")

        # 将 ISO 8601 格式的日期时间字符串转换为 datetime 对象
        start_datetime = (
            datetime.fromisoformat(iso_datetime_str) if iso_datetime_str else None
        )

        data_dict["start_datetime"] = start_datetime
        # 返回 MyData 类的实例
        return cls(**data_dict)
