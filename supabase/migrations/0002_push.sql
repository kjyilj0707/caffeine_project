-- 카페인 측정기 Step 4-5: 웹 푸시 알림
-- 흐름: 화면에서 알림 예약(notifications에 행 추가) → pg_cron이 1분마다 Edge Function send-push 호출
--       → 함수가 보낼 시각이 된 알림을 '가져가기'(claim)해서 사용자 기기(push_subscriptions)로 보냄

-- ── 1. '보내는 중' 상태 추가 (두 번 보내지 않게) ─────────────────
alter table public.notifications drop constraint notifications_status_check;
alter table public.notifications add constraint notifications_status_check
  check (status in ('pending', 'sending', 'sent', 'failed', 'cancelled'));

-- ── 2. 보낼 알림 가져가기 (Edge Function만 호출, 서버 키로) ───────────
-- 동시에 여러 번 불려도 같은 알림을 두 번 가져가지 않도록 skip locked.
-- '보내는 중'으로 10분 넘게 멈춘 것(함수가 중간에 죽은 경우)은 다시 가져간다.
create function public.claim_due_notifications(max_rows int default 100)
returns setof public.notifications
language sql
security invoker
set search_path = ''
as $$
  update public.notifications n
     set status = 'sending', sent_at = now()
   where n.id in (
     select id from public.notifications
      where (status = 'pending' and send_at <= now())
         or (status = 'sending' and sent_at < now() - interval '10 minutes')
      order by send_at
      limit max_rows
      for update skip locked)
  returning n.*;
$$;
revoke execute on function public.claim_due_notifications(int) from public, anon, authenticated;

-- ── 3. 1분마다 Edge Function 호출 ────────────────────────────
create extension if not exists pg_cron;
create extension if not exists pg_net;

-- 호출 주소·공개 키는 Vault에 (cron 작업 내용에 직접 쓰지 않음)
select vault.create_secret('https://arqruewigqgzbmlsgjad.supabase.co/functions/v1/send-push', 'send_push_url');
-- 함수 호출용 키 = 공개(anon) 키. 누가 불러도 '보낼 시각이 된 알림'만 보내므로 해가 없고, 아무나 못 부르게 JWT 검사만 둔다
select vault.create_secret('eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImFycXJ1ZXdpZ3FnemJtbHNnamFkIiwicm9sZSI6ImFub24iLCJpYXQiOjE3OTM1MjcwOTEsImV4cCI6MjEwOTEwMzA5MX0.d-P_oKeYdumxKT-IKpZaI4stoPIzrPOAKRYDhnFW7U4', 'send_push_key');

create function public.invoke_send_push()
returns void
language plpgsql
security definer
set search_path = ''
as $$
declare
  url text := (select decrypted_secret from vault.decrypted_secrets where name = 'send_push_url');
  key text := (select decrypted_secret from vault.decrypted_secrets where name = 'send_push_key');
begin
  -- 보낼 알림이 없으면 함수를 깨우지 않는다 (무료 플랜 호출 수 절약)
  if not exists (select 1 from public.notifications
                  where (status = 'pending' and send_at <= now())
                     or (status = 'sending' and sent_at < now() - interval '10 minutes')) then
    return;
  end if;
  perform net.http_post(url := url,
                        headers := jsonb_build_object('Content-Type', 'application/json',
                                                      'Authorization', 'Bearer ' || key),
                        body := '{}'::jsonb,
                        timeout_milliseconds := 30000);
end $$;
revoke execute on function public.invoke_send_push() from public, anon, authenticated;

select cron.schedule('send-push-every-minute', '* * * * *', 'select public.invoke_send_push()');
