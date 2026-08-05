-- ==========================================================================
--  KEEP-ALIVE for the Supabase FREE tier — prevents the 7-day idle pause
--  during a long office closure (Eid / vacation) when the server PC is off.
--
--  In NORMAL use you don't need this: the nightly backup's pg_dump touches
--  the database every working day, which already keeps it awake. This is the
--  safety net for a 5+ day inactive stretch.
--
--  ONE-TIME SETUP:
--  1) Supabase Dashboard -> SQL Editor -> paste & run the two statements below.
--     (Creates a trivial function the public 'anon' key may call. It returns
--      only the word 'ok' — no data is exposed.)
--  2) cron-job.org (free signup) -> create a job:
--        URL     :  https://piqrfdwirbpbfcdibdmh.supabase.co/rest/v1/rpc/keepalive
--        Method  :  POST
--        Headers :  apikey: <your-anon-key>
--                   Authorization: Bearer <your-anon-key>
--                   Content-Type: application/json
--        Body    :  {}
--        Schedule:  every 3 days  (safe margin — even a missed ping stays
--                                  under the 7-day pause limit; 5 days works
--                                  too but leaves less room if a ping fails)
--  Each ping runs the function on the database = real activity = never pauses.
-- ==========================================================================

create or replace function public.keepalive()
    returns text
    language sql
as $$
    select 'ok'::text;
$$;

grant execute on function public.keepalive() to anon;
