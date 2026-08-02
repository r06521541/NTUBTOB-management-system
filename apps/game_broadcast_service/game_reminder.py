import requests
from datetime import datetime, timedelta, time

from shared_module.models.games import Game
from shared_module.models.ballparks import Ballpark
from shared_module.settings import (
    local_timezone
)
from shared_module.message_templates.general_message import (
    weekday_mapping
)
from emoji_mappings import (
    weather_emoji_mapping,
    rainfall_emoji_mapping,
    number_emoji_mapping,
    clock_emoji_mapping
)


def get_game_reminder_string(before_days: int) -> str:

	# Set up time and date variables
	now = datetime.now(local_timezone)
	target_date = (datetime.combine(now, time.min, tzinfo=local_timezone) + timedelta(days=before_days)).replace(tzinfo=None)

	# Search for games and ballpark information
	games = Game.search_games(target_date, target_date + timedelta(days=1), True)
	if not games:
		return None

	location = games[0].location
	ballpark = Ballpark.search_by_name(location)

	# Generate reminder
	first_game = games[0]
	formatted_date = first_game.start_datetime.astimezone(local_timezone).strftime("%-m/%-d（%a）").replace(first_game.start_datetime.strftime('%a'), weekday_mapping[first_game.start_datetime.strftime('%A')])
	gathering_time = first_game.start_datetime.astimezone(local_timezone) + timedelta(hours=-1)

	day_name = '明天'

	reminder = (
		f'提醒一下，{day_name} {formatted_date}有{len(games)}場比賽在{location}唷！\n'
		f'集合時間是{gathering_time.strftime("%-H:%M")}，別太晚到啊～～\n\n'
		+ ''.join(
			f'{"季後賽" if game.is_offseason() else "⚾"} {game.get_formatted_start_time()} - {game.get_formatted_end_time()} vs {game.get_opponent()} {"先守（三壘側）" if game.get_is_home_team() else "先攻（一壘側）"}\n'
			for game in games
		)		
		+ f'\n{get_weather_string(target_date, day_name, ballpark.city_name, ballpark.city_weather_code, ballpark.district_name)}'
	)

	return reminder


def get_weather_string(target_date: datetime, day_name: str, city_name: str, city_weather_code: str, district_name: str) -> str:

	api_key = 'CWA-D3587479-3CBA-44C5-83FC-A7E019F75363'
	api = f'https://opendata.cwa.gov.tw/api/v1/rest/datastore/F-D0047-{city_weather_code}?Authorization={api_key}&elementName=Wx,AT,T,PoP6h&LocationName={district_name}'
	datetime_format = "%Y-%m-%dT%H:%M:%S%z"

	data_json = requests.get(api).json()
	data = data_json['records']['Locations'][0]['Location'][0]

	target_date = datetime.combine(target_date, time.min, tzinfo=local_timezone)
	time_points = [target_date + timedelta(hours=hour) for hour in [6, 9, 12, 15, 18]]		

	# Define time range and points of interest
	begin_time, end_time = target_date + timedelta(hours=6), target_date + timedelta(hours=18)

	# Extract weather data
	weather_data = next(item for item in data['WeatherElement'] if item['ElementName'] == '天氣現象')
	temperature_data = next(item for item in data['WeatherElement'] if item['ElementName'] == '溫度')
	rainfall_data = next(item for item in data['WeatherElement'] if item['ElementName'] == '3小時降雨機率')

	# Helper function to filter data by time range
	def filter_by_start_time(data, element_name, start_time, end_time):
		return [
			(datetime.strptime(entry['StartTime'], datetime_format), entry['ElementValue'][0][element_name])
			for entry in data['Time']
			if (start_time <= datetime.strptime(entry['StartTime'], datetime_format) < end_time)
		]
	# Helper function to filter data by time range
	def filter_by_data_time(data, element_name, time_points):
		return [
			(datetime.strptime(entry['DataTime'], datetime_format), entry['ElementValue'][0][element_name])
			for entry in data['Time']
			if (datetime.strptime(entry['DataTime'], datetime_format) in time_points)
		]
	
	# Filter data
	temperatures = [int(value) for _, value in filter_by_data_time(temperature_data, 'Temperature', time_points)]
	weathers = [weather_emoji_mapping.get(code, '❓') for _, code in filter_by_start_time(weather_data, 'WeatherCode', begin_time, end_time)]
	rainfalls = [int(value) for _, value in filter_by_start_time(rainfall_data, 'ProbabilityOfPrecipitation', begin_time, end_time)]

	# Create strings for output
	time_string = '時間 ' + '　'.join(clock_emoji_mapping[time.hour % 12] for time in time_points)
	weather_string = '天氣 　' + '　'.join(weathers)
	#rainfall_string = f'降雨 　{rainfall_emoji_mapping[rainfalls[0]]}　➡️　{rainfall_emoji_mapping[rainfalls[1]]}'
	rainfall_tens_digit_string = '降雨 　' + '　'.join(number_emoji_mapping[temp // 10] for temp in rainfalls)
	rainfall_units_digit_string = '　　 　' + '　'.join(number_emoji_mapping[temp % 10] for temp in rainfalls)
	temperature_tens_digit_string = '氣溫 ' + '　'.join(number_emoji_mapping[temp // 10] for temp in temperatures)
	temperature_units_digit_string = '　　 ' + '　'.join(number_emoji_mapping[temp % 10] for temp in temperatures)


	weather_string = (
		f'\n{day_name}{city_name[:-1] if len(city_name) > 2 else city_name}'
		f'{district_name[:-1] if len(district_name) > 2 else district_name}的天氣預報：\n'
		
		+ f'\n{time_string}\n{weather_string}'
		+ f'\n———————————————'
		+ f'\n{rainfall_tens_digit_string}'
		+ f'\n{rainfall_units_digit_string}'
		+ f'\n———————————————'
		+ f'\n{temperature_tens_digit_string}'
		+ f'\n{temperature_units_digit_string}'
		
		+ ('\n\n若天候不佳，請密切關注比賽訊息！' if any(rainfall >= 50 for rainfall in rainfalls) else '')
	)
	return weather_string


'''
# Extract weather information
for time_data in data['weatherElement'][0]['time']:
    times.append(clock_emoji_mapping[int(time_data['startTime'][11:13])])
    weather_code = time_data['elementValue'][1]['value']
    weather.append(weather_emoji_mapping.get(weather_code, '❓'))

# Extract rainfall probability
for time_data in data['weatherElement'][2]['time']:
    rainfall_value = int(time_data['elementValue'][0]['value'])
    rainfall.append(''.join(number_emoji_mapping[int(d)] for d in str(rainfall_value)))

# Extract temperature
for time_data in data['weatherElement'][1]['time']:
    temp_value = time_data['elementValue'][0]['value']
    temperature.append(''.join(number_emoji_mapping[int(d)] for d in str(temp_value)))

# Display formatted output
print('時間　' + '　'.join(times))
print('天氣　' + '　'.join(weather))
print('降雨　' + '　　　'.join(rainfall))
print('氣溫　' + '　'.join(temperature))
'''