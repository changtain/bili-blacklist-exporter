/* Bilibili blacklist importer - browser console edition.
 *
 * Migrates a UID list INTO the currently logged-in account's blacklist.
 * WRITE OPERATION: review the summary, then set DO_IMPORT = true below.
 *
 * How to use:
 *   1. Log in as the DESTINATION account.
 *   2. Open https://account.bilibili.com/account/blacklist
 *   3. F12 -> Console. If prompted, type `allow pasting` first.
 *   4. Paste the UID list into the UID_LIST array below (or paste a CSV/TXT).
 *   5. Set DO_IMPORT = true only when ready, then paste this whole file and Enter.
 */

(async () => {
  // ------------------------------------------------------------------
  // EDIT HERE: paste UIDs, one per line, e.g. `12345\n67890`
  const UID_TEXT = ``;
  const DO_IMPORT = false;   // must flip to true to actually block users
  const DELAY_MS = 1500;     // conservative pause between writes
  // ------------------------------------------------------------------

  const MODIFY = 'https://api.bilibili.com/x/relation/modify';
  const BLACKS = 'https://api.bilibili.com/x/relation/blacks';
  const NAV = 'https://api.bilibili.com/x/web-interface/nav';

  const readCookie = name => {
    const parts = ('; ' + document.cookie).split('; ' + name + '=');
    return parts.length === 2 ? parts.pop().split(';').shift() : null;
  };
  const csrf = readCookie('bili_jct');

  const uids = [...new Set(
    UID_TEXT.split(/[\s,;"']+/)
      .map(s => s.trim())
      .filter(s => /^\d+$/.test(s))
  )];

  if (!csrf) {
    console.error('[import] bili_jct not found - are you logged in?');
    return;
  }
  if (!uids.length) {
    console.error('[import] no UIDs found. Fill in UID_TEXT first.');
    return;
  }

  const nav = await (await fetch(NAV, { credentials: 'include' })).json();
  if (nav.code !== 0 || !nav.data || !nav.data.isLogin) {
    console.error('[import] not logged in');
    return;
  }
  const selfUid = String(nav.data.mid);

  // Load the destination account's current blacklist to avoid duplicates.
  const existing = new Set();
  for (let pn = 1; pn <= 200; pn++) {
    const r = await (await fetch(`${BLACKS}?re_src=32&pn=${pn}&ps=50`,
      { credentials: 'include' })).json();
    if (r.code !== 0) { console.error('[import] cannot read blacklist', r); return; }
    (r.data.list || []).forEach(u => existing.add(String(u.mid)));
    if (!(r.data.list || []).length || existing.size >= (r.data.total || 0)) break;
  }

  const todo = uids.filter(uid => uid !== selfUid && !existing.has(uid));
  console.log(`[import] target account: ${nav.data.uname} (${selfUid})`);
  console.log(`[import] parsed ${uids.length} UIDs, ${todo.length} need blocking`);
  console.log(`[import] mode: ${DO_IMPORT ? 'APPLY - WILL WRITE' : 'DRY-RUN - no changes'}`);

  if (!DO_IMPORT || !todo.length) {
    console.log('[import] nothing written. Set DO_IMPORT = true and paste again to apply.');
    return;
  }

  let ok = 0, failed = 0;
  for (let i = 0; i < todo.length; i++) {
    const uid = todo[i];
    try {
      const body = new URLSearchParams({
        fid: uid, act: '5', re_src: '11', csrf
      });
      const res = await fetch(MODIFY, {
        method: 'POST',
        credentials: 'include',
        headers: {
          'Content-Type': 'application/x-www-form-urlencoded',
          'Referer': 'https://www.bilibili.com/'
        },
        body
      });
      const data = await res.json();
      if (data.code === 0) {
        ok++;
        console.log(`[import] ${i + 1}/${todo.length} uid=${uid} ok`);
      } else {
        failed++;
        console.error(`[import] ${i + 1}/${todo.length} uid=${uid} code=${data.code} ${data.message || ''}`);
        // Stop on risk control / CSRF failure; continuing would waste the batch.
        if ([-101, -403, -352, 412].includes(data.code)) {
          console.error('[import] fatal code, stopping. Retry later with a larger DELAY_MS.');
          break;
        }
      }
    } catch (err) {
      failed++;
      console.error(`[import] ${i + 1}/${todo.length} uid=${uid} error`, err);
    }
    if (i < todo.length - 1 && DELAY_MS) {
      await new Promise(r => setTimeout(r, DELAY_MS));
    }
  }
  console.log(`[import] done: ok=${ok} failed=${failed}`);
})();
