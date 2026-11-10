// Frameback: read a public Frame.io V4 share page (no login).
// Run in the page (browser devtools / javascript tool) after the comments panel has loaded.
// Returns {name, url, size, width, height, notes} where notes is the import-notes JSON format.
// Data comes from Frame.io's Apollo GraphQL cache (window.__APOLLO_CLIENT__), checked 2026-11-10.
(() => {
  const c = window.__APOLLO_CLIENT__?.cache?.extract();
  if (!c) return { error: "no Frame.io data on this page (is it a public /share/ link and fully loaded?)" };
  const get = r => (r && r.__ref ? c[r.__ref] : r);
  const viewId = (location.pathname.match(/\/view\/([0-9a-f-]{36})/) || [])[1];
  const asset = c["Asset:" + viewId] || Object.entries(c).find(([k]) => k.startsWith("Asset:"))?.[1];
  if (!asset) return { error: "no video found on this page" };
  const listKey = Object.keys(asset).find(k => k.startsWith("comments("));
  const top = (asset[listKey]?.result || []).map(get).filter(x => x && !x.parentId);
  const sec = us => (us == null ? null : us / 1e6);
  const name = x => get(x.owner)?.name || "Frame.io";
  const notes = top.map(x => {
    const n = { id: x.id, author: name(x), text: x.text || "", done: !!x.completed, created: x.insertedAt,
      replies: (x.replies || []).map(get).filter(Boolean).map(r => ({ author: name(r), text: r.text || "", created: r.insertedAt })) };
    if (x.timestampMicroseconds != null) n.seconds = sec(x.timestampMicroseconds);
    if (x.duration && n.seconds != null) n.end_seconds = n.seconds + sec(x.duration);  // unit assumed microseconds, unverified
    if (x.annotation) n.text += " (had a drawing in Frame.io)";
    if ((x.attachments || []).length) n.text += " (had an attachment in Frame.io)";
    return n;
  });
  const vm = Object.entries(c).find(([k]) => k.startsWith("VideoMetadata"))?.[1] || {};
  const o = asset.media?.original || {};
  return { name: asset.name, url: o.downloadUrl, size: o.filesizeInBytes, width: vm.originalWidth, height: vm.originalHeight,
           notes: { source: "frameio", notes } };
})()
