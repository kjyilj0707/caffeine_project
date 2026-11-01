-- 카페인 측정기 Step 4-1: 표 8개 + "내 데이터는 나만" 규칙(RLS)
-- 설계: 노션 「Step 4 계획」 3번. 시간은 모두 timestamptz(한국 시간으로 보여주기는 화면에서).
-- 모든 표에 user_id가 있고, 로그인한 사용자는 자기 행만 읽고 쓸 수 있다.
-- 알림 발송(Edge Function)은 service_role로 실행되어 RLS를 거치지 않는다.

-- ── 1. 기본 정보 (한 사람당 1행) ─────────────────────────
create table public.profiles (
  user_id             uuid primary key references auth.users (id) on delete cascade,
  birth_year          smallint check (birth_year between 1900 and 2100),   -- 생년월일 대신 출생연도만 (최소 수집)
  weight_kg           numeric(5,1) check (weight_kg between 20 and 300),
  sex                 text check (sex in ('male', 'female')),
  smoker              boolean not null default false,
  oral_contraceptive  boolean not null default false,
  pregnancy_trimester smallint check (pregnancy_trimester between 1 and 3),
  breastfeeding       boolean not null default false,
  liver_disease       boolean not null default false,
  cyp1a2_inhibitor    boolean not null default false,
  heart_or_anxiety    boolean not null default false,
  sensitivity         text not null default 'normal' check (sensitivity in ('sensitive', 'normal', 'tolerant')),
  chronotype          text not null default 'neutral' check (chronotype in ('morning', 'neutral', 'evening')),
  daily_cap_mg        numeric(6,1) check (daily_cap_mg > 0),
  sip_ml              numeric(4,1) not null default 17.5 check (sip_ml between 5 and 50),
  created_at          timestamptz not null default now(),
  updated_at          timestamptz not null default now()
);

-- ── 2. 수면 기록 ─────────────────────────────────────
create table public.sleep_logs (
  id                bigint generated always as identity primary key,
  user_id           uuid not null default auth.uid() references auth.users (id) on delete cascade,
  slept_at          timestamptz not null,
  woke_at           timestamptz not null,
  quality           smallint check (quality between 1 and 5),
  sleep_latency_min smallint check (sleep_latency_min between 0 and 600),  -- 잠드는 데 걸린 시간 (피드백)
  created_at        timestamptz not null default now(),
  check (woke_at > slept_at and woke_at - slept_at < interval '24 hours'),
  unique (user_id, woke_at)
);

-- ── 3. 엔진이 만든 플랜 (예측을 남겨야 나중에 실제와 비교 가능) ──
create table public.plans (
  id             bigint generated always as identity primary key,
  user_id        uuid not null default auth.uid() references auth.users (id) on delete cascade,
  plan_date      date not null,
  engine_version text not null,          -- 코드 커밋 등
  params_hash    text,                   -- parameters.yaml 버전
  inputs         jsonb not null,         -- 그날 입력 전체 (시나리오 형식)
  result         jsonb not null,         -- 추천 잔·컷오프·지표
  created_at     timestamptz not null default now()
);

-- ── 4. 마신 기록 ─────────────────────────────────────
create table public.intakes (
  id             bigint generated always as identity primary key,
  user_id        uuid not null default auth.uid() references auth.users (id) on delete cascade,
  taken_at       timestamptz not null,
  beverage_key   text,                   -- 음료 DB(beverages.yaml) 항목, 직접 입력이면 null
  beverage_label text,
  mg             numeric(6,1) not null check (mg between 0 and 2000),
  ml             numeric(6,1) check (ml > 0),
  sips           numeric(5,1) check (sips > 0),
  plan_id        bigint references public.plans (id) on delete set null,  -- 플랜대로 마신 잔이면 연결
  created_at     timestamptz not null default now()
);

-- ── 5. 피드백 (정답 데이터) ─────────────────────────────
create table public.feedback (
  id          bigint generated always as identity primary key,
  user_id     uuid not null default auth.uid() references auth.users (id) on delete cascade,
  at          timestamptz not null default now(),
  kind        text not null check (kind in ('sleepiness', 'note')),
  kss         smallint check (kss between 1 and 9),     -- 카롤린스카 졸림 척도 1~9
  note        text check (char_length(note) <= 1000),
  plan_id     bigint references public.plans (id) on delete set null,
  created_at  timestamptz not null default now(),
  check (kind <> 'sleepiness' or kss is not null)
);

