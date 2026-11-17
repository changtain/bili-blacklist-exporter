/* Bilibili blacklist exporter - browser console edition.
 *
 * How to use:
 *   1. Open https://account.bilibili.com/account/blacklist while logged in.
 *   2. Press F12 -> Console. If Chrome warns about pasting, type
 *      `allow pasting` and press Enter first.
 *   3. Paste this whole file and press Enter.
 *   4. A CSV named bilibili_blacklist.csv is downloaded.
 *
 * No Cookie is read, printed, or transmitted. The browser attaches your
 * session automatically because the request is same-origin.
 */

(async () => {
  const API = 'https://api.bilibili.com/x/relation/blacks';
  // The server caps ps at 50 regardless of the requested value.
  const PAGE_SIZE = 50;
  // Hard stop so a malformed response cannot cause an infinite loop.
  const MAX_PAGES = 200;
  // A short pause between pages reduces the chance of hitting risk control.
  const DELAY_MS = 200;

  const rows = new Map();
  let total = null;

  for (let pn = 1; pn <= MAX_PAGES; pn++) {
    let payload;
    try {
      const res = await fetch(`${API}?re_src=32&pn=${pn}&ps=${PAGE_SIZE}`, {
        credentials: 'include'
      });
      payload = await res.json();
    } catch (err) {
      console.error('[blacklist] request failed on page', pn, err);
      break;
    }

    if (payload.code !== 0) {
      console.error('[blacklist] API error on page', pn, payload.code, payload.message);
      break;
    }
    if (total === null) total = payload.data && payload.data.total;

    const list = (payload.data && payload.data.list) || [];
    for (const user of list) rows.set(String(user.mid), user);
    console.log(`[blacklist] page ${pn}: +${list.length}, collected ${rows.size}/${total ?? '?'}`);

    if (!list.length || (total && rows.size >= total)) break;
    await new Promise(resolve => setTimeout(resolve, DELAY_MS));
  }

  if (!rows.size) {
    console.error('[blacklist] nothing exported - are you logged in?');
    return;
  }

  // Quote only when needed, matching Python's csv.DictWriter behaviour.
  const field = value => {
    const s = String(value == null ? '' : value);
    return /[",\r\n]/.test(s) ? '"' + s.replace(/"/g, '""') + '"' : s;
  };
  const pad = n => String(n).padStart(2, '0');

  const sorted = [...rows.entries()].sort((a, b) =>
    BigInt(a[0]) < BigInt(b[0]) ? -1 : BigInt(a[0]) > BigInt(b[0]) ? 1 : 0
  );

  const lines = ['uid,uname,blocked_at,space_url,sign'];
  for (const [uid, user] of sorted) {
    const d = new Date((user.mtime || 0) * 1000);
    const ts = `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ` +
               `${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`;
    lines.push([
      uid,
      field(user.uname),
      field(ts),
      field('https://space.bilibili.com/' + uid),
      field((user.sign || '').replace(/[\r\n]+/g, ' '))
    ].join(','));
  }

  const blob = new Blob(['\ufeff' + lines.join('\r\n')], {
    type: 'text/csv;charset=utf-8'
  });
  const link = document.createElement('a');
  link.href = URL.createObjectURL(blob);
  link.download = 'bilibili_blacklist.csv';
  document.body.appendChild(link);
  link.click();
  link.remove();
  setTimeout(() => URL.revokeObjectURL(link.href), 1000);

  console.log(`[blacklist] done: ${rows.size} UIDs downloaded (API total: ${total ?? '?'})`);
})();
