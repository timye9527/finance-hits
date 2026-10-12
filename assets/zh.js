/* 简 / 繁 切换(右上角)。页面按简体生成;点「繁」时才加载 OpenCC 词库(约 1MB,
 * 只加载一次),把页面文字转成香港繁体。点「简」直接还原生成时的原文,所以
 * YouTube 原标题(本来就是繁体)不会被转成简体。选择记在 localStorage,换期数也保持。
 * 每页只需要一行:<script src="assets/zh.js" defer></script>(weeks/ 下用 ../assets/)。 */
(function () {
  var KEY = "fh-script";
  var me = document.currentScript;
  var base = me ? me.src.replace(/zh\.js(\?.*)?$/, "") : "assets/";
  var conv = null, loading = null, saved = null, mode = "hans";

  var css = document.createElement("style");
  css.textContent =
    ".zh-switch{position:fixed;top:12px;right:16px;z-index:50;display:flex;padding:3px;gap:2px;" +
    "background:var(--surface,#fcfcfb);border:1px solid var(--c-hit,#2a78d6);border-radius:999px;" +
    "box-shadow:0 4px 14px rgba(0,0,0,.12);font:600 14px/1 system-ui,-apple-system,'PingFang SC',sans-serif}" +
    ".zh-switch button{all:unset;cursor:pointer;padding:7px 13px;border-radius:999px;color:var(--ink2,#52514e)}" +
    ".zh-switch button[aria-pressed=true]{background:var(--c-hit,#2a78d6);color:#fff}" +
    ".zh-switch button:focus-visible{outline:3px solid color-mix(in srgb,var(--c-hit,#2a78d6) 45%,transparent);outline-offset:2px}" +
    ".zh-switch.busy{opacity:.6;pointer-events:none}" +
    ".jumpnav{padding-right:112px}" +
    "@media print{.zh-switch{display:none}}";
  document.head.appendChild(css);

  var box = document.createElement("div");
  box.className = "zh-switch";
  box.setAttribute("role", "group");
  box.setAttribute("aria-label", "简体 / 繁體");
  box.innerHTML = '<button type="button" data-v="hans" lang="zh-Hans" title="简体中文">简</button>' +
                  '<button type="button" data-v="hant" lang="zh-Hant" title="繁體中文">繁</button>';
  document.body.appendChild(box);

  function paint() {
    var bs = box.querySelectorAll("button");
    for (var i = 0; i < bs.length; i++) bs[i].setAttribute("aria-pressed", bs[i].dataset.v === mode);
  }

  function load() {
    if (conv) return Promise.resolve();
    if (!loading) loading = new Promise(function (ok, fail) {
      var s = document.createElement("script");
      s.src = base + "opencc-cn2t.js";
      s.onload = function () { conv = OpenCC.Converter({ from: "cn", to: "hk" }); ok(); };
      s.onerror = function () { loading = null; fail(); };
      document.head.appendChild(s);
    });
    return loading;
  }

  // Collect once, before any conversion, so 简 always restores the generated original.
  function snapshot() {
    if (saved) return;
    saved = { text: [], attr: [], title: document.title };
    var w = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT, {
      acceptNode: function (n) {
        var p = n.parentNode;
        if (!n.nodeValue.trim() || !p || /^(SCRIPT|STYLE|NOSCRIPT)$/.test(p.nodeName) || box.contains(n))
          return NodeFilter.FILTER_REJECT;
        return NodeFilter.FILTER_ACCEPT;
      }
    });
    for (var n; (n = w.nextNode());) saved.text.push([n, n.nodeValue]);
    var els = document.body.querySelectorAll("[title],[aria-label],[alt]");
    for (var i = 0; i < els.length; i++) {
      if (box.contains(els[i])) continue;
      ["title", "aria-label", "alt"].forEach(function (a) {
        if (els[i].hasAttribute(a)) saved.attr.push([els[i], a, els[i].getAttribute(a)]);
      });
    }
  }

  function apply(v) {
    if (v === "hant") {
      box.classList.add("busy");
      return load().then(function () {
        snapshot();
        saved.text.forEach(function (t) { t[0].nodeValue = conv(t[1]); });
        saved.attr.forEach(function (a) { a[0].setAttribute(a[1], conv(a[2])); });
        document.title = conv(saved.title);
        document.documentElement.lang = "zh-Hant-HK";
        mode = "hant"; paint(); box.classList.remove("busy");
      }, function () {
        box.classList.remove("busy");
        alert("繁体词库加载失败,请检查网络后再试。");
      });
    }
    if (saved) {
      saved.text.forEach(function (t) { t[0].nodeValue = t[1]; });
      saved.attr.forEach(function (a) { a[0].setAttribute(a[1], a[2]); });
      document.title = saved.title;
    }
    document.documentElement.lang = "zh-Hans";
    mode = "hans"; paint();
  }

  box.addEventListener("click", function (e) {
    var v = e.target.dataset && e.target.dataset.v;
    if (!v || v === mode) return;
    try { localStorage.setItem(KEY, v); } catch (_) {}
    apply(v);
  });

  paint();
  var pref = null;
  try { pref = localStorage.getItem(KEY); } catch (_) {}
  if (pref === "hant") apply("hant");
})();