-- ── 6. 예약 알림 ─────────────────────────────────────
create table public.notifications (
  id         bigint generated always as identity primary key,
  user_id    uuid not null default auth.uid() references auth.users (id) on delete cascade,
  plan_id    bigint references public.plans (id) on delete cascade,
  send_at    timestamptz not null,
  kind       text not null check (kind in ('drink', 'stop', 'test', 'feedback')),
  title      text not null check (char_length(title) <= 200),
  body       text not null default '' check (char_length(body) <= 500),
  status     text not null default 'pending' check (status in ('pending', 'sent', 'failed', 'cancelled')),
  sent_at    timestamptz,
  error      text,
  created_at timestamptz not null default now()
);

-- ── 7. 알림 받을 기기 (웹 푸시 구독) ─────────────────────
create table public.push_subscriptions (
  id         bigint generated always as identity primary key,
  user_id    uuid not null default auth.uid() references auth.users (id) on delete cascade,
  endpoint   text not null unique,
  p256dh     text not null,
  auth       text not null,
  user_agent text,
  created_at timestamptz not null default now()
);

-- ── 8. 동의 기록 (쌓기만 하고 고치지 않음) ─────────────────
create table public.consents (
  id         bigint generated always as identity primary key,
  user_id    uuid not null default auth.uid() references auth.users (id) on delete cascade,
  kind       text not null check (kind in ('service', 'sensitive', 'research')),
  version    text not null,
  agreed     boolean not null,
  at         timestamptz not null default now()
);

-- ── 색인 ────────────────────────────────────────────
create index on public.sleep_logs (user_id, woke_at desc);
create index on public.intakes (user_id, taken_at desc);
create index on public.plans (user_id, plan_date desc);
create index on public.feedback (user_id, at desc);
create index on public.notifications (user_id, send_at);
create index notifications_due on public.notifications (send_at) where status = 'pending';
create index on public.push_subscriptions (user_id);
create index on public.consents (user_id, kind, at desc);
create index on public.intakes (plan_id);
create index on public.feedback (plan_id);
create index on public.notifications (plan_id);

-- ── updated_at 자동 갱신 ─────────────────────────────
create function public.touch_updated_at() returns trigger
language plpgsql set search_path = '' as $$
begin
  new.updated_at := now();
  return new;
end $$;
create trigger profiles_touch before update on public.profiles
  for each row execute function public.touch_updated_at();

-- ── RLS: 로그인한 사용자는 자기 행만 ────────────────────────
alter table public.profiles           enable row level security;
alter table public.sleep_logs         enable row level security;
alter table public.plans              enable row level security;
alter table public.intakes            enable row level security;
alter table public.feedback           enable row level security;
alter table public.notifications      enable row level security;
alter table public.push_subscriptions enable row level security;
alter table public.consents           enable row level security;

-- 읽기·쓰기·고치기·지우기 모두 "내 것만" (auth.uid()는 행마다 다시 계산하지 않도록 select로 감쌈)
do $$
declare t text;
begin
  foreach t in array array['profiles', 'sleep_logs', 'plans', 'intakes', 'feedback', 'notifications',
                           'push_subscriptions'] loop
    execute format('create policy "own rows: select" on public.%I for select to authenticated using (user_id = (select auth.uid()))', t);
    execute format('create policy "own rows: insert" on public.%I for insert to authenticated with check (user_id = (select auth.uid()))', t);
    execute format('create policy "own rows: update" on public.%I for update to authenticated using (user_id = (select auth.uid())) with check (user_id = (select auth.uid()))', t);
    execute format('create policy "own rows: delete" on public.%I for delete to authenticated using (user_id = (select auth.uid()))', t);
  end loop;
end $$;

-- 동의는 기록용: 읽기와 추가만 (철회는 agreed=false 행을 새로 추가)
create policy "own rows: select" on public.consents for select to authenticated using (user_id = (select auth.uid()));
create policy "own rows: insert" on public.consents for insert to authenticated with check (user_id = (select auth.uid()));
