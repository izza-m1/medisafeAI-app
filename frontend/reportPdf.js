// The safety report as a printable A4 page, made into a PDF. Built from the same report data the screen shows.
// Download: Android asks once which folder (Downloads, say) and saves it there; iPhone opens "Save to Files".
// Share: the phone's share sheet (WhatsApp, email...).
import { Platform } from 'react-native';
import AsyncStorage from '@react-native-async-storage/async-storage';
import { File, Directory, Paths } from 'expo-file-system';
import * as Print from 'expo-print';
import * as Sharing from 'expo-sharing';

const VERDICT = { 'Safe': 'Safe for you', 'Use with caution': 'Take with care', 'Not safe': 'Not safe for you' };
const STATUS_TEXT = { ok: 'OK', info: 'Check pack', caution: 'Check', stop: 'Not suitable' };
const COLOR = { ok: '#1E7D3A', info: '#4B6563', caution: '#B45309', stop: '#C0261A' };
const BRAND = { main: '#0E7C7B', dark: '#0A5958', mint: '#8EDDD1', ink: '#0B2523', sub: '#4B6563', line: '#E1EAE8' };  // ui.js colours

const esc = v => String(v ?? '').replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
const textOf = item => (typeof item === 'string' ? item : item?.text || '');
const list = items => (items.length ? `<ul>${items.map(i => `<li>${i}</li>`).join('')}</ul>` : '<p class="muted">None listed.</p>');

// The MediSafe mark, the same teal square with a white cross and mint dot as the app (ui.js Logo).
const LOGO = `<svg width="30" height="30" viewBox="0 0 34 34" xmlns="http://www.w3.org/2000/svg">
  <rect width="34" height="34" rx="10" fill="${BRAND.main}"/><rect x="13.6" y="7.5" width="6.8" height="19" rx="2.4" fill="#fff"/>
  <rect x="7.5" y="13.6" width="19" height="6.8" rx="2.4" fill="#fff"/><circle cx="26.5" cy="7.5" r="2.7" fill="${BRAND.mint}"/></svg>`;

const yesNo = v => (v ? 'Yes' : 'No');

// Patient details two to a row: name and age, then gender, then (for women) periods, pregnancy and breastfeeding.
function personGrid(p, name) {
  const cells = [['Name', name || 'Not given'], ['Age', `${p.age} years`], ['Gender', p.sex === 'female' ? 'Female' : 'Male']];
  if (p.sex === 'female') {
    if (p.periods) cells.push(['Periods', p.periods === 'no' ? 'No' : 'Yes']);
    cells.push(['Pregnant', yesNo(p.pregnant)], ['Breastfeeding', yesNo(p.breastfeeding)]);
  }
  const rows = [];
  for (let i = 0; i < cells.length; i += 2) {
    rows.push(`<tr>${cells.slice(i, i + 2).map(([k, v]) => `<th>${esc(k)}</th><td>${esc(v)}</td>`).join('')}${cells[i + 1] ? '' : '<th></th><td></td>'}</tr>`);
  }
  const wide = [
    ['Health conditions', (p.conditions || []).join(', ') || 'None given'],
    ['Medicines', (p.medicine_names || []).join(', ') || 'None given'],
    ['Other supplements', (p.supplements || []).join(', ') || 'None given'],
  ].map(([k, v]) => `<tr><th>${esc(k)}</th><td colspan="3">${esc(v)}</td></tr>`);
  return rows.join('') + wide.join('');
}

// "You also take Caltrate: take iron and calcium at different times." when the pair meets one of the user's own supplements.
export function pairText(o) {
  return o.with_yours?.length ? `You also take ${o.with_yours.join(', ')}: ${o.text}` : o.text;
}

// Supplements the user typed that the NIH data does not name, so nothing was checked for them.
export function uncheckedText(names) {
  return names?.length ? `${names.join(', ')}: not found in the NIH data, so not checked. Ask your pharmacist.` : '';
}

