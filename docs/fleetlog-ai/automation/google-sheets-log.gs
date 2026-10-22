/**
 * FleetLog AI -> Google Sheets event log (optional, free). No n8n needed.
 *
 * Setup (5 minutes):
 *  1. Create a Google Sheet; Extensions > Apps Script; paste this file.
 *  2. Project Settings > Script properties: add FLEETLOG_SECRET = any long random string.
 *  3. Deploy > New deployment > Web app: execute as "Me", access "Anyone". Copy the /exec URL.
 *  4. In FleetLog AI's environment (.env / Vercel): OPS_EVENTS_WEBHOOK_URL = that URL,
 *     OPS_EVENTS_WEBHOOK_SECRET = the same secret.
 *
 * Every business event (issue.reported, booking.created, booking.approved, booking.rescheduled, issue.resolved,
 * fuel.abnormal, brief.sent, ...) becomes one row in a tab named after the event.
 * Note: Apps Script web apps cannot read request headers, so the secret also travels as ?key=... in the URL:
 * set OPS_EVENTS_WEBHOOK_URL to "<exec URL>?key=<secret>".
 */
function doPost(e) {
  var secret = PropertiesService.getScriptProperties().getProperty('FLEETLOG_SECRET');
  if (!secret || !e || !e.parameter || e.parameter.key !== secret) {
    return ContentService.createTextOutput(JSON.stringify({ ok: false, error: 'forbidden' }))
      .setMimeType(ContentService.MimeType.JSON);
  }
  var body = JSON.parse(e.postData.contents);
  var data = body.data || {};
  var book = SpreadsheetApp.getActiveSpreadsheet();
  var sheet = book.getSheetByName(body.event) || book.insertSheet(body.event);
  var keys = Object.keys(data).filter(function (k) { return typeof data[k] !== 'object' || data[k] === null; });
  if (sheet.getLastRow() === 0) sheet.appendRow(['received_at'].concat(keys));
  var header = sheet.getRange(1, 1, 1, sheet.getLastColumn()).getValues()[0];
  keys.forEach(function (k) {            // new fields get a new column
    if (header.indexOf(k) < 0) { header.push(k); sheet.getRange(1, header.length).setValue(k); }
  });
  sheet.appendRow(header.map(function (k) { return k === 'received_at' ? new Date() : (k in data ? data[k] : ''); }));
  return ContentService.createTextOutput(JSON.stringify({ ok: true })).setMimeType(ContentService.MimeType.JSON);
}
