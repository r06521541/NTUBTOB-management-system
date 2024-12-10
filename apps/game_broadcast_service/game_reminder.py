import requests
from datetime import datetime, timedelta, time

from shared_module.models.games import Game
from shared_module.models.ballparks import Ballpark
from shared_module.settings import (
    local_timezone
)
from shared_module.general_message import (
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

	api_key = 'CWA-D3587479-3CBA-44C5-83FC-A7E019F75363'
	api = f'https://opendata.cwa.gov.tw/api/v1/rest/datastore/F-D0047-{ballpark.city_weather_code}?Authorization={api_key}&elementName=Wx,AT,T,PoP6h&locationName={ballpark.district_name}'

	data = requests.get(api).json()['records']['locations'][0]['location'][0]
	#data = test_1.data['records']['locations'][0]['location'][0]

	# Define time range and points of interest
	begin_time, end_time = target_date + timedelta(hours=6), target_date + timedelta(hours=18)
	time_points = [target_date + timedelta(hours=hour) for hour in [6, 9, 12, 15, 18]]

	# Extract weather data
	weather_data = next(item for item in data['weatherElement'] if item['elementName'] == 'Wx')
	temperature_data = next(item for item in data['weatherElement'] if item['elementName'] == 'T')
	rainfall_data = next(item for item in data['weatherElement'] if item['elementName'] == 'PoP6h')

	# Helper function to filter data by time range
	def filter_by_time(data, element_value_index, time_key, start_time, end_time):
		return [
			(datetime.strptime(entry[time_key], "%Y-%m-%d %H:%M:%S"), entry['elementValue'][element_value_index]['value'])
			for entry in data['time']
			if (time_key == 'startTime' and start_time <= datetime.strptime(entry[time_key], "%Y-%m-%d %H:%M:%S") < end_time)
			or (time_key == 'dataTime' and start_time <= datetime.strptime(entry[time_key], "%Y-%m-%d %H:%M:%S") <= end_time)
		]

	# Filter data
	weathers = [weather_emoji_mapping.get(code, '❓') for _, code in filter_by_time(weather_data, 1, 'startTime', begin_time, end_time)]
	rainfalls = [int(value) for _, value in filter_by_time(rainfall_data, 0, 'startTime', begin_time, end_time)]
	temperatures = [int(value) for _, value in filter_by_time(temperature_data, 0, 'dataTime', begin_time, end_time)]

	# Create strings for output
	time_string = '時間 ' + '　'.join(clock_emoji_mapping[time.hour % 12] for time in time_points)
	weather_string = '天氣 　' + '　'.join(weathers)
	rainfall_string = f'降雨 　{rainfall_emoji_mapping[rainfalls[0]]}　➡️　{rainfall_emoji_mapping[rainfalls[1]]}'
	temperature_tens_digit_string = '氣溫 ' + '　'.join(number_emoji_mapping[temp // 10] for temp in temperatures)
	temperature_units_digit_string = '　　 ' + '　'.join(number_emoji_mapping[temp % 10] for temp in temperatures)

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
		+ f'\n{day_name}{ballpark.city_name[:-1] if len(ballpark.city_name) > 2 else ballpark.city_name}'
		f'{ballpark.district_name[:-1] if len(ballpark.district_name) > 2 else ballpark.district_name}的天氣預報：\n'
		
		+ f'\n{time_string}\n{weather_string}'
		+ f'\n———————————————'
		+ f'\n{rainfall_string}'
		+ f'\n———————————————'
		+ f'\n{temperature_tens_digit_string}'
		+ f'\n{temperature_units_digit_string}'
		
		+ ('\n\n若天候不佳，請密切關注比賽訊息！' if any(rainfall >= 50 for rainfall in rainfalls) else '')
	)

	return reminder



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