export function reportHtml(data, name) {
  const r = data.report;
  const v = r.is_safe_to_take;
  const tone = v.tone || { 'Safe': 'ok', 'Use with caution': 'caution', 'Not safe': 'stop' }[v.verdict];
  const dose = r.recommended_dosage?.summary || {};
  const checks = v.checks.filter(c => c.key !== 'maker');
  const sources = [...new Set([
    ...checks.map(c => c.source).filter(u => u?.startsWith('http')),
    ...(r.fact_sheets || []).map(f => f.url),
  ])];
  return `<!DOCTYPE html><html><head><meta charset="utf-8"><style>
    @page { size: A4; margin: 18mm 16mm; }
    body { font-family: -apple-system, Roboto, "Segoe UI", Arial, sans-serif; color: ${BRAND.ink}; font-size: 11pt; line-height: 1.45; }
    header { display: flex; justify-content: space-between; align-items: center; border-bottom: 2px solid ${BRAND.main}; padding-bottom: 8px; }
    .brand { display: flex; align-items: center; gap: 8px; color: ${BRAND.main}; font-weight: 800; font-size: 16pt; }
    .meta { color: ${BRAND.sub}; font-size: 9.5pt; text-align: right; }
    h1 { font-size: 18pt; margin: 14px 0 2px; }
    h2 { font-size: 12.5pt; color: ${BRAND.dark}; margin: 18px 0 6px; border-bottom: 1px solid ${BRAND.line}; padding-bottom: 3px; }
    table { width: 100%; border-collapse: collapse; }
    th, td { text-align: left; vertical-align: top; padding: 5px 6px; border-bottom: 1px solid ${BRAND.line}; }
    th { width: 22%; color: ${BRAND.sub}; font-weight: 600; }
    .patient th { width: 16%; } .patient td { width: 34%; }
    .verdict { border: 2px solid ${COLOR[tone]}; border-radius: 8px; padding: 10px 12px; margin-top: 12px; }
    .verdict b { color: ${COLOR[tone]}; font-size: 15pt; }
    .tag { font-weight: 700; font-size: 9pt; text-transform: uppercase; }
    ul { margin: 4px 0; padding-left: 18px; } li { margin: 2px 0; }
    .muted { color: ${BRAND.sub}; } .small { font-size: 9pt; color: ${BRAND.sub}; word-break: break-all; }
    footer { margin-top: 22px; border-top: 1px solid ${BRAND.line}; padding-top: 8px; font-size: 9pt; color: ${BRAND.sub}; }
  </style></head><body>
    <header><div class="brand">${LOGO}<span>MediSafe AI</span></div>
      <div class="meta">Supplement safety report<br>Generated ${esc(new Date().toLocaleString(undefined, { day: 'numeric', month: 'long', year: 'numeric', hour: 'numeric', minute: '2-digit' }))}</div></header>
    <h1>${esc(data.product.name)}</h1>
    <div class="muted">Made by: ${esc(data.company?.name || 'Not seen on the pack')}</div>

    <h2>Patient</h2><table class="patient">${personGrid(data.profile, name)}
      <tr><th>Reasons for taking it</th><td colspan="3">${esc((data.reasons || []).join(', ') || 'Not given')}</td></tr></table>

    <div class="verdict"><b>${esc(v.title || VERDICT[v.verdict])}</b><p>${esc(v.reason)}</p></div>

    <h2>Safety checks</h2><table>${checks.map(c => `<tr><th>${esc(c.title)}</th>
      <td><span class="tag" style="color:${COLOR[c.status]}">${STATUS_TEXT[c.status]}</span><br>${esc(c.text)}</td></tr>`).join('')}</table>

    ${dose.doctor_only ? '<h2>How to take it</h2><p><b>Only take this if your doctor prescribed it.</b></p>' : `
    <h2>How to take it</h2><table>
      <tr><th>Amount</th><td>${esc(dose.amount || 'As on the pack')}</td></tr>
      <tr><th>How often</th><td>${esc(dose.how_often || 'As on the pack')}</td></tr>
      <tr><th>When</th><td>${esc(dose.when || 'As on the pack')}</td></tr></table>
      ${dose.short_course ? '<p><b>Short course only.</b> Not for daily use over many months unless a doctor advises.</p>' : ''}
      ${(r.tips || []).map(t => `<p>${esc(t.text)}</p>`).join('')}`}

    <h2>Foods and drinks</h2>
    <p><b>Can lower how much you absorb:</b></p>${list((r.foods_to_avoid || []).map(f => `${esc(f.food)}${f.nutrients ? ` (${esc(f.nutrients.join(', '))})` : ''}`))}
    <p><b>Helps you absorb it:</b></p>${list((r.recommended_foods || []).map(f => `${esc(f.food)}${f.nutrients ? ` (${esc(f.nutrients.join(', '))})` : ''}`))}

    ${(r.other_supplements || []).length || (r.unrecognised_supplements || []).length ? `<h2>With other supplements</h2>${list([
      ...(r.other_supplements || []).map(o => esc(pairText(o))),
      ...(r.unrecognised_supplements?.length ? [esc(uncheckedText(r.unrecognised_supplements))] : [])])}` : ''}

    ${(r.purpose_check?.results || []).length ? `<h2>Your reasons</h2>${list(r.purpose_check.results.map(p => `<b>${esc(p.reason)}:</b> ${esc(p.text)}`))}` : ''}

    <h2>About this supplement</h2>
    ${r.actual_usage ? `<p>${esc(textOf(r.actual_usage))}</p>` : ''}
    ${(r.benefits || []).length ? `<p><b>Benefits</b></p>${list(r.benefits.map(b => esc(textOf(b))))}` : ''}
    ${(r.side_effects || []).length ? `<p><b>Possible side effects</b></p>${list(r.side_effects.map(b => esc(textOf(b))))}` : ''}

    <h2>Sources</h2>${sources.map(u => `<div class="small">${esc(u)}</div>`).join('')}
    <footer>Made by MediSafe AI from NIH Office of Dietary Supplements, NIH NCCIH and USDA FoodData Central data.
      This report is information, not a prescription. Follow the directions on the pack, or your doctor's advice.</footer>
  </body></html>`;
}

