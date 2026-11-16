/* ============================================================
   config.js — הגדרות האתר
   כל מה שצריך לעדכן מעת לעת (טלפון, מחירים, קישורים) נמצא כאן.
   הקובץ נטען ראשון; i18n.js ו-app.js קוראים ממנו.
   ============================================================ */
'use strict';

const CONFIG = Object.freeze({
  phone: "972544633386",            // ← מספר ה-WhatsApp בפורמט בינלאומי, בלי + ובלי 0 מוביל
  displayPhone: "054-463-3386",     // ← איך המספר יוצג באתר
  dropoffAddress: "",               // ← כתובת ההשארה. ריק = לא מוצגת באתר (נשלחת ללקוח ב-WhatsApp בלבד)
  videoUrl: "",                     // ← שם קובץ mp4 שיושב לצד index.html (קובץ מקומי בלבד). ריק = מוצג כפתור "שלחו לי את הסרטון"
  address: "כביש עוקף דרום, כפר ויתקין",
  businessName: "אלון להק — סדנה לתיקוני גלשנים",
  businessId: "",                   // ← מספר עוסק מורשה/פטור. ריק = לא מוצג
  legalUpdated: "אוגוסט 2026",       // ← תאריך עדכון ההצהרות המשפטיות
  legalUpdatedEn: "August 2026",     // ← אותו תאריך, באנגלית
  // ← קישורים חיצוניים: חייבים להתחיל ב-https:// (קישור אחר לא יוחל)
  mapsUrl: "https://maps.app.goo.gl/7fCY8iCD42zbD3Uk7",   // ← הפין של אלון ב-Google Maps
  wazeUrl: "https://waze.com/ul/hsvbb1wjs7",              // ← הפין של אלון ב-Waze
  // ← מחירים: כרגע כבויים. הבוט אומר שאלון מתמחר לפי תמונות, בלי מספרים.
  //   כדי להפעיל, החליפו את prices: null בבלוק הזה עם המחירים האמיתיים:
  //   prices: { small: "₪150–₪300", medium: "₪300–₪600", big: "₪600 ומעלה" }
  prices: null,
  // ← תנאי אחסון: כרגע מוצג בלי מספרים. כשאלון יחליט, החליפו ל:
  //   storage: { freeDays: 14, fee: "₪10 ליום" }
  storage: null,
  // ← ערכת תיקון עצמי. price: null = מוצג "מחיר ב-WhatsApp".
  //   כשיש מחיר, למשל: price: "₪149"
  //   contents: עדכנו לפי מה שבאמת נמצא בערכה
  kit: {
    name: "DING-AID",
    shopUrl: "https://dingaid.shop/",   // ← לאן מפנים לרכישת הערכה
    price: null,
    priceNote: "ערכת תיקון מהיר לדינגים קטנים · רכישה באתר dingaid.shop",
    contents: [
      "מדבקות DING-AID שקופות",
      "שרף Fiber-Fill"
    ]
  },
  // ← אותה ערכה באנגלית (המחיר נלקח מ-kit.price למעלה)
  kitEn: {
    name: "DING-AID",
    priceNote: "A speed repair kit for minor dings · Buy at dingaid.shop",
    contents: [
      "Clear DING-AID stickers",
      "Fiber-fill resin"
    ]
  }
});
