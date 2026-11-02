// 카페인 측정기 Step 4-5: 보낼 시각이 된 알림을 사용자 기기로 웹 푸시
// pg_cron이 1분마다 부른다 (supabase/migrations/0002_push.sql). 여러 번 불려도 같은 알림은 한 번만 보낸다.
import "jsr:@supabase/functions-js/edge-runtime.d.ts";
import webpush from "npm:web-push@3.6.7";
import { createClient } from "npm:@supabase/supabase-js@2.118.0";

const SITE = "https://kjyilj0707.github.io/caffeine_project/";
// 공개 키는 index.html에도 있는 값 (누가 봐도 됨). 비밀 키는 Edge Function 비밀값 VAPID_PRIVATE_KEY에만.
const VAPID_PUBLIC_KEY = "BBc1naBjXI25fPC_0StoymAffFsflFIx8ltaYZnCsgzlH2va1FBHgBt6r39OcbAwV41QkHOAK3dlfKqdeZrAsYk";

const secretKeys = Deno.env.get("SUPABASE_SECRET_KEYS");
const serverKey = secretKeys ? JSON.parse(secretKeys).default : Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!;
const db = createClient(Deno.env.get("SUPABASE_URL")!, serverKey, { auth: { persistSession: false } });
webpush.setVapidDetails(SITE, VAPID_PUBLIC_KEY, Deno.env.get("VAPID_PRIVATE_KEY")!);

const json = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });

Deno.serve(async () => {
  const { data: due, error } = await db.rpc("claim_due_notifications", { max_rows: 100 });
  if (error) return json({ error: error.message }, 500);

  let sent = 0, failed = 0;
  for (const n of due ?? []) {
    const { data: subs } = await db.from("push_subscriptions")
      .select("id, endpoint, p256dh, auth").eq("user_id", n.user_id);
    if (!subs?.length) {
      await db.from("notifications").update({ status: "failed", error: "알림 받을 기기가 없음" }).eq("id", n.id);
      failed++;
      continue;
    }
    const payload = JSON.stringify({ title: n.title, body: n.body, kind: n.kind, url: SITE, tag: `n${n.id}` });
    let ok = 0;
    const errors: string[] = [];
    for (const s of subs) {
      try {
        // TTL 1시간: 핸드폰이 꺼져 있다가 1시간 안에 켜지면 받음 (그 뒤엔 늦은 알림이라 버림)
        await webpush.sendNotification({ endpoint: s.endpoint, keys: { p256dh: s.p256dh, auth: s.auth } },
          payload, { TTL: 3600, urgency: "high" });
        ok++;
      } catch (e) {
        const err = e as { statusCode?: number; body?: string; message?: string };
        errors.push(`${err.statusCode ?? ""} ${err.body ?? err.message ?? e}`.slice(0, 200));
        // 404·410 = 구독이 끝난 기기 (앱 삭제·알림 끔) → 지워서 다음부터 안 보냄
        if (err.statusCode === 404 || err.statusCode === 410) {
          await db.from("push_subscriptions").delete().eq("id", s.id);
        }
      }
    }
    await db.from("notifications").update(ok
      ? { status: "sent", sent_at: new Date().toISOString(), error: errors.join(" | ") || null }
      : { status: "failed", error: errors.join(" | ") }).eq("id", n.id);
    if (ok) sent++; else failed++;
  }
  return json({ claimed: due?.length ?? 0, sent, failed });
});