// "MediSafe-Report-Centrum-Women-22-Nov-2026.pdf"
function fileName(data) {
  const product = (data.product?.name || 'Supplement').replace(/[^A-Za-z0-9]+/g, '-').replace(/^-|-$/g, '');
  const day = new Date().toLocaleDateString('en-GB', { day: '2-digit', month: 'short', year: 'numeric' }).replace(/ /g, '-');
  return `MediSafe-Report-${product}-${day}.pdf`;
}

// The PDF in the app's cache, with a readable name.
async function makePdf(data, name) {
  const { uri } = await Print.printToFileAsync({ html: reportHtml(data, name) });
  const named = new File(Paths.cache, fileName(data));
  if (named.exists) named.delete();
  await new File(uri).copy(named);
  return named;
}

const FOLDER_KEY = 'medisafe_pdf_folder';        // the folder the user picked last time (Android)

// Returns { saved: true, folder, file } when saved, { saved: false } if the user cancelled the folder picker,
// { saved: null } on iPhone (the user finishes in "Save to Files").
export async function downloadReportPdf(data, name) {
  const pdf = await makePdf(data, name);
  if (Platform.OS !== 'android') {
    await Sharing.shareAsync(pdf.uri, { mimeType: 'application/pdf', UTI: 'com.adobe.pdf', dialogTitle: 'Save your report' });
    return { saved: null, file: pdf.name };
  }
  let folder;
  try {
    folder = await Directory.pickDirectoryAsync((await AsyncStorage.getItem(FOLDER_KEY)) || undefined);
  } catch {
    return { saved: false };
  }
  await AsyncStorage.setItem(FOLDER_KEY, folder.uri).catch(() => {});
  const out = folder.createFile(pdf.name, 'application/pdf');
  out.write(await pdf.bytes());
  return { saved: true, folder: decodeURIComponent(folder.name || 'the folder you chose'), file: pdf.name, open: () => out.preview?.() };
}

export async function shareReportPdf(data, name) {
  const pdf = await makePdf(data, name);
  await Sharing.shareAsync(pdf.uri, { mimeType: 'application/pdf', UTI: 'com.adobe.pdf', dialogTitle: 'Share your report' });
}
