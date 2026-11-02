-- RLS 확인: 가짜 사용자 A·B를 만들고 A로 로그인한 척, B 데이터에 손댈 수 있는지 본다.
-- 끝에서 일부러 오류를 내므로 모든 테스트 데이터는 되돌려진다(DB에 남지 않음).
-- 기대 결과(2026-11-01 통과): A profiles=1, intakes=1, B consents=0, B 수정=0, B 삭제=0,
--   B 이름으로 쓰기=차단, user_id 생략 후 A intakes=2, 동의 고치기=0 | 비로그인 0, 0
do $$
declare
  a uuid := '00000000-0000-0000-0000-0000000000a1';
  b uuid := '00000000-0000-0000-0000-0000000000b2';
  r text := '';
  n int;
begin
  insert into auth.users (id, email, aud, role) values
    (a, 'test-a@example.com', 'authenticated', 'authenticated'),
    (b, 'test-b@example.com', 'authenticated', 'authenticated');
  insert into public.profiles (user_id, weight_kg) values (a, 60), (b, 80);
  insert into public.intakes (user_id, taken_at, mg) values (a, now(), 75), (b, now(), 150), (b, now(), 150);
  insert into public.consents (user_id, kind, version, agreed) values (b, 'service', 'v1', true);

  perform set_config('role', 'authenticated', true);
  perform set_config('request.jwt.claims', json_build_object('sub', a, 'role', 'authenticated')::text, true);

  select count(*) into n from public.profiles;            r := r || 'A profiles=' || n;
  select count(*) into n from public.intakes;             r := r || ', intakes=' || n;
  select count(*) into n from public.consents;            r := r || ', B consents=' || n;
  update public.intakes set mg = 0 where user_id = b;     get diagnostics n = row_count; r := r || ', B 수정=' || n;
  delete from public.profiles where user_id = b;          get diagnostics n = row_count; r := r || ', B 삭제=' || n;
  begin
    insert into public.intakes (user_id, taken_at, mg) values (b, now(), 999);
    r := r || ', B 이름으로 쓰기=성공(문제!)';
  exception when insufficient_privilege then r := r || ', B 이름으로 쓰기=차단';
  end;
  insert into public.intakes (taken_at, mg) values (now(), 30);
  select count(*) into n from public.intakes;             r := r || ', user_id 생략 후 A intakes=' || n;
  insert into public.consents (kind, version, agreed) values ('service', 'v1', true);
  update public.consents set agreed = false;              get diagnostics n = row_count; r := r || ', 동의 고치기=' || n;

  execute 'reset role';
  perform set_config('role', 'anon', true);
  select count(*) into n from public.profiles;            r := r || ' | 비로그인 ' || n;
  select count(*) into n from public.intakes;             r := r || ', ' || n;

  execute 'reset role';
  raise exception 'RLS_TEST_RESULT: %', r;
end $$;
