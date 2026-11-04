-- 카페인 측정기: 앱 의견 보내기 (설정 → 의견 보내기)
-- 로그인 안 한 사람도 보낼 수 있다 (anon 쓰기 허용). 읽기 규칙은 없으므로 앱에서는 아무도 읽을 수 없고,
-- 개발자만 대시보드(서버 키)로 본다. 로그인한 사람이 보내면 user_id가 자동으로 들어간다.
create table public.app_feedback (
  id          bigint generated always as identity primary key,
  created_at  timestamptz not null default now(),
  user_id     uuid default auth.uid() references auth.users (id) on delete set null,
  category    text not null check (category in ('불편', '버그', '기능 요청', '기타')),
  message     text not null check (char_length(btrim(message)) between 1 and 2000),
  contact     text check (char_length(contact) <= 200),          -- 답을 받고 싶으면 (선택)
  page        text check (char_length(page) <= 100),             -- 어느 화면에서 보냈나
  user_agent  text check (char_length(user_agent) <= 500)
);

alter table public.app_feedback enable row level security;

-- 쓰기만: 로그인 안 했으면 user_id 없이, 로그인했으면 자기 user_id로만
create policy "anyone can send feedback" on public.app_feedback
  for insert to anon, authenticated
  with check (user_id is null or user_id = auth.uid());

revoke all on public.app_feedback from anon, authenticated;
grant insert on public.app_feedback to anon, authenticated;

create index on public.app_feedback (created_at desc);
