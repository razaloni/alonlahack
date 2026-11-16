/* ============================================================
   app.js — הלוגיקה של העמוד
   תלוי ב-CONFIG (config.js) וב-I18N_EN / STR (i18n.js).

   תוכן:
     1. קבועים ועזרים
     2. קישורים (WhatsApp, טלפון, ניווט, חנות)
     3. שפה — עברית / English
     4. ערכת התיקון וסרטון ההגעה
     5. מידע משפטי — פתיחה לפי ה-hash בכתובת
     6. עוזר הסדנה (בוט)
     7. חשיפה בגלילה
     8. אתחול
   ============================================================ */
(() => {
  'use strict';

  /* ----------------------------------------------------------
     1. קבועים ועזרים
     ---------------------------------------------------------- */
  const SUPPORTED_LANGS = ['he', 'en'];
  const DEFAULT_LANG = 'he';
  const LANG_STORAGE_KEY = 'alonlahack-lang';
  const PHONE_PLACEHOLDER = '972500000000';
  const PHONE_PATTERN = /^\d{8,15}$/;
  const BOT_REPLY_DELAY_MS = 250;

  const byId = id => document.getElementById(id);
  const $ = (selector, root = document) => root.querySelector(selector);
  const $$ = (selector, root = document) => Array.from(root.querySelectorAll(selector));
  const hasOwn = (obj, key) => Object.prototype.hasOwnProperty.call(obj, key);

  /** מחזיר את הכתובת רק אם היא https תקינה; אחרת null (חוסם javascript:, data: וכד׳). */
  function safeHttpsUrl(url) {
    try {
      const parsed = new URL(url);
      return parsed.protocol === 'https:' ? parsed.href : null;
    } catch (err) {
      return null;
    }
  }

  /** פותח קישור חיצוני בלשונית חדשה, בלי גישה חזרה לעמוד הזה. */
  function openExternal(url) {
    const safe = safeHttpsUrl(url);
    if (safe) window.open(safe, '_blank', 'noopener');
  }

  const phoneIsValid = PHONE_PATTERN.test(CONFIG.phone) && CONFIG.phone !== PHONE_PLACEHOLDER;

  let lang = readInitialLang();
  /** הטקסטים של השפה הנוכחית. */
  const strings = () => STR[lang];

  /* ----------------------------------------------------------
     2. קישורים
     ---------------------------------------------------------- */
  function waLink(text) {
    return 'https://wa.me/' + CONFIG.phone + '?text=' + encodeURIComponent(text);
  }

  /** כל אלמנט עם data-wa="<שם תבנית>" הופך לקישור WhatsApp עם הודעה מוכנה. */
  function applyWhatsAppLinks() {
    if (!phoneIsValid) return;
    const templates = strings().templates;
    $$('[data-wa]').forEach(el => {
      const key = el.dataset.wa;
      el.href = waLink(hasOwn(templates, key) ? templates[key] : templates.general);
      el.target = '_blank';
      el.rel = 'noopener';
    });
  }

  /** קישורים חיצוניים שמנוהלים מ-CONFIG: data-link="maps|waze|shop". */
  function applyConfigLinks() {
    const links = { maps: CONFIG.mapsUrl, waze: CONFIG.wazeUrl, shop: CONFIG.kit.shopUrl };
    $$('[data-link]').forEach(el => {
      const key = el.dataset.link;
      const url = hasOwn(links, key) ? safeHttpsUrl(links[key]) : null;
      if (url) el.href = url;
    });
  }

  function initPhoneLink() {
    if (phoneIsValid) byId('telLink').href = 'tel:+' + CONFIG.phone;
    else byId('setup').hidden = false;
  }

  /* ----------------------------------------------------------
     3. שפה — עברית / English
     ---------------------------------------------------------- */
  function isSupportedLang(value) {
    return SUPPORTED_LANGS.includes(value);
  }

  /** סדר עדיפויות: ‎?lang=‎ בכתובת ← הבחירה השמורה ← ברירת מחדל. כל ערך אחר נדחה. */
  function readInitialLang() {
    try {
      const fromUrl = new URLSearchParams(location.search).get('lang');
      if (isSupportedLang(fromUrl)) return fromUrl;
      const stored = localStorage.getItem(LANG_STORAGE_KEY);
      if (isSupportedLang(stored)) return stored;
    } catch (err) { /* localStorage חסום — ממשיכים עם ברירת המחדל */ }
    return DEFAULT_LANG;
  }

  /** העברית המקורית של כל מפתח, נשמרת מה-HTML בפעם הראשונה כדי שאפשר יהיה לחזור אליה. */
  const hebrewSource = Object.create(null);

  function translateMarkup() {
    $$('[data-i18n]').forEach(el => {
      const key = el.dataset.i18n;
      if (!(key in hebrewSource)) hebrewSource[key] = el.innerHTML;
      // innerHTML בטוח כאן: המקור הוא ה-HTML של העמוד עצמו או המילון הקבוע ב-i18n.js.
      el.innerHTML = lang === 'en' && hasOwn(I18N_EN, key) ? I18N_EN[key] : hebrewSource[key];
    });
  }

  function setAttr(selector, attr, value) {
    const el = $(selector);
    if (el) el.setAttribute(attr, value);
  }

  function applyAccessibilityLabels() {
    const a = strings().attrs;
    setAttr('#fab', 'aria-label', a.fab);
    setAttr('#botwin', 'aria-label', a.botwin);
    setAttr('#botclose', 'aria-label', a.botclose);
    setAttr('nav', 'aria-label', a.nav);
    setAttr('.ba-before img', 'alt', a.before);
    setAttr('.ba-after video', 'aria-label', a.hero);
    setAttr('#mapframe iframe', 'title', a.map);
    $$('.reel video').forEach((video, i) => video.setAttribute('aria-label', a['r' + (i + 1)]));
  }

  /** טקסטים שמגיעים מ-CONFIG ולא מהמילון (טלפון, שנה, תאריכי עדכון, מספר עוסק). */
  function renderDynamicText() {
    const s = strings();

    const langBtn = byId('langBtn');
    langBtn.textContent = s.langBtn;
    langBtn.setAttribute('aria-label', s.langLabel);
    langBtn.setAttribute('lang', lang === 'en' ? 'he' : 'en');

    byId('telLink').textContent = lang === 'en' ? '+972-54-463-3386' : CONFIG.displayPhone;
    byId('yr').textContent = new Date().getFullYear();
    ['lu1', 'lu2', 'lu3'].forEach(id => {
      const el = byId(id);
      if (el) el.textContent = s.legalUpdated;
    });
    if (CONFIG.businessId) byId('bizid').textContent = s.bizid(CONFIG.businessId);

    $('.bot-head .av').textContent = lang === 'en' ? 'A' : 'א';
    const videoCaption = $('#videobox .vcap');
    if (videoCaption) videoCaption.textContent = s.vcap;
  }

  function applyLang(nextLang) {
    lang = isSupportedLang(nextLang) ? nextLang : DEFAULT_LANG;
    try { localStorage.setItem(LANG_STORAGE_KEY, lang); } catch (err) { /* לא קריטי */ }

    const root = document.documentElement;
    root.lang = lang;
    root.dir = lang === 'en' ? 'ltr' : 'rtl';
    document.title = strings().title;

    translateMarkup();          // קודם התרגום — הוא מחליף אלמנטים פנימיים
    applyAccessibilityLabels();
    renderDynamicText();        // ואז ממלאים מחדש את מה שהוחלף
    applyWhatsAppLinks();
    renderKit();
    resetBot();
  }

  /* ----------------------------------------------------------
     4. ערכת התיקון וסרטון ההגעה
     ---------------------------------------------------------- */
  function renderKit() {
    const s = strings();
    byId('kitName').textContent = s.kitName;
    byId('kitPrice').textContent = CONFIG.kit.price || s.kitPriceNone;
    byId('kitPriceNote').textContent = s.kitPriceNote || '';
    byId('kitOrder').textContent = s.kitOrder;

    const list = byId('kitContents');
    list.replaceChildren(...s.kitContents.map(text => {
      const li = document.createElement('li');
      li.textContent = text;
      return li;
    }));
  }

  /** אם הוגדר CONFIG.videoUrl — מציגים את סרטון ההגעה במקום כפתור הבקשה. */
  function initDropoffVideo() {
    if (!CONFIG.videoUrl) return;

    const video = document.createElement('video');
    video.controls = true;
    video.playsInline = true;
    video.preload = 'metadata';
    video.src = CONFIG.videoUrl;   // ה-CSP (media-src 'self') מאפשר רק קובץ מקומי
    const nodes = [video];

    if (CONFIG.dropoffAddress) {
      const address = document.createElement('p');
      address.className = 'vaddr';
      address.textContent = CONFIG.dropoffAddress;
      nodes.push(address);
    }

    const caption = document.createElement('p');
    caption.className = 'vcap';
    caption.textContent = strings().vcap;
    nodes.push(caption);

    byId('videobox').replaceChildren(...nodes);
  }

  function initMapFallback() {
    const frame = $('#mapframe iframe');
    if (frame) frame.addEventListener('error', () => { byId('mapfallback').hidden = false; });
  }

  /* ----------------------------------------------------------
     5. מידע משפטי — פתיחה לפי ה-hash בכתובת
     ---------------------------------------------------------- */
  /** פותח את סעיף ה-<details> שה-hash מצביע עליו (‎#a11y / #privacy / #terms‎). */
  function openDetailsFromHash() {
    // getElementById ולא querySelector: hash שרירותי מהכתובת אינו סלקטור תקין בהכרח.
    let id = '';
    try { id = decodeURIComponent(location.hash.slice(1)); } catch (err) { return; }
    const el = id ? byId(id) : null;
    if (!(el instanceof HTMLDetailsElement)) return;

    const box = el.closest('.legalbox');
    if (box) box.open = true;
    el.open = true;
    el.scrollIntoView({ behavior: 'smooth', block: 'center' });
  }

  function initLegalLinks() {
    window.addEventListener('hashchange', openDetailsFromHash);
    // לחיצה חוזרת על אותו קישור לא משנה את ה-hash, לכן מטפלים גם בלחיצה עצמה.
    $$('[data-legal]').forEach(link => link.addEventListener('click', () => setTimeout(openDetailsFromHash)));
    openDetailsFromHash();
  }

  /* ----------------------------------------------------------
     6. עוזר הסדנה — בוט תשובות ראשונות (דו-לשוני)
     ---------------------------------------------------------- */
  const botWindow = byId('botwin');
  const botBody = byId('botbody');
  const botQuick = byId('botquick');
  const fab = byId('fab');
  let botFlow = strings().bot.flow();
  let botStarted = false;

  function addBubble(text, who) {
    const bubble = document.createElement('div');
    bubble.className = 'msg ' + who;
    bubble.textContent = text;
    botBody.appendChild(bubble);
    botBody.scrollTop = botBody.scrollHeight;
  }

  function quickButton(label, extraClass, onClick) {
    const button = document.createElement('button');
    button.type = 'button';
    button.className = 'qr' + (extraClass ? ' ' + extraClass : '');
    button.textContent = label;
    button.addEventListener('click', onClick);
    return button;
  }

  function showStart() {
    addBubble(botFlow.start.msg, 'bot');
    setQuickReplies(botFlow.start.quick);
  }

  function setQuickReplies(labels) {
    const bot = strings().bot;
    const buttons = labels.map(label => {
      const isAction = hasOwn(bot.actions, label) || label === bot.toShop;
      return quickButton(label, isAction ? 'go' : '', () => handleReply(label));
    });
    buttons.push(quickButton(bot.other, '', () => {
      addBubble(bot.other, 'me');
      setTimeout(showStart, BOT_REPLY_DELAY_MS);
    }));
    botQuick.replaceChildren(...buttons);
  }

  function handleReply(label) {
    const bot = strings().bot;
    const backToStart = () => setQuickReplies(botFlow.start.quick);
    addBubble(label, 'me');

    // פתיחת WhatsApp עם הודעה מוכנה
    if (hasOwn(bot.actions, label)) {
      const url = waLink(strings().templates[bot.actions[label]]);
      setTimeout(() => {
        addBubble(bot.opening(), 'bot');
        if (phoneIsValid) openExternal(url);
        backToStart();
      }, BOT_REPLY_DELAY_MS);
      return;
    }

    // מעבר לחנות הערכה
    if (label === bot.toShop) {
      setTimeout(() => {
        addBubble(bot.shopMsg, 'bot');
        openExternal(CONFIG.kit.shopUrl);
        backToStart();
      }, BOT_REPLY_DELAY_MS);
      return;
    }

    // גלילה לקטע בעמוד
    if (label === bot.toKit || label === bot.toMap) {
      setTimeout(() => {
        if (label === bot.toMap) addBubble(bot.mapMsg(), 'bot');
        byId(label === bot.toKit ? 'kit' : 'workshop').scrollIntoView({ behavior: 'smooth' });
        closeBot();
        backToStart();
      }, BOT_REPLY_DELAY_MS);
      return;
    }

    // שאלה מתוך תרשים השיחה
    const node = hasOwn(botFlow, label) ? botFlow[label] : null;
    setTimeout(() => {
      addBubble(node ? node.msg : bot.unknown, 'bot');
      setQuickReplies(node ? node.quick : [Object.keys(bot.actions)[0]]);
    }, BOT_REPLY_DELAY_MS);
  }

  /** נקרא בהחלפת שפה: מתחיל את השיחה מחדש בשפה הנוכחית. */
  function resetBot() {
    botFlow = strings().bot.flow();
    botBody.replaceChildren();
    botQuick.replaceChildren();
    if (botStarted) showStart();
  }

  function openBot() {
    botWindow.classList.add('open');
    fab.setAttribute('aria-expanded', 'true');
    byId('fabdot').hidden = true;
    if (!botStarted) {
      botStarted = true;
      showStart();
    }
  }

  function closeBot() {
    botWindow.classList.remove('open');
    fab.setAttribute('aria-expanded', 'false');
  }

  function initBot() {
    fab.addEventListener('click', () => (botWindow.classList.contains('open') ? closeBot() : openBot()));
    byId('botclose').addEventListener('click', closeBot);
    document.addEventListener('keydown', e => { if (e.key === 'Escape') closeBot(); });
  }

  /* ----------------------------------------------------------
     7. חשיפה בגלילה
     ---------------------------------------------------------- */
  /**
   * אלמנטים עם ‎.rv‎ מוסתרים רק אחרי שהמחלקה js-reveal נוספה ל-<html>,
   * כך שבלי JavaScript (או אם הסקריפט נכשל) התוכן נשאר גלוי.
   */
  function initReveal() {
    const reducedMotion = matchMedia('(prefers-reduced-motion: reduce)').matches;
    if (!('IntersectionObserver' in window) || reducedMotion) return;

    document.documentElement.classList.add('js-reveal');
    const observer = new IntersectionObserver(entries => {
      entries.forEach(entry => {
        if (!entry.isIntersecting) return;
        entry.target.classList.add('in');
        observer.unobserve(entry.target);
      });
    }, { rootMargin: '0px 0px -8% 0px' });
    $$('.rv').forEach(el => observer.observe(el));
  }

  /* ----------------------------------------------------------
     8. אתחול
     ---------------------------------------------------------- */
  initReveal();
  initPhoneLink();
  applyConfigLinks();
  initDropoffVideo();
  initMapFallback();
  initBot();
  byId('langBtn').addEventListener('click', () => applyLang(lang === 'he' ? 'en' : 'he'));
  applyLang(lang);
  initLegalLinks();
})();
