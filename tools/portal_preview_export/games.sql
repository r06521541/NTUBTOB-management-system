BEGIN TRANSACTION READ ONLY;
SET LOCAL statement_timeout = '30s';
SELECT jsonb_build_object(
  'id', id, 'year', year, 'season', season, 'start_datetime', start_datetime,
  'duration', duration, 'location', location, 'home_team', home_team,
  'away_team', away_team, 'invitation_time', invitation_time,
  'cancellation_time', cancellation_time,
  'cancellation_announcement_time', cancellation_announcement_time
)::text
FROM ntubtob.games
ORDER BY id;
COMMIT;